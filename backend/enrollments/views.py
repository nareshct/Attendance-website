import re
from datetime import date
from decimal import Decimal, InvalidOperation

from django.db.models import Q
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import filters, status
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed, PermissionDenied
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from audit.services import log_action
from config.permissions import IsAdmin, IsAdminOrTrainer, IsTrainer
from trainers.models import Trainer

from .certificate_pdf import render_certificate_pdf
from .models import Enrollment, PaymentInstallment, SubstituteAssignment
from .report_pdf import render_student_report_pdf
from .serializers import EnrollmentSerializer, PaymentInstallmentSerializer, SubstituteAssignmentSerializer
from .services import find_schedule_conflict, trainer_payment_gate


class EnrollmentViewSet(ModelViewSet):
    queryset = Enrollment.objects.select_related('student', 'course', 'trainer').order_by('-start_date')
    serializer_class = EnrollmentSerializer
    permission_classes = [IsAdmin]
    # ?search= matches student name OR course name OR trainer name (case-insensitive
    # substring) — mirrors EnrollmentsPage.jsx's search box, now run server-side so it
    # covers every enrollment, not just whichever page happens to be loaded.
    filter_backends = [filters.SearchFilter]
    search_fields = ['student__name', 'course__name', 'trainer__name']
    # No DELETE — enrollments are only ever withdrawn (see withdraw below), never
    # hard-deleted, so their attendance/payment history can never be lost.
    http_method_names = ['get', 'post', 'put', 'patch', 'head', 'options']

    def get_permissions(self):
        if self.action in ('report', 'certificate'):
            return [IsAdminOrTrainer()]
        return super().get_permissions()

    def get_queryset(self):
        qs = super().get_queryset()
        trainer_id = self.request.query_params.get('trainer')
        if trainer_id:
            qs = qs.filter(trainer_id=trainer_id)
        return qs

    @action(detail=True, methods=['post'])
    def transfer(self, request, pk=None):
        """Reassign an ongoing enrollment to a different trainer, going forward.

        Past Attendance records keep their original `marked_by` trainer so
        historical payouts stay correct — only the enrollment's trainer changes.
        """
        enrollment = self.get_object()
        if enrollment.status != 'ongoing':
            return Response(
                {'detail': 'Only ongoing enrollments can be transferred.'}, status=status.HTTP_400_BAD_REQUEST
            )

        trainer = Trainer.objects.filter(id=request.data.get('trainer'), status='active').first()
        if trainer is None:
            return Response({'detail': 'Select an active trainer.'}, status=status.HTTP_400_BAD_REQUEST)
        if trainer.id == enrollment.trainer_id:
            return Response(
                {'detail': 'Student is already assigned to this trainer.'}, status=status.HTTP_400_BAD_REQUEST
            )
        if not trainer.has_rate_for(enrollment.course):
            return Response(
                {'detail': f'{trainer.name} has no rate set for {enrollment.course.name} — set a default rate or add a course override first.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        conflict = find_schedule_conflict(
            trainer, enrollment.class_time, enrollment.class_days, exclude_enrollment_id=enrollment.id,
        )
        if conflict is not None:
            return Response(
                {'detail': f'{trainer.name} already has a class at that time — {conflict.student.name} ({conflict.course.name}). Choose a different trainer.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        previous_trainer_name = enrollment.trainer.name
        enrollment.trainer = trainer
        enrollment.save(update_fields=['trainer'])
        log_action(
            request.user, 'enrollment_transfer',
            f'{enrollment.student.name} — {enrollment.course.name}', f'{previous_trainer_name} → {trainer.name}',
        )
        return Response(self.get_serializer(enrollment).data)

    @action(detail=True, methods=['post'])
    def withdraw(self, request, pk=None):
        """The student is leaving before finishing the course. Attendance
        already taken stays exactly as it is — those classes happened and
        were already billed, so nothing about them gets undone. This just
        stops anything further: the enrollment can no longer take new
        classes, and for a B2C enrollment with a payment plan, any
        still-pending installments are cancelled (not deleted, so the
        original plan stays visible for the record) with an optional refund
        amount/note logged against it.
        """
        enrollment = self.get_object()
        if enrollment.status != 'ongoing':
            return Response(
                {'detail': 'Only ongoing enrollments can be withdrawn.'}, status=status.HTTP_400_BAD_REQUEST
            )

        refund_amount = request.data.get('refund_amount')
        refund_note = (request.data.get('refund_note') or '').strip()
        if refund_amount not in (None, ''):
            try:
                refund_amount = Decimal(str(refund_amount))
            except InvalidOperation:
                return Response({'detail': 'refund_amount must be a number.'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            refund_amount = None

        enrollment.status = 'withdrawn'
        enrollment.save(update_fields=['status'])

        detail = f'{enrollment.student.name} — {enrollment.course.name}'
        plan = getattr(enrollment, 'payment_plan', None)
        if plan is not None:
            cancelled = plan.installments.filter(paid_status='pending').update(paid_status='cancelled')
            if refund_amount is not None:
                plan.refunded_amount = refund_amount
                plan.refund_note = refund_note
                plan.save(update_fields=['refunded_amount', 'refund_note'])
                detail += f' — refunded ₹{refund_amount}'
            if cancelled:
                detail += f' — {cancelled} pending installment(s) cancelled'

        log_action(request.user, 'enrollment_withdraw', detail, refund_note)
        return Response(self.get_serializer(enrollment).data)

    @action(detail=True, methods=['post'])
    def assign_substitute(self, request, pk=None):
        """Temporarily hand this enrollment's classes to a different trainer
        for a date range — for a short absence, not a permanent handoff (see
        `transfer` for that). See SubstituteAssignment.
        """
        enrollment = self.get_object()
        if enrollment.status != 'ongoing':
            return Response(
                {'detail': 'Only ongoing enrollments can have a substitute assigned.'}, status=status.HTTP_400_BAD_REQUEST
            )

        substitute = Trainer.objects.filter(id=request.data.get('trainer'), status='active').first()
        if substitute is None:
            return Response({'detail': 'Select an active trainer.'}, status=status.HTTP_400_BAD_REQUEST)
        if substitute.id == enrollment.trainer_id:
            return Response(
                {'detail': 'This trainer already teaches this enrollment.'}, status=status.HTTP_400_BAD_REQUEST
            )
        if not substitute.has_rate_for(enrollment.course):
            return Response(
                {'detail': f'{substitute.name} has no rate set for {enrollment.course.name} — set a default rate or add a course override first.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        start_date = request.data.get('start_date')
        end_date = request.data.get('end_date')
        if not start_date or not end_date:
            return Response({'detail': 'start_date and end_date are required.'}, status=status.HTTP_400_BAD_REQUEST)
        if end_date < start_date:
            return Response({'detail': 'end_date cannot be before start_date.'}, status=status.HTTP_400_BAD_REQUEST)

        conflict = find_schedule_conflict(
            substitute, enrollment.class_time, enrollment.class_days,
            exclude_enrollment_id=enrollment.id, date_range=(start_date, end_date),
        )
        if conflict is not None:
            return Response(
                {'detail': f'{substitute.name} already has a class at that time — {conflict.student.name} ({conflict.course.name}). Choose a different trainer or time.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        assignment = SubstituteAssignment.objects.create(
            enrollment=enrollment, substitute_trainer=substitute,
            start_date=start_date, end_date=end_date, created_by=request.user,
        )
        log_action(
            request.user, 'substitute_assign',
            f'{enrollment.student.name} — {enrollment.course.name}',
            f'{substitute.name} covering {start_date} to {end_date}',
        )
        return Response(SubstituteAssignmentSerializer(assignment).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'])
    def report(self, request, pk=None):
        enrollment = self.get_object()
        if not request.user.is_staff and enrollment.trainer_id != request.user.trainer.id:
            raise PermissionDenied('You can only download reports for your own students.')

        pdf_bytes = render_student_report_pdf(enrollment)
        slug = re.sub(r'[^A-Za-z0-9]+', '-', enrollment.student.name).strip('-').lower()
        filename = f'student-report-{slug}-batch{enrollment.batch_number}.pdf'

        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response

    @action(detail=True, methods=['get'])
    def certificate(self, request, pk=None):
        enrollment = self.get_object()
        if not request.user.is_staff and enrollment.trainer_id != request.user.trainer.id:
            raise PermissionDenied('You can only download certificates for your own students.')
        if enrollment.status != 'completed':
            return Response(
                {'detail': 'A certificate is only available once this enrollment is completed.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        pdf_bytes = render_certificate_pdf(enrollment)
        slug = re.sub(r'[^A-Za-z0-9]+', '-', enrollment.student.name).strip('-').lower()
        filename = f'certificate-{slug}-{enrollment.course.name.lower().replace(" ", "-")}.pdf'

        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response


class PaymentInstallmentViewSet(ModelViewSet):
    queryset = PaymentInstallment.objects.select_related('plan__enrollment')
    serializer_class = PaymentInstallmentSerializer
    permission_classes = [IsAdmin]
    http_method_names = ['get', 'post', 'head', 'options']

    def create(self, request, *args, **kwargs):
        # Installments are only ever built by create_payment_plan() when an enrollment
        # is created — PaymentInstallmentSerializer has no writable 'plan' field, so a
        # raw POST here would only ever fail with an IntegrityError. 'post' stays in
        # http_method_names for the mark_paid/revoke actions below.
        raise MethodNotAllowed('POST')

    @action(detail=True, methods=['post'])
    def mark_paid(self, request, pk=None):
        installment = self.get_object()
        installment.paid_status = 'paid'
        installment.paid_date = date.today()
        installment.save(update_fields=['paid_status', 'paid_date'])
        enrollment = installment.plan.enrollment
        log_action(
            request.user, 'installment_mark_paid',
            f'{enrollment.student.name} — installment #{installment.sequence}', f'₹{installment.amount}',
        )
        return Response(PaymentInstallmentSerializer(installment).data)

    @action(detail=True, methods=['post'])
    def revoke(self, request, pk=None):
        """Undo a mistaken mark_paid — back to pending, no paid_date."""
        installment = self.get_object()
        installment.paid_status = 'pending'
        installment.paid_date = None
        installment.save(update_fields=['paid_status', 'paid_date'])
        enrollment = installment.plan.enrollment
        log_action(
            request.user, 'installment_revoke',
            f'{enrollment.student.name} — installment #{installment.sequence}', f'₹{installment.amount}',
        )
        return Response(PaymentInstallmentSerializer(installment).data)


class SubstituteAssignmentViewSet(ModelViewSet):
    """Admin-facing: create goes through EnrollmentViewSet.assign_substitute
    (needs the conflict check tied to a specific enrollment) — this ViewSet is
    for listing current/upcoming coverage and cancelling one early (DELETE)
    if the original trainer comes back sooner than planned.
    """

    queryset = SubstituteAssignment.objects.select_related(
        'enrollment__student', 'enrollment__course', 'enrollment__trainer', 'substitute_trainer'
    ).order_by('-start_date')
    serializer_class = SubstituteAssignmentSerializer
    permission_classes = [IsAdmin]
    http_method_names = ['get', 'delete', 'head', 'options']

    def get_queryset(self):
        qs = super().get_queryset()
        enrollment_id = self.request.query_params.get('enrollment')
        if enrollment_id:
            qs = qs.filter(enrollment_id=enrollment_id)
        return qs

    def perform_destroy(self, instance):
        log_action(
            self.request.user, 'substitute_cancel',
            f'{instance.enrollment.student.name} — {instance.enrollment.course.name}',
            f'{instance.substitute_trainer.name} — was covering {instance.start_date} to {instance.end_date}',
        )
        instance.delete()


class MyStudentsView(ListAPIView):
    """Trainer-facing: their own allocated enrollments, plus anything they're
    currently covering as a substitute (see SubstituteAssignment) — those get
    a `covering_for` name so the frontend can label them distinctly.

    Excludes archived students entirely — this is the single shared source for
    My Students, the trainer dashboard's weekly schedule, and the attendance-
    marking picker, so filtering here removes an archived student from all
    three at once. A student can only be archived once none of their
    enrollments are ongoing (see StudentViewSet.archive), so this only ever
    hides already-completed/withdrawn batches from a trainer's own view — see
    StudentViewSet.profile() for the matching block on viewing their profile
    page directly.

    B2C enrollments with a payment plan are additionally gated on payment status —
    see trainer_payment_gate(). An enrollment whose first payment hasn't been
    recorded yet is left out entirely; one that's fallen behind on a later
    installment stays listed (name still visible) but with its schedule blanked out
    and `payment_blocked: true` so the frontend hides it from the weekly grid,
    today's classes, and the attendance-marking picker.
    """

    serializer_class = EnrollmentSerializer
    permission_classes = [IsTrainer]

    def _active_substitute_map(self):
        today = timezone.localdate()
        return {
            assignment.enrollment_id: assignment
            for assignment in SubstituteAssignment.objects.filter(
                substitute_trainer=self.request.user.trainer, start_date__lte=today, end_date__gte=today,
            ).select_related('enrollment__trainer')
        }

    def get_queryset(self):
        substitute_enrollment_ids = self._active_substitute_map().keys()
        return (
            Enrollment.objects.select_related('student', 'course', 'trainer', 'payment_plan')
            .prefetch_related('payment_plan__installments')
            .filter(Q(trainer=self.request.user.trainer) | Q(id__in=substitute_enrollment_ids))
            .exclude(student__status='archived')
            .order_by('-start_date')
        )

    def list(self, request, *args, **kwargs):
        substitute_map = self._active_substitute_map()
        data = []
        for enrollment in self.get_queryset():
            gate = trainer_payment_gate(enrollment)
            if gate == 'hidden':
                continue
            row = self.get_serializer(enrollment).data
            row['payment_blocked'] = gate == 'blocked'
            if gate == 'blocked':
                row['class_time'] = None
                row['class_days'] = ''
            if enrollment.id in substitute_map:
                assignment = substitute_map[enrollment.id]
                row['covering_for'] = assignment.enrollment.trainer.name
                row['covering_until'] = assignment.end_date
            data.append(row)
        return Response(data)
