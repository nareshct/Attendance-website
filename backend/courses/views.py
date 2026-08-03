from django.http import FileResponse
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.viewsets import ModelViewSet

from config.permissions import IsAdmin, IsAdminOrTrainer

from .models import Course, CourseMaterial
from .serializers import CourseMaterialSerializer, CourseSerializer


class CourseViewSet(ModelViewSet):
    queryset = Course.objects.all().order_by('name')
    serializer_class = CourseSerializer
    # No DELETE — courses are referenced by enrollments/payment plans and are never
    # hard-deleted.
    http_method_names = ['get', 'post', 'put', 'patch', 'head', 'options']

    def get_permissions(self):
        # Trainers need to read the course list (e.g. to filter Course Materials by
        # course) — only creating/editing a course is admin-only.
        if self.action in ('list', 'retrieve'):
            return [IsAdminOrTrainer()]
        return [IsAdmin()]


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
            qs = qs.filter(course_id=course_id)
        return qs

    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        material = self.get_object()
        filename = material.file.name.rsplit('/', 1)[-1]
        return FileResponse(material.file.open('rb'), as_attachment=True, filename=filename)
