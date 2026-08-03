from django.contrib import admin

from .models import Trainer, TrainerCourseRate


class TrainerCourseRateInline(admin.TabularInline):
    model = TrainerCourseRate
    extra = 1


@admin.register(Trainer)
class TrainerAdmin(admin.ModelAdmin):
    list_display = ('trainer_id', 'name', 'phone_number', 'place', 'status')
    list_filter = ('status',)
    search_fields = ('trainer_id', 'name', 'phone_number')
    readonly_fields = ('trainer_id',)
    inlines = [TrainerCourseRateInline]


@admin.register(TrainerCourseRate)
class TrainerCourseRateAdmin(admin.ModelAdmin):
    list_display = ('trainer', 'course', 'rate_per_class')
    list_filter = ('course',)
