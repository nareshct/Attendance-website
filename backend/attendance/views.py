from decimal import Decimal

from django.db import transaction
from django.db.models import Exists, F, OuterRef, Q
from django.db.models.functions import Greatest
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from audit.services import log_action
from billing.models import B2CRevenueAdjustment, BillingCycle, ClientInvoiceAdjustment, PayoutAdjustment
from billing.services import get_or_create_cycle, historical_rate
from config.permissions import IsAdmin, IsAdminOrTrainer, IsTrainer
from enrollments.models import Enrollment
from enrollments.services import trainer_covers_enrollment

from .models import Attendance, AttendanceRequest
from .serializers import AttendanceRequestSerializer, AttendanceSerializer


def _is_closed(date):
    return (
        BillingCycle.objects.filter(cycle_start__lte=date, cycle_end__gte=date)
        .exclude(status='open')
        .exists()
    )


class AttendanceViewSet(ModelViewSet):
    serializer_class = AttendanceSerializer

    def get_permissions(self):
        if self.action == 'create':
            return [IsTrainer()]
        if self.action in ('partial_update', 'destroy'):
            return [IsAdminOrTrainer()]
        if self.action == 'update':
            return [IsAdmin()]
        return [IsAdminOrTrainer()]

    def get_queryset(self):
        closed_cycle_qs = BillingCycle.objects.filter(
            cycle_start__lte=OuterRef('date'), cycle_end__gte=OuterRef('date')
        ).exclude(status='open')

        qs = Attendance.objects.select_related(
            'enrollment__student', 'enrollment__course', 'enrollment__trainer', 'marked_by', 'approval_request'
        ).annotate(in_closed_cycle=Exists(closed_cycle_qs))
        user = self.request.user
        enrollment_id = self.request.query_params.get('enrollment')

        if not user.is_staff:
            if enrollment_id:
                # Full session history for one of the trainer's own current
                # enrollments — includes sessions taught before any transfer,
                # so a newly-assigned trainer can see everything already covered.
                # Also open to a trainer currently covering this enrollment as an
                # active substitute (see trainer_covers_enrollment) — MyStudentsView
                # already surfaces these enrollments to them, so history access
                # should match rather than silently coming back empty.
                is_own = Enrollment.objects.filter(id=enrollment_id, trainer=user.trainer).exists()
                if is_own or trainer_covers_enrollment(user.trainer, enrollment_id):
                    qs = qs.filter(enrollment_id=enrollment_id)
                else:
                    qs = qs.none()
            else:
                qs = qs.filter(marked_by=user.trainer)
        elif enrollment_id:
            qs = qs.filter(enrollment_id=enrollment_id)

        trainer_id = self.request.query_params.get('trainer')
        date = self.request.query_params.get('date')
        # Both bounds inclusive, same convention as reports/views.py's CSV exports —
        # lets a caller ask for just the window it actually needs (e.g. the current +
        # last billing cycle) instead of a trainer's entire history. Without this, a
        # trainer active long enough to have taught 100+ classes total would trip the
        # frontend's fail-loud pagination guard (see api/client.js unwrapPaginated) on
        # every page that used to fetch this endpoint unbounded.
        start = self.request.query_params.get('start')
        end = self.request.query_params.get('end')
        # A late-approved class keeps its own (earlier, already-closed-cycle) date —
        # only its *earnings* move to whatever cycle was open when it got approved (see
        # PayoutAdjustment). So a plain start/end window naturally excludes it even
        # though its payout amount is credited to that cycle. Pass this to also pull in
        # any attendance carried forward into cycle `carried_forward_cycle` — used by the
        # trainer's My Earnings and the admin Payouts page's per-cycle class breakdown,
        # so a cycle's classes list matches what it actually paid.
        carried_forward_cycle = self.request.query_params.get('carried_forward_cycle')
        if trainer_id and user.is_staff:
            qs = qs.filter(marked_by_id=trainer_id)
        if date:
            qs = qs.filter(date=date)
        if start or end or carried_forward_cycle:
            window_q = None
            if start or end:
                window_q = Q()
                if start:
                    window_q &= Q(date__gte=start)
                if end:
                    window_q &= Q(date__lte=end)
            if carried_forward_cycle:
                carried_q = Q(payout_adjustment__applied_cycle_id=carried_forward_cycle)
                qs = qs.filter(window_q | carried_q if window_q is not None else carried_q)
            else:
                qs = qs.filter(window_q)
        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        enrollment = serializer.validated_data['enrollment']
        attendance_date = serializer.validated_data['date']
        # Not a model field — pop it before any serializer.save() call below, or
        # Attendance.objects.create() would choke on an unexpected kwarg.
        confirm_duplicate = serializer.validated_data.pop('confirm_duplicate', False)

        if not user.is_staff:
            existing_count = Attendance.objects.filter(enrollment=enrollment, date=attendance_date).count()

            if existing_count >= 2:
                return Response(
                    {'detail': 'This student already has two classes recorded for this date — no further entries are allowed.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if existing_count == 1:
                if not confirm_duplicate:
                    # A plain resubmit (double-click, stale tab) stays a hard block —
                    # only an explicit confirm from the trainer turns this into an
                    # admin-approval request, so the request queue doesn't fill up
                    # with ordinary mistakes. See MarkAttendancePage.jsx.
                    return Response(
                        {
                            'duplicate_confirm_required': True,
                            'detail': 'Attendance for this class on this date has already been marked. '
                                      'If this is genuinely a second class today, confirm to send it to admin for approval.',
                        },
                        status=status.HTTP_409_CONFLICT,
                    )
                return self._request_approval(
                    enrollment, attendance_date, serializer.validated_data.get('topic_covered', ''), user.trainer,
                    request_type='duplicate_day',
                    pending_detail='A request for a second class on this date is already pending admin approval.',
                    new_detail='This is a second class for this student today — a request has been sent to admin for approval.',
                )

            if _is_closed(attendance_date):
                return self._request_approval(
                    enrollment, attendance_date, serializer.validated_data.get('topic_covered', ''), user.trainer,
                    request_type='late_entry',
                    pending_detail='A request for this date is already pending admin approval.',
                    new_detail='This date falls in a closed billing cycle. Your request has been sent to admin for approval.',
                )

        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def _request_approval(self, enrollment, attendance_date, topic_covered, trainer, *, request_type, pending_detail, new_detail):
        # Without this check, a double-submit (or resubmitting after the tab was left
        # open) would create a second pending request for the same class. Both would
        # look approvable independently — see approve()'s matching guard on the other
        # side of the same race.
        existing_request = AttendanceRequest.objects.filter(
            enrollment=enrollment, date=attendance_date, status='pending', request_type=request_type,
        ).first()
        if existing_request is not None:
            return Response(
                {'pending_approval': True, 'detail': pending_detail, 'request': AttendanceRequestSerializer(existing_request).data},
                status=status.HTTP_202_ACCEPTED,
            )

        req = AttendanceRequest.objects.create(
            enrollment=enrollment, date=attendance_date, topic_covered=topic_covered,
            requested_by=trainer, request_type=request_type,
        )
        return Response(
            {'pending_approval': True, 'detail': new_detail, 'request': AttendanceRequestSerializer(req).data},
            status=status.HTTP_202_ACCEPTED,
        )

    @transaction.atomic
    def perform_create(self, serializer):
        # A trainer only ever logs a session they actually taught — marking it
        # IS the "present" signal. There's no separate absent action; a class
        # the trainer skips just never gets a record.
        attendance = serializer.save(marked_by=self.request.user.trainer, status='present')

        # Locked for the duration of this transaction so two classes for the same
        # enrollment can't be marked concurrently and lose an increment.
        enrollment = Enrollment.objects.select_for_update().get(pk=attendance.enrollment_id)
        enrollment.classes_completed = F('classes_completed') + 1
        enrollment.save(update_fields=['classes_completed'])
        enrollment.refresh_from_db(fields=['classes_completed'])
        enrollment.sync_completion_status()

    def perform_update(self, serializer):
        attendance = serializer.instance
        user = self.request.user

        if not user.is_staff:
            # get_queryset()'s ?enrollment= branch deliberately broadens read access to
            # every session on one of the trainer's own current enrollments, including
            # ones logged by a previous trainer before a transfer — that's for viewing
            # history. Editing/deleting must stay narrower: only whoever actually
            # marked_by this specific row, not whoever currently owns the enrollment.
            if attendance.marked_by_id != user.trainer.id:
                raise PermissionDenied('You can only edit a class you marked yourself.')
            allowed_fields = {'topic_covered', 'date'}
            if set(self.request.data.keys()) - allowed_fields:
                raise ValidationError('You can only edit the date or topic covered for your own classes.')

        # Applies to admins too, not just trainers: once a cycle closes, its Payout/
        # ClientInvoice totals are frozen (and any late class routes through the
        # AttendanceRequest approval flow instead). Editing/deleting an attendance row
        # here wouldn't recalculate those totals, so it would silently make them wrong
        # — and for a late-approved class it would cascade-delete its PayoutAdjustment/
        # ClientInvoiceAdjustment audit row (OneToOneField, on_delete=CASCADE).
        if _is_closed(attendance.date):
            raise PermissionDenied('This class falls in a closed billing cycle and can no longer be edited.')

        new_date = serializer.validated_data.get('date', attendance.date)
        if new_date != attendance.date and _is_closed(new_date):
            raise PermissionDenied('You cannot move this class into a closed billing cycle.')

        serializer.save()

    @transaction.atomic
    def perform_destroy(self, instance):
        user = self.request.user
        # See perform_update — same reasoning, marked_by not the enrollment's current trainer.
        if not user.is_staff and instance.marked_by_id != user.trainer.id:
            raise PermissionDenied('You can only delete a class you marked yourself.')

        # See perform_update — applies to admins too, for the same reason.
        if _is_closed(instance.date):
            raise PermissionDenied('This class falls in a closed billing cycle and can no longer be deleted.')

        enrollment = instance.enrollment
        was_present = instance.status == 'present'
        log_action(
            self.request.user, 'attendance_delete',
            f'{enrollment.student.name} — {enrollment.course.name} — {instance.date}',
            f'marked by {instance.marked_by.name}',
        )
        instance.delete()

        if was_present:
            # Locked for the duration of this transaction — see perform_create.
            enrollment = Enrollment.objects.select_for_update().get(pk=enrollment.pk)
            enrollment.classes_completed = Greatest(F('classes_completed') - 1, 0)
            enrollment.save(update_fields=['classes_completed'])
            enrollment.refresh_from_db(fields=['classes_completed'])
            enrollment.sync_completion_status()


class AttendanceRequestViewSet(ReadOnlyModelViewSet):
    serializer_class = AttendanceRequestSerializer

    def get_permissions(self):
        if self.action in ('approve', 'deny'):
            return [IsAdmin()]
        return [IsAdminOrTrainer()]

    def get_queryset(self):
        qs = AttendanceRequest.objects.select_related('enrollment__student', 'enrollment__course', 'requested_by')
        if not self.request.user.is_staff:
            qs = qs.filter(requested_by=self.request.user.trainer)
        trainer_id = self.request.query_params.get('trainer')
        if trainer_id:
            qs = qs.filter(requested_by_id=trainer_id)
        # Comma-separated, e.g. ?status=approved,denied — lets the admin Requests page
        # fetch "pending" (a small, naturally self-draining queue) and "reviewed" (an
        # ever-growing history, paginated with Load more) as two separate, bounded
        # requests instead of one unbounded fetch of every request ever made. See
        # AttendanceRequestsPage.jsx and the same fail-loud guard this pattern avoids
        # tripping in api/client.js's unwrapPaginated.
        status_param = self.request.query_params.get('status')
        if status_param:
            qs = qs.filter(status__in=status_param.split(','))
        return qs

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        req = self.get_object()
        if req.status != 'pending':
            return Response({'detail': f'Request is already {req.status}.'}, status=status.HTTP_400_BAD_REQUEST)

        # Belt-and-suspenders alongside the dedupe check in AttendanceViewSet.create():
        # a second pending request for the same (enrollment, date) can still exist from
        # before that check was added, or if the class got marked normally in the
        # meantime. A 'duplicate_day' request expects to find exactly one existing row
        # (the first class it's adding a second one alongside) — anything past the
        # 2-per-day cap, or any existing row at all for a 'late_entry' request, means
        # this request is stale and should be denied instead of approved.
        existing_count = Attendance.objects.filter(enrollment=req.enrollment, date=req.date).count()
        max_before_approval = 1 if req.request_type == 'duplicate_day' else 0
        if existing_count > max_before_approval:
            return Response(
                {'detail': 'A class is already recorded for this enrollment and date. Deny this request instead.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            attendance = Attendance.objects.create(
                enrollment=req.enrollment,
                date=req.date,
                status='present',
                topic_covered=req.topic_covered,
                marked_by=req.requested_by,
            )
            # Locked for the duration of this transaction — see AttendanceViewSet.perform_create.
            enrollment = Enrollment.objects.select_for_update().get(pk=req.enrollment_id)
            enrollment.classes_completed = F('classes_completed') + 1
            enrollment.save(update_fields=['classes_completed'])
            enrollment.refresh_from_db(fields=['classes_completed'])
            enrollment.sync_completion_status()

            req.status = 'approved'
            req.attendance = attendance
            req.reviewed_at = timezone.now()
            req.save(update_fields=['status', 'attendance', 'reviewed_at'])

            # This date lands in an already-closed cycle (that's why it needed
            # approval) — closing a cycle is what generates its Payout, so that
            # payout has already been finalized (paid or not). Never edit it
            # after the fact — carry this class's earnings forward to the
            # trainer's current, still-open cycle instead.
            cycle = BillingCycle.objects.filter(
                cycle_start__lte=req.date, cycle_end__gte=req.date
            ).exclude(status='open').first()
            if cycle:
                current_cycle, _ = get_or_create_cycle()

                # An enrollment-specific rate (set on the enrollment form) always wins —
                # see Enrollment.trainer_rate_per_class. Otherwise, bill this class at the
                # rate that was actually in effect on req.date, not whatever the rate
                # happens to be today — a rate change made after this class's own cycle
                # already closed shouldn't retroactively reprice a class taught before it.
                # Falls back to the live rate if it's never changed.
                trainer_rate = req.enrollment.trainer_rate_per_class
                if trainer_rate is None:
                    trainer_rate = historical_rate(req.requested_by, req.enrollment.course, req.date)
                    if trainer_rate is None:
                        trainer_rate = req.requested_by.rate_for(req.enrollment.course) or Decimal('0.00')

                PayoutAdjustment.objects.create(
                    trainer=req.requested_by,
                    attendance=attendance,
                    source_cycle=cycle,
                    amount=trainer_rate,
                    applied_cycle=current_cycle,
                )

                # Revenue side: closing a cycle is what freezes its billed
                # amount — the client's ClientInvoice for B2B, or the
                # dashboard's CycleRevenueSnapshot for B2C — so pending or not,
                # don't edit it after the fact. Add this class's revenue to the
                # current, still-open cycle instead of the closed one.
                student = req.enrollment.student
                if student.source_type == 'B2C':
                    course_rate = historical_rate(req.enrollment.course, None, req.date)
                    if course_rate is None:
                        course_rate = req.enrollment.course.rate_per_class or Decimal('0.00')
                    B2CRevenueAdjustment.objects.create(
                        attendance=attendance,
                        source_cycle=cycle,
                        amount=course_rate,
                        trainer_cost=trainer_rate,
                        applied_cycle=current_cycle,
                    )
                elif student.client is not None:
                    client_rate = req.enrollment.client_rate_per_class
                    if client_rate is None:
                        client_rate = historical_rate(student.client, req.enrollment.course, req.date)
                        if client_rate is None:
                            client_rate = student.client.rate_for(req.enrollment.course) or Decimal('0.00')
                    ClientInvoiceAdjustment.objects.create(
                        client=student.client,
                        attendance=attendance,
                        source_cycle=cycle,
                        amount=client_rate,
                        trainer_cost=trainer_rate,
                        applied_cycle=current_cycle,
                    )

        return Response(AttendanceRequestSerializer(req).data)

    @action(detail=True, methods=['post'])
    def deny(self, request, pk=None):
        req = self.get_object()
        if req.status != 'pending':
            return Response({'detail': f'Request is already {req.status}.'}, status=status.HTTP_400_BAD_REQUEST)

        req.status = 'denied'
        req.reviewed_at = timezone.now()
        req.save(update_fields=['status', 'reviewed_at'])

        return Response(AttendanceRequestSerializer(req).data)
