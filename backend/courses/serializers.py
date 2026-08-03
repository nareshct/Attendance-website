from rest_framework import serializers

from .models import Course, CourseMaterial


class CourseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Course
        fields = ['id', 'name', 'total_classes', 'rate_per_class']


class CourseMaterialSerializer(serializers.ModelSerializer):
    course_name = serializers.CharField(source='course.name', read_only=True)
    file_name = serializers.SerializerMethodField()

    class Meta:
        model = CourseMaterial
        fields = ['id', 'course', 'course_name', 'title', 'description', 'file', 'file_name', 'uploaded_at']
        extra_kwargs = {'file': {'write_only': True}}

    def get_file_name(self, obj):
        return obj.file.name.rsplit('/', 1)[-1] if obj.file else None
