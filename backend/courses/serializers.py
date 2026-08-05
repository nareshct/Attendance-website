from rest_framework import serializers

from .models import Course, CourseMaterial


class CourseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Course
        fields = ['id', 'name', 'total_classes', 'rate_per_class']


class TrainerCourseSerializer(serializers.ModelSerializer):
    """Course list/detail as seen by a trainer — everything except rate_per_class
    (the B2C price list), which is billing data a trainer has no reason to see.
    Trainers only hit this endpoint to filter Course Materials by course."""

    class Meta:
        model = Course
        fields = ['id', 'name', 'total_classes']


class CourseMaterialSerializer(serializers.ModelSerializer):
    course_name = serializers.CharField(source='course.name', read_only=True)
    file_name = serializers.SerializerMethodField()

    class Meta:
        model = CourseMaterial
        fields = ['id', 'course', 'course_name', 'title', 'description', 'file', 'file_name', 'uploaded_at']
        extra_kwargs = {'file': {'write_only': True}}

    def get_file_name(self, obj):
        return obj.file.name.rsplit('/', 1)[-1] if obj.file else None
