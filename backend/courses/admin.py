from django.contrib import admin

from .models import Course, CourseMaterial


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('name', 'total_classes')
    search_fields = ('name',)


@admin.register(CourseMaterial)
class CourseMaterialAdmin(admin.ModelAdmin):
    list_display = ('course', 'title', 'uploaded_at')
    list_filter = ('course',)
    search_fields = ('title', 'course__name')
