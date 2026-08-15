import re
import uuid

from django.conf import settings
from django.db.models import Q
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import filters, serializers
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from audit.services import log_action
from batches.models import BatchEnrollment
from batches.serializers import BatchInstallmentSerializer
from config.permissions import IsAdmin, IsAdminOrTrainer
from config.throttling import ParentLinkRateThrottle
from enrollments.certificate_pdf import render_certificate_pdf
from enrollments.models import Enrollment, PaymentInstallment, SubstituteAssignment
from enrollments.serializers import PaymentPlanSerializer
from enrollments.services import trainer_payment_gate

from .models import ParentShareLink, Student
from .serializers import StudentSerializer


def _parent_link_payload(link):
    return {
        'token': str(link.token),
        'revoked': link.revoked,
        'url': f'{settings.FRONTEND_URL}/parent/{link.token}',
    }


class ParentPaymentPlanSerializer(PaymentPlanSerializer):
    """Same fields as PaymentPlanSerializer minus refund_note — that's free text an
    admin types when withdrawing a student (see EnrollmentsPage.jsx / BatchDetailPage.jsx
    withdraw forms), meant for internal record-keeping, not for the public, unauthenticated
    parent share link. Used only by ParentShareView below; the admin-facing
    EnrollmentHistoryWithPaymentSerializer still uses the unrestricted PaymentPlanSerializer.
    """

    class Meta(PaymentPlanSerializer.Meta):
        fields = [f for f in PaymentPlanSerializer.Meta.fields if f != 'refund_note']


class EnrollmentHistorySerializer(serializers.ModelSerializer):
    course_name = serializers.CharField(source='course.name', read_only=True)
    trainer_name = serializers.CharField(source='trainer.name', read_only=True)

    class Meta:
        model = Enrollment
        fields = [
            'id', 'course', 'course_name', 'trainer', 'trainer_name', 'batch_number',
            'classes_completed', 'classes_total', 'start_date', 'status', 'class_time', 'class_days',
        ]


class EnrollmentHistoryWithPaymentSerializer(EnrollmentHistorySerializer):
    """Admin-only variant of EnrollmentHistorySerializer — adds the B2C payment plan.
    Never used for the trainer-facing branch of profile(), same as client/pending_amount
    billing info is withheld from trainers elsewhere in the app.
    """

    payment_plan = serializers.SerializerMethodField()

    class Meta(EnrollmentHistorySerializer.Meta):
        fields = EnrollmentHistorySerializer.Meta.fields + ['payment_plan']

    def get_payment_plan(self, obj):
        plan = getattr(obj, 'payment_plan', None)
        return PaymentPlanSerializer(plan).data if plan else None


class StudentBatchEnrollmentSerializer(serializers.ModelSerializer):
    """Admin-only: a student's group-batch (see batches app) memberships, shown
    alongside their 1:1 course enrollments on the profile page — a student can be in
    both at once, and batches are otherwise only browsable from the Batches list."""

    batch_name = serializers.CharField(source='batch.name', read_only=True)
    course_name = serializers.CharField(source='batch.course.name', read_only=True)
    installments = BatchInstallmentSerializer(many=True, read_only=True)

    class Meta:
        model = BatchEnrollment
        fields = [
            'id', 'batch', 'batch_name', 'course_name', 'status', 'joined_date',
            'refunded_amount', 'refund_note', 'installments',
        ]


