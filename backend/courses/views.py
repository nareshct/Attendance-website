from django.http import FileResponse
from rest_framework import filters
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.viewsets import ModelViewSet

from config.permissions import IsAdmin, IsAdminOrTrainer

from .models import Course, CourseMaterial
from .serializers import CourseMaterialSerializer, CourseSerializer, TrainerCourseSerializer


class CourseViewSet(ModelViewSet):
    queryset = Course.objects.all().order_by('name')
    serializer_class = CourseSerializer
    # ?search= matches course name (case-insensitive substring) — same server-side search
    # pattern as TrainerViewSet/StudentViewSet, used by async-search course pickers (see
    # SearchableSelect). The course catalog itself is small enough that this is mostly
    # for consistency rather than a real scaling need.
    filter_backends = [filters.SearchFilter]
    search_fields = ['name']
    # No DELETE — courses are referenced by enrollments/payment plans and are never
    # hard-deleted.
    http_method_names = ['get', 'post', 'put', 'patch', 'head', 'options']

    def get_permissions(self):
        # Trainers need to read the course list (e.g. to filter Course Materials by
        # course) — only creating/editing a course is admin-only.
        if self.action in ('list', 'retrieve'):
            return [IsAdminOrTrainer()]
        return [IsAdmin()]

    def get_serializer_class(self):
        # rate_per_class is the B2C price list — billing data a trainer has no reason
        # to see, even though they need list/retrieve access for the Course Materials
        # filter. See TrainerCourseSerializer.
        if self.action in ('list', 'retrieve') and not self.request.user.is_staff:
            return TrainerCourseSerializer
        return CourseSerializer


class CourseMaterialViewSet(ModelViewSet):
    serializer_class = CourseMaterialSerializer
    parser_classes = [MultiPartParser, FormParser]

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy'):
            return [IsAdmin()]
        return [IsAdminOrTrainer()]

    def get_queryset(self):
        qs = CourseMaterial.objects.select_related('course').order_by('course__name', '-uploaded_at')
        course_id = self.request.query_params.get('course')
        if course_id:
            if not course_id.isdigit():
                raise ValidationError({'course': 'Invalid course filter.'})
            qs = qs.filter(course_id=course_id)

        # Unlike CourseViewSet (course *names* aren't sensitive, so that stays
        # unscoped for the filter dropdown — see its get_permissions comment),
        # materials are real teaching content, so a trainer only gets courses
        # they actually have some current tie to: their own 1:1 enrollments,
        # batches they're on (trainer_names is free text, not a relation — see
        # batch_ids_for_trainer), or a course they're currently substitute-covering.
        user = self.request.user
        if not user.is_staff:
            from django.utils import timezone

            from batches.models import Batch
            from batches.services import batch_ids_for_trainer
            from enrollments.models import Enrollment, SubstituteAssignment

            trainer = user.trainer
            today = timezone.localdate()
            allowed_course_ids = set(
                Enrollment.objects.filter(trainer=trainer).values_list('course_id', flat=True)
            ) | set(
                SubstituteAssignment.objects.filter(
                    substitute_trainer=trainer, start_date__lte=today, end_date__gte=today,
                ).values_list('enrollment__course_id', flat=True)
            ) | set(
                Batch.objects.filter(id__in=batch_ids_for_trainer(trainer.name)).values_list('course_id', flat=True)
            )
            qs = qs.filter(course_id__in=allowed_course_ids)
        return qs

    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        material = self.get_object()
        filename = material.file.name.rsplit('/', 1)[-1]
        return FileResponse(material.file.open('rb'), as_attachment=True, filename=filename)
