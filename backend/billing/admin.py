from django.contrib import admin

from .models import BillingCycle, Payout


@admin.register(BillingCycle)
class BillingCycleAdmin(admin.ModelAdmin):
    list_display = ('cycle_start', 'cycle_end', 'status')
    list_filter = ('status',)


@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    list_display = ('trainer', 'cycle', 'total_classes', 'total_amount', 'paid_status')
    list_filter = ('paid_status', 'cycle')
    search_fields = ('trainer__name',)