class StudentViewSet(ModelViewSet):
    # select_related('client') because StudentSerializer.client_name traverses
    # student.client.company_name — without it, listing B2B students triggers one extra
    # query per row (confirmed via reports/scale_audit.py: 44 queries for a 100-row page).
    queryset = Student.objects.select_related('client').order_by('name')
    serializer_class = StudentSerializer
    # ?search= matches against name OR student_id (case-insensitive substring) — mirrors
    # what StudentsPage.jsx's search box used to do client-side over just the loaded
    # page; searching server-side instead means it covers every student, not just
    # whichever page happens to be loaded.
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'student_id']
    # No DELETE — students are only ever archived (see archive/unarchive below), never
    # hard-deleted, so their enrollment/attendance/payment history can never be lost.
    http_method_names = ['get', 'post', 'put', 'patch', 'head', 'options']

    def get_queryset(self):
        qs = super().get_queryset()
        client_id = self.request.query_params.get('client')
        if client_id:
            if not client_id.isdigit():
                raise serializers.ValidationError({'client': 'Invalid client filter.'})
            qs = qs.filter(client_id=client_id)
        status_param = self.request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param)
        return qs

    def get_permissions(self):
        if self.action == 'profile':
            return [IsAdminOrTrainer()]
        return [IsAdmin()]

    @action(detail=True, methods=['get'], url_path='archive-blockers')
    def archive_blockers(self, request, pk=None):
        """Feeds the Archive confirmation dialog. `ongoing_enrollments` and
        `active_batch_enrollments` both hard-block archiving (see archive() below) —
        a student can't be archived while still taking classes, whether that's a 1:1
        Enrollment or a group Batch (see the batches app), mirroring
        TrainerViewSet.archive. `pending_installments` is informational only, not a
        blocker: withdrawing an ongoing enrollment already auto-cancels any pending
        installment tied to it (see EnrollmentViewSet.withdraw), so this only ever
        lists installments on a non-ongoing (already completed) enrollment — nothing
        left to withdraw would resolve them."""
        student = self.get_object()
        ongoing_enrollments = student.enrollments.filter(status='ongoing').select_related('course', 'trainer').order_by('course__name')
        active_batch_enrollments = (
            student.batch_enrollments.filter(status='active').select_related('batch__course').order_by('batch__name')
        )
        pending_installments = PaymentInstallment.objects.filter(
            plan__enrollment__student=student, paid_status='pending',
        ).select_related('plan__enrollment__course').order_by('plan__enrollment__course__name', 'sequence')
        return Response({
            'ongoing_enrollments': [
                {
                    'id': e.id,
                    'course_name': e.course.name,
                    'trainer_name': e.trainer.name,
                    'batch_number': e.batch_number,
                }
                for e in ongoing_enrollments
            ],
            'active_batch_enrollments': [
                {
                    'id': be.id,
                    'batch_name': be.batch.name,
                    'course_name': be.batch.course.name,
                }
                for be in active_batch_enrollments
            ],
            'pending_installments': [
                {
                    'id': i.id,
                    'course_name': i.plan.enrollment.course.name,
                    'sequence': i.sequence,
                    'amount': i.amount,
                    'due_at_classes': i.due_at_classes,
                }
                for i in pending_installments
            ],
        })

    @action(detail=True, methods=['post'])
    def archive(self, request, pk=None):
        student = self.get_object()
        if student.enrollments.filter(status='ongoing').exists():
            return Response(
                {'detail': 'This student still has ongoing batches — withdraw them first.'}, status=400,
            )
        if student.batch_enrollments.filter(status='active').exists():
            return Response(
                {'detail': 'This student is still active in a batch — withdraw them first.'}, status=400,
            )
        student.status = 'archived'
        student.save(update_fields=['status'])
        log_action(request.user, 'student_archive', student.name)
        return Response(StudentSerializer(student).data)

    @action(detail=True, methods=['post'])
    def unarchive(self, request, pk=None):
        student = self.get_object()
        student.status = 'active'
        student.save(update_fields=['status'])
        log_action(request.user, 'student_unarchive', student.name)
        return Response(StudentSerializer(student).data)

    @action(detail=True, methods=['get', 'post'])
    def parent_link(self, request, pk=None):
        """Fetch (or create, on first call) this student's parent share link.
        Idempotent — repeated calls return the same token until it's
        regenerated or revoked. See ParentShareLink.
        """
        student = self.get_object()
        link, created = ParentShareLink.objects.get_or_create(student=student)
        if created:
            log_action(request.user, 'parent_link_create', student.name)
        return Response(_parent_link_payload(link))

    @action(detail=True, methods=['post'])
    def regenerate_parent_link(self, request, pk=None):
        """Swap in a fresh token, invalidating any link already sent out.

        Updates the existing row in place rather than delete-then-create — `student`
        is a OneToOneField, so two near-simultaneous regenerate clicks racing a
        delete+create would have one of them hit the unique constraint and 500
        instead of cleanly regenerating. A single UPDATE (or INSERT via
        get_or_create if none exists yet) has no such race.
        """
        student = self.get_object()
        link, _ = ParentShareLink.objects.get_or_create(student=student)
        link.token = uuid.uuid4()
        link.revoked = False
        link.save(update_fields=['token', 'revoked'])
        log_action(request.user, 'parent_link_regenerate', student.name)
        return Response(_parent_link_payload(link))

    @action(detail=True, methods=['post'])
    def revoke_parent_link(self, request, pk=None):
        student = self.get_object()
        link = ParentShareLink.objects.filter(student=student).first()
        if link is None:
            return Response({'detail': 'No link exists for this student yet.'}, status=400)
        link.revoked = True
        link.save(update_fields=['revoked'])
        log_action(request.user, 'parent_link_revoke', student.name)
        return Response(_parent_link_payload(link))

    @action(detail=True, methods=['get'])
    def profile(self, request, pk=None):
        student = self.get_object()
        enrollments = (
            student.enrollments.select_related('course', 'trainer', 'payment_plan')
            .prefetch_related('payment_plan__installments')
            .order_by('-start_date')
        )

        user = request.user
        if not user.is_staff:
            # Unlike MyStudentsView (which still lists an archived student's
            # completed batches — see its docstring), the profile page itself
            # stays fully blocked for an archived student: nothing links to it
            # from that completed-batches row (plain text, not a link), so
            # there's no legitimate path here besides a stale bookmark/URL.
            if student.status == 'archived':
                return Response({'detail': 'Not found.'}, status=404)
            today = timezone.localdate()
            substitute_enrollment_ids = SubstituteAssignment.objects.filter(
                substitute_trainer=user.trainer, start_date__lte=today, end_date__gte=today,
            ).values_list('enrollment_id', flat=True)
            enrollments = enrollments.filter(
                Q(trainer=user.trainer) | Q(id__in=substitute_enrollment_ids)
            )
            visible = [(e, trainer_payment_gate(e)) for e in enrollments]
            visible = [(e, gate) for e, gate in visible if gate != 'hidden']
            if not visible:
                return Response({'detail': 'Not found.'}, status=404)
            data = {
                'id': student.id,
                'student_id': student.student_id,
                'name': student.name,
                'grade': student.grade,
                'place': student.place,
                'parent_name': student.parent_name,
                'status': student.status,
            }
            rows = []
            for e, gate in visible:
                row = EnrollmentHistorySerializer(e).data
                row['payment_blocked'] = gate == 'blocked'
                if gate == 'blocked':
                    row['class_time'] = None
                    row['class_days'] = ''
                rows.append(row)
            data['enrollments'] = rows
            return Response(data)

        data = StudentSerializer(student).data
        data['enrollments'] = EnrollmentHistoryWithPaymentSerializer(enrollments, many=True).data
        batch_enrollments = (
            student.batch_enrollments.select_related('batch__course').prefetch_related('installments')
            .order_by('-joined_date')
        )
        data['batch_enrollments'] = StudentBatchEnrollmentSerializer(batch_enrollments, many=True).data
        return Response(data)


