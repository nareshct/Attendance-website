from django.contrib import admin

from .models import Enrollment


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ('student', 'course', 'trainer', 'batch_number', 'classes_completed', 'classes_total', 'status', 'start_date', 'class_days', 'class_time')
    list_filter = ('status', 'course', 'trainer')
    search_fields = ('student__name', 'student__student_id')
