from django.contrib import admin

from .models import Attendance


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ('enrollment', 'date', 'status', 'marked_by')
    list_filter = ('status', 'date', 'marked_by')
    search_fields = ('enrollment__student__name', 'topic_covered')
    date_hierarchy = 'date'
