from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from .models import Client, ClientContact, ClientCourseRate


class ClientContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = ClientContact
        fields = ['id', 'client', 'name', 'role', 'phone', 'email']


class ClientCourseRateSerializer(serializers.ModelSerializer):
    course_name = serializers.CharField(source='course.name', read_only=True)

    class Meta:
        model = ClientCourseRate
        fields = ['id', 'client', 'course', 'course_name', 'rate_per_class']


class ClientSerializer(serializers.ModelSerializer):
    course_rates = ClientCourseRateSerializer(many=True, read_only=True)
    contacts = ClientContactSerializer(many=True, read_only=True)
    pending_amount = serializers.SerializerMethodField()
    # Annotated on ClientViewSet.get_queryset() — fall back to a live count for callers
    # that build a Client instance outside that queryset (e.g. serializer.save() in create()).
    active_student_count = serializers.SerializerMethodField()
    overdue_invoice_count = serializers.SerializerMethodField()
    # Tells the admin frontend which login-management UI to show — "Set up client
    # login" (no user yet) vs "Reset password" (one already exists). See
    # ClientViewSet.set_up_login/.reset_password.
    has_login = serializers.SerializerMethodField()
    # A multipart PATCH has no native way to send "clear this file field" (there's no
    # null in form-data) — this is the explicit signal for it instead. Mutually
    # exclusive with actually sending a new 'logo' file in the same request; see
    # update() below.
    remove_logo = serializers.BooleanField(write_only=True, required=False, default=False)

    class Meta:
        model = Client
        fields = [
            'id', 'company_name', 'contact_phone', 'contact_email', 'rate_per_class',
            'status', 'logo', 'tagline', 'remove_logo', 'course_rates', 'contacts', 'pending_amount',
            'active_student_count', 'overdue_invoice_count', 'has_login',
        ]
        read_only_fields = ['status']

    def create(self, validated_data):
        # remove_logo has a default, so it's always present in validated_data (even on
        # create, where there's nothing to remove yet) — not a real model field, so it
        # can't be passed through to Client.objects.create().
        validated_data.pop('remove_logo', None)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if validated_data.pop('remove_logo', False):
            # Only the DB reference is cleared, not the underlying file on disk — this
            # app doesn't clean up replaced/removed media files anywhere else either
            # (see CourseMaterial), so this stays consistent with that.
            instance.logo = None
            instance.save(update_fields=['logo'])
        return super().update(instance, validated_data)

    def get_pending_amount(self, obj):
        """Live current cycle billing so far + pending pay-ins from closed cycles.

        Same figure on every endpoint (list, retrieve, create response, ...) — always
        computed here rather than only patched on in ClientViewSet.list(). `obj.pending_amount`
        is the closed-cycle sum, annotated on ClientViewSet's queryset; falls back to 0
        if the instance wasn't queried through it (e.g. right after a create()).

        The child serializer instance is reused across every item in a `many=True`
        list, so `self.context` is shared across the whole pass — resolve the
        current cycle once and cache it there instead of once per client.
        """
        from billing.services import client_current_cycle_totals, get_or_create_cycle

        if 'current_cycle' not in self.context:
            cycle, _ = get_or_create_cycle()
            self.context['current_cycle'] = cycle

        closed_pending = getattr(obj, 'pending_amount', None) or Decimal('0.00')
        current = client_current_cycle_totals(obj, cycle=self.context['current_cycle'])
        return current['total_revenue'] + closed_pending

    def get_active_student_count(self, obj):
        if isinstance(getattr(obj, 'active_student_count', None), int):
            return obj.active_student_count
        return obj.students.filter(status='active').count()

    def get_overdue_invoice_count(self, obj):
        from billing.models import ClientInvoice

        if isinstance(getattr(obj, 'overdue_invoice_count', None), int):
            return obj.overdue_invoice_count
        cutoff = timezone.localdate() - timedelta(days=ClientInvoice.OVERDUE_GRACE_DAYS)
        return obj.invoices.filter(status='pending', cycle__cycle_end__lt=cutoff).count()

    def get_has_login(self, obj):
        return obj.user_id is not None
