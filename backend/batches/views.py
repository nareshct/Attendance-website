import re
from datetime import date
from decimal import Decimal, InvalidOperation

from django.http import HttpResponse
from rest_framework import filters, status
from rest_framework.decorators import action
from rest_framework.generics import ListAPIView
from rest_framework.exceptions import MethodNotAllowed
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from audit.services import log_action
from config.permissions import IsAdmin, IsAdminOrTrainer, IsTrainer

from students.models import Student

from .models import Batch, BatchEnrollment, BatchInstallment, BatchPayout, BatchSession
from .serializers import (
    BatchEnrollmentSerializer,
    BatchInstallmentSerializer,
    BatchPayoutSerializer,
    BatchSerializer,
    BatchSessionSerializer,
    MyBatchSerializer,
)
from .services import (
    all_batches_summary,
    batch_ids_for_trainer,
    batch_revenue_summary,
    build_export_workbook,
    build_import_template,
    create_batch_installments,
    import_students_from_excel,
    source_report,
)


class BatchViewSet(ModelViewSet):
    queryset = Batch.objects.select_related('course').prefetch_related('payouts')
    serializer_class = BatchSerializer
    permission_classes = [IsAdmin]
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'course__name', 'trainer_names']
    # No DELETE — a batch is never hard-deleted once created (set status to cancelled
    # instead), so its enrollment/installment/session/payout history can never be lost.
    http_method_names = ['get', 'post', 'put', 'patch', 'head', 'options']

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Top-line stats for the Batches list page header."""
        return Response(all_batches_summary())

    @action(detail=True, methods=['get'])
    def revenue(self, request, pk=None):
        return Response(batch_revenue_summary(self.get_object()))

    @action(detail=False, methods=['get'])
    def source_breakdown(self, request):
        """Enrollment count + revenue by how each guest heard about the center —
        the ROI signal for comparing ad channels. See services.source_report."""
        return Response(source_report())

    @action(detail=True, methods=['get'])
    def export_students(self, request, pk=None):
        """.xlsx of this batch's current roster — the mirror of Excel import."""
        batch = self.get_object()
        buffer = build_export_workbook(batch)
        response = HttpResponse(
            buffer.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        safe_name = re.sub(r'[^A-Za-z0-9 _-]', '', batch.name).strip() or 'batch'
        response['Content-Disposition'] = f'attachment; filename="{safe_name} - students.xlsx"'
        return response

    def perform_destroy(self, instance):
        log_action(self.request.user, 'batch_delete', instance.name, f'{instance.batch_enrollments.count()} enrollment(s) removed')
        instance.delete()

    @action(detail=False, methods=['get'])
    def import_template(self, request):
        """A blank .xlsx with the exact headers bulk-import expects — a guide for
        renaming columns on a downloaded Google Form response sheet before uploading."""
        buffer = build_import_template()
        response = HttpResponse(
            buffer.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = 'attachment; filename="batch_import_template.xlsx"'
        return response

    @action(detail=True, methods=['post'], parser_classes=[MultiPartParser, FormParser])
    def import_students(self, request, pk=None):
        batch = self.get_object()
        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({'detail': 'Attach an Excel (.xlsx) file as "file".'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            summary = import_students_from_excel(batch, file_obj)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        log_action(
            request.user, 'batch_import_students', batch.name,
            f"{summary['enrolled']} enrolled, {summary['marked_paid']} marked paid, "
            f"{len(summary['skipped'])} skipped",
        )
        return Response(summary)


class MyBatchesView(ListAPIView):
    """Trainer-facing: batches where their name appears in the free-text trainer_names
    list (see Batch's docstring — trainer_names isn't a relation to the Trainer table,
    so this can't be a normal FK filter). Read-only; a trainer logs sessions and views
    their own payouts for these batches through BatchSessionViewSet/BatchPayoutViewSet."""

    serializer_class = MyBatchSerializer
    permission_classes = [IsTrainer]

    def get_queryset(self):
        ids = batch_ids_for_trainer(self.request.user.trainer.name)
        return Batch.objects.filter(id__in=ids).select_related('course').prefetch_related('payouts')


class BatchPayoutViewSet(ModelViewSet):
    """One agreed payout per person helping run a batch — see BatchPayout.
    Any number per batch, e.g. one per co-teaching trainer.

    Trainers get read-only access, scoped to payouts addressed to them by name —
    never another co-trainer's payout on the same batch."""

    queryset = BatchPayout.objects.select_related('batch')
    serializer_class = BatchPayoutSerializer
    http_method_names = ['get', 'post', 'delete', 'head', 'options']

    def get_permissions(self):
        if self.action in ('create', 'destroy', 'mark_paid'):
            return [IsAdmin()]
        return [IsAdminOrTrainer()]

    def get_queryset(self):
        qs = super().get_queryset()
        batch_id = self.request.query_params.get('batch')
        if batch_id:
            qs = qs.filter(batch_id=batch_id)
        if not self.request.user.is_staff:
            qs = qs.filter(recipient_name__iexact=self.request.user.trainer.name)
        return qs

    def perform_create(self, serializer):
        payout = serializer.save()
        log_action(
            self.request.user, 'batch_payout_create',
            f'{payout.batch.name} — {payout.recipient_name}', f'₹{payout.amount}',
        )

    @action(detail=True, methods=['post'])
    def mark_paid(self, request, pk=None):
        payout = self.get_object()
        payout.paid = True
        payout.paid_date = date.today()
        payout.save(update_fields=['paid', 'paid_date'])
        log_action(
            request.user, 'batch_payout_mark_paid',
            f'{payout.batch.name} — {payout.recipient_name}', f'₹{payout.amount}',
        )
        return Response(BatchPayoutSerializer(payout).data)


class BatchEnrollmentViewSet(ModelViewSet):
    queryset = BatchEnrollment.objects.select_related('batch', 'student').prefetch_related('installments')
    serializer_class = BatchEnrollmentSerializer
    permission_classes = [IsAdmin]
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']
    filter_backends = [filters.SearchFilter]
    search_fields = ['guest_name', 'student__name']

    def get_queryset(self):
        qs = super().get_queryset()
        batch_id = self.request.query_params.get('batch')
        if batch_id:
            qs = qs.filter(batch_id=batch_id)
        student_id = self.request.query_params.get('student')
        if student_id:
            qs = qs.filter(student_id=student_id)
        return qs

    def perform_update(self, serializer):
        enrollment = serializer.save()
        log_action(self.request.user, 'batch_enrollment_edit', f'{enrollment.display_name} — {enrollment.batch.name}', '')

    def perform_destroy(self, instance):
        log_action(self.request.user, 'batch_enrollment_delete', f'{instance.display_name} — {instance.batch.name}', '')
        instance.delete()

    def create(self, request, *args, **kwargs):
        batch_id = request.data.get('batch')
        student_id = request.data.get('student') or None
        guest_name = (request.data.get('guest_name') or '').strip()
        guest_phone = (request.data.get('guest_phone_number') or '').strip()

        batch = Batch.objects.filter(id=batch_id).first()
        if batch is None:
            return Response({'detail': 'Select a batch.'}, status=status.HTTP_400_BAD_REQUEST)
        if not batch.accepting_enrollments:
            return Response({'detail': 'This batch is closed to new enrollments.'}, status=status.HTTP_400_BAD_REQUEST)
        if not student_id and not guest_name:
            return Response(
                {'detail': 'Select an existing student, or enter a name for someone not in the system.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if student_id and guest_name:
            return Response(
                {'detail': 'Choose either an existing student or a new name — not both.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if student_id and BatchEnrollment.objects.filter(batch_id=batch_id, student_id=student_id).exists():
            return Response({'detail': 'This student is already enrolled in this batch.'}, status=status.HTTP_400_BAD_REQUEST)
        if guest_name and guest_phone:
            # Same name+phone dedup rule as the Excel import (see
            # services.import_students_from_excel) — a guest has no unique_together
            # guard to lean on since student=None, so this has to be checked explicitly.
            phone_digits = re.sub(r'\D', '', guest_phone)
            same_name_guests = BatchEnrollment.objects.filter(
                batch_id=batch_id, student__isnull=True, guest_name__iexact=guest_name,
            ).values_list('guest_phone_number', flat=True)
            if phone_digits and any(re.sub(r'\D', '', p) == phone_digits for p in same_name_guests):
                return Response(
                    {'detail': f'{guest_name} is already enrolled in this batch.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        serializer = self.get_serializer(data={
            'batch': batch_id,
            'student': student_id,
            'guest_name': guest_name,
            'guest_phone_number': guest_phone,
            'guest_email': request.data.get('guest_email', ''),
            'guest_occupation': request.data.get('guest_occupation', ''),
            'guest_source': request.data.get('guest_source', ''),
            'joined_date': date.today().isoformat(),
        })
        serializer.is_valid(raise_exception=True)
        enrollment = serializer.save(joined_date=date.today())
        create_batch_installments(enrollment)
        log_action(request.user, 'batch_enroll', f'{enrollment.display_name} — {batch.name}', f'₹{batch.fee_per_student}')
        return Response(BatchEnrollmentSerializer(enrollment).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def withdraw(self, request, pk=None):
        enrollment = self.get_object()

        refund_amount = Decimal('0')
        raw_refund = request.data.get('refund_amount')
        if raw_refund not in (None, ''):
            try:
                refund_amount = Decimal(str(raw_refund))
            except InvalidOperation:
                return Response({'detail': 'refund_amount must be a number.'}, status=status.HTTP_400_BAD_REQUEST)
            if refund_amount < 0:
                return Response({'detail': 'refund_amount cannot be negative.'}, status=status.HTTP_400_BAD_REQUEST)

        enrollment.status = 'withdrawn'
        update_fields = ['status']
        if refund_amount:
            enrollment.refunded_amount = refund_amount
            enrollment.refund_note = (request.data.get('refund_note') or '').strip()
            update_fields += ['refunded_amount', 'refund_note']
        enrollment.save(update_fields=update_fields)
        enrollment.installments.filter(paid_status='pending').update(paid_status='cancelled')

        detail = f'refunded ₹{refund_amount}' if refund_amount else ''
        log_action(request.user, 'batch_withdraw', f'{enrollment.display_name} — {enrollment.batch.name}', detail)
        return Response(BatchEnrollmentSerializer(enrollment).data)

    @action(detail=True, methods=['post'])
    def reactivate(self, request, pk=None):
        enrollment = self.get_object()
        enrollment.status = 'active'
        enrollment.save(update_fields=['status'])
        enrollment.installments.filter(paid_status='cancelled').update(paid_status='pending')
        log_action(request.user, 'batch_reactivate', f'{enrollment.display_name} — {enrollment.batch.name}', '')
        return Response(BatchEnrollmentSerializer(enrollment).data)

    @action(detail=True, methods=['post'])
    def convert_to_student(self, request, pk=None):
        """Register a guest enrollment as a full Student, using the details already
        captured at signup — for a guest who's stuck around and now needs a proper
        record (e.g. joining another batch, or 1-on-1 classes)."""
        enrollment = self.get_object()
        if enrollment.student_id is not None:
            return Response({'detail': 'This enrollment is already linked to a registered student.'}, status=status.HTTP_400_BAD_REQUEST)
        student = Student.objects.create(
            name=enrollment.guest_name, grade='', parent_phone_number=enrollment.guest_phone_number,
            source_type='B2C', client=None,
        )
        enrollment.student = student
        enrollment.save(update_fields=['student'])
        log_action(request.user, 'batch_convert_guest', f'{enrollment.guest_name} — {enrollment.batch.name}', f'now {student.student_id}')
        return Response(BatchEnrollmentSerializer(enrollment).data)


class BatchInstallmentViewSet(ModelViewSet):
    queryset = BatchInstallment.objects.select_related('batch_enrollment__batch', 'batch_enrollment__student')
    serializer_class = BatchInstallmentSerializer
    permission_classes = [IsAdmin]
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    def create(self, request, *args, **kwargs):
        # Installments are only ever built by create_batch_installments() when a student
        # enrolls in a batch — 'batch_enrollment' has no writable serializer field, so a
        # raw POST here would only ever fail with an IntegrityError. 'post' stays in
        # http_method_names for the mark_paid/revoke actions below.
        raise MethodNotAllowed('POST')

    def perform_update(self, serializer):
        old_amount = serializer.instance.amount
        installment = serializer.save()
        enrollment = installment.batch_enrollment
        log_action(
            self.request.user, 'batch_installment_amount_edit',
            f'{enrollment.display_name} — {enrollment.batch.name} — installment #{installment.sequence}',
            f'₹{old_amount} → ₹{installment.amount}',
        )

    @action(detail=True, methods=['post'])
    def mark_paid(self, request, pk=None):
        installment = self.get_object()
        installment.paid_status = 'paid'
        installment.paid_date = date.today()
        installment.save(update_fields=['paid_status', 'paid_date'])
        enrollment = installment.batch_enrollment
        log_action(
            request.user, 'batch_installment_mark_paid',
            f'{enrollment.display_name} — {enrollment.batch.name} — installment #{installment.sequence}',
            f'₹{installment.amount}',
        )
        return Response(BatchInstallmentSerializer(installment).data)

    @action(detail=True, methods=['post'])
    def revoke(self, request, pk=None):
        installment = self.get_object()
        installment.paid_status = 'pending'
        installment.paid_date = None
        installment.save(update_fields=['paid_status', 'paid_date'])
        return Response(BatchInstallmentSerializer(installment).data)


class BatchSessionViewSet(ModelViewSet):
    """Admins see/log sessions for any batch. A trainer can only see and log sessions
    for batches where their name is listed in trainer_names (see batch_ids_for_trainer)
    — not every batch in the system."""

    queryset = BatchSession.objects.select_related('batch')
    serializer_class = BatchSessionSerializer
    permission_classes = [IsAdminOrTrainer]

    def get_queryset(self):
        qs = super().get_queryset()
        batch_id = self.request.query_params.get('batch')
        if batch_id:
            qs = qs.filter(batch_id=batch_id)
        if not self.request.user.is_staff:
            qs = qs.filter(batch_id__in=batch_ids_for_trainer(self.request.user.trainer.name))
        return qs

    def create(self, request, *args, **kwargs):
        if not request.user.is_staff:
            batch_id = str(request.data.get('batch') or '')
            allowed_ids = batch_ids_for_trainer(request.user.trainer.name)
            if not batch_id.isdigit() or int(batch_id) not in allowed_ids:
                return Response(
                    {'detail': "You're not listed as a trainer on this batch."}, status=status.HTTP_403_FORBIDDEN,
                )
        return super().create(request, *args, **kwargs)
