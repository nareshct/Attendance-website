from django.contrib import admin

from .models import Student


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    list_display = ('student_id', 'name', 'grade', 'source_type', 'client', 'status', 'created_at')
    list_filter = ('source_type', 'status', 'grade')
    search_fields = ('student_id', 'name', 'parent_name', 'parent_phone_number')
    readonly_fields = ('student_id', 'created_at')
