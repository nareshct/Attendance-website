from django.contrib import admin

from .models import Client


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('company_name', 'contact_phone', 'contact_email')
    search_fields = ('company_name', 'contact_phone', 'contact_email')
