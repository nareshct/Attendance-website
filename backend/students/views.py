import re

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
from config.permissions import IsAdmin, IsAdminOrTrainer
from enrollments.certificate_pdf import render_certificate_pdf
from enrollments.models import Enrollment, SubstituteAssignment
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
            qs = qs.filter(client_id=client_id)
        return qs

    def get_permissions(self):
        if self.action == 'profile':
            return [IsAdminOrTrainer()]
        return [IsAdmin()]

    @action(detail=True, methods=['post'])
    def archive(self, request, pk=None):
        student = self.get_object()
        student.status = 'archived'
        student.save(update_fields=['status'])
        return Response(StudentSerializer(student).data)

    @action(detail=True, methods=['post'])
    def unarchive(self, request, pk=None):
        student = self.get_object()
        student.status = 'active'
        student.save(update_fields=['status'])
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
        """Swap in a fresh token, invalidating any link already sent out."""
        student = self.get_object()
        ParentShareLink.objects.filter(student=student).delete()
        link = ParentShareLink.objects.create(student=student)
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
        enrollments = student.enrollments.select_related('course', 'trainer').order_by('-start_date')

        user = request.user
        if not user.is_staff:
            today = timezone.localdate()
            substitute_enrollment_ids = SubstituteAssignment.objects.filter(
                substitute_trainer=user.trainer, start_date__lte=today, end_date__gte=today,
            ).values_list('enrollment_id', flat=True)
            enrollments = enrollments.filter(
                Q(trainer=user.trainer) | Q(id__in=substitute_enrollment_ids)
            ).select_related('payment_plan').prefetch_related('payment_plan__installments')
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
                    for a in e.attendance_records.filter(status='present').order_by('-date')[:10]
                ],
            }
            plan = getattr(e, 'payment_plan', None)
            if plan is not None:
                row['payment_plan'] = PaymentPlanSerializer(plan).data
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

    def get(self, request, token, enrollment_id):
        link = ParentShareLink.objects.filter(token=token, revoked=False).select_related('student').first()
        if link is None:
            return Response({'detail': 'This link is invalid or has been revoked.'}, status=404)

        enrollment = Enrollment.objects.filter(
            id=enrollment_id, student=link.student, status='completed'
        ).select_related('student', 'course', 'trainer').first()
        if enrollment is None:
            return Response({'detail': 'A certificate is not available for this enrollment.'}, status=404)

        pdf_bytes = render_certificate_pdf(enrollment)
        slug = re.sub(r'[^A-Za-z0-9]+', '-', enrollment.student.name).strip('-').lower()
        filename = f'certificate-{slug}-{enrollment.course.name.lower().replace(" ", "-")}.pdf'

        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
