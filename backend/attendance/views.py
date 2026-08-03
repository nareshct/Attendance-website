from decimal import Decimal

from django.db import transaction
from django.db.models import Exists, F, OuterRef
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
                qs = qs.filter(enrollment_id=enrollment_id, enrollment__trainer=user.trainer)
            else:
                qs = qs.filter(marked_by=user.trainer)
        elif enrollment_id:
            qs = qs.filter(enrollment_id=enrollment_id)

        trainer_id = self.request.query_params.get('trainer')
        date = self.request.query_params.get('date')
        if trainer_id and user.is_staff:
            qs = qs.filter(marked_by_id=trainer_id)
        if date:
            qs = qs.filter(date=date)
        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        if not user.is_staff and _is_closed(serializer.validated_data['date']):
            req = AttendanceRequest.objects.create(
                enrollment=serializer.validated_data['enrollment'],
                date=serializer.validated_data['date'],
                topic_covered=serializer.validated_data.get('topic_covered', ''),
                requested_by=user.trainer,
            )
            return Response(
                {
                    'pending_approval': True,
                    'detail': 'This date falls in a closed billing cycle. Your request has been sent to admin for approval.',
                    'request': AttendanceRequestSerializer(req).data,
                },
                status=status.HTTP_202_ACCEPTED,
            )

        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

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
        return qs

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        req = self.get_object()
        if req.status != 'pending':
            return Response({'detail': f'Request is already {req.status}.'}, status=status.HTTP_400_BAD_REQUEST)

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

                # Bill this class at the rate that was actually in effect on
                # req.date, not whatever the rate happens to be today — a rate
                # change made after this class's own cycle already closed
                # shouldn't retroactively reprice a class taught before it.
                # Falls back to the live rate if it's never changed.
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