class ParentShareView(APIView):
    """Public, unauthenticated: a parent's read-only view of their child's
    schedule, progress, and (for B2C) payment plan — reachable only by
    knowing the exact token from ParentShareLink, no login. Deliberately a
    much narrower payload than the admin/trainer profile views: no rates, no
    client info, no other students, no internal IDs beyond the student's own
    public-facing student_id.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ParentLinkRateThrottle]

    def get(self, request, token):
        link = ParentShareLink.objects.filter(token=token, revoked=False).select_related('student').first()
        if link is None:
            return Response({'detail': 'This link is invalid or has been revoked.'}, status=404)

        student = link.student
        enrollments = (
            student.enrollments.select_related('course', 'trainer', 'payment_plan')
            .prefetch_related('payment_plan__installments', 'attendance_records')
            .order_by('-start_date')
        )

        rows = []
        for e in enrollments:
            row = {
                'id': e.id,
                'course_name': e.course.name,
                'trainer_name': e.trainer.name,
                'batch_number': e.batch_number,
                'classes_completed': e.classes_completed,
                'classes_total': e.classes_total,
                'status': e.status,
                'class_time': e.class_time,
                'class_days': e.class_days,
                'recent_classes': [
                    {'date': a.date, 'topic_covered': a.topic_covered}
                    for a in e.attendance_records.filter(status='present').order_by('-date')
                ],
            }
            plan = getattr(e, 'payment_plan', None)
            if plan is not None:
                row['payment_plan'] = ParentPaymentPlanSerializer(plan).data
            rows.append(row)

        return Response({
            'student_id': student.student_id,
            'name': student.name,
            'grade': student.grade,
            'enrollments': rows,
        })


class ParentCertificateView(APIView):
    """Public, unauthenticated: lets a parent download their child's
    completion certificate directly from the same share link used for
    ParentShareView — no separate login, no separate link to send. Only
    works for an enrollment that belongs to that exact student and has
    actually reached 'completed'.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ParentLinkRateThrottle]

    def get(self, request, token, enrollment_id):
        link = ParentShareLink.objects.filter(token=token, revoked=False).select_related('student').first()
        if link is None:
            return Response({'detail': 'This link is invalid or has been revoked.'}, status=404)

        enrollment = Enrollment.objects.filter(
            id=enrollment_id, student=link.student, status='completed'
        ).select_related('student__client', 'course', 'trainer').first()
        if enrollment is None:
            return Response({'detail': 'A certificate is not available for this enrollment.'}, status=404)

        pdf_bytes = render_certificate_pdf(enrollment)
        slug = re.sub(r'[^A-Za-z0-9]+', '-', enrollment.student.name).strip('-').lower()
        filename = f'certificate-{slug}-{enrollment.course.name.lower().replace(" ", "-")}.pdf'

        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
