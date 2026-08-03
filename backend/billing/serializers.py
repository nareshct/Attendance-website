from decimal import Decimal

from django.db.models import Sum
from rest_framework import serializers

from .models import BillingCycle, ClientInvoice, ClientInvoiceAdjustment, Payout, PayoutAdjustment


class BillingCycleSerializer(serializers.ModelSerializer):
    class Meta:
        model = BillingCycle
        fields = ['id', 'cycle_start', 'cycle_end', 'status']
        read_only_fields = ['status']


class PayoutSerializer(serializers.ModelSerializer):
    trainer_name = serializers.CharField(source='trainer.name', read_only=True)
    cycle_start = serializers.DateField(source='cycle.cycle_start', read_only=True)
    cycle_end = serializers.DateField(source='cycle.cycle_end', read_only=True)
    carried_forward_amount = serializers.SerializerMethodField()

    class Meta:
        model = Payout
        fields = [
            'id', 'trainer', 'trainer_name', 'cycle', 'cycle_start', 'cycle_end',
            'total_classes', 'total_amount', 'paid_status', 'carried_forward_amount',
        ]
        read_only_fields = ['trainer', 'cycle', 'total_classes', 'total_amount']

    def get_carried_forward_amount(self, obj):
        """How much of this payout's amount was carried forward from a late-approved
        class in an earlier, already-paid cycle (rather than earned in this cycle).

        Prefers the queryset annotation (see billing.services.payouts_with_carried_forward,
        used by PayoutViewSet/MyEarningsView) when present, to avoid a query per row on a
        list endpoint — falls back to a live query for a single already-fetched instance
        that wasn't annotated (e.g. PayoutViewSet.mark_paid()).
        """
        annotated = getattr(obj, 'carried_forward_amount_annotated', None)
        if annotated is not None:
            return annotated
        total = PayoutAdjustment.objects.filter(
            trainer=obj.trainer, applied_cycle=obj.cycle,
        ).aggregate(total=Sum('amount'))['total']
        return total or Decimal('0.00')


class ClientInvoiceSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source='client.company_name', read_only=True)
    cycle_start = serializers.DateField(source='cycle.cycle_start', read_only=True)
    cycle_end = serializers.DateField(source='cycle.cycle_end', read_only=True)
    due_date = serializers.ReadOnlyField()
    is_overdue = serializers.ReadOnlyField()
    days_overdue = serializers.ReadOnlyField()
    carried_forward_amount = serializers.SerializerMethodField()

    class Meta:
        model = ClientInvoice
        fields = [
            'id', 'client', 'client_name', 'cycle', 'cycle_start', 'cycle_end',
            'total_classes', 'total_amount', 'status', 'due_date', 'is_overdue', 'days_overdue',
            'carried_forward_amount',
        ]
        read_only_fields = ['client', 'cycle', 'total_classes', 'total_amount']

    def get_carried_forward_amount(self, obj):
        """How much of this invoice's amount was carried forward from a late-approved
        class whose own cycle had already been invoiced to the client.

        Prefers the queryset annotation (see billing.services.client_invoices_with_carried_forward,
        used by ClientInvoiceViewSet) when present, to avoid a query per row on a list
        endpoint — falls back to a live query for a single already-fetched instance that
        wasn't annotated (e.g. ClientInvoiceViewSet.mark_received()).
        """
        annotated = getattr(obj, 'carried_forward_amount_annotated', None)
        if annotated is not None:
            return annotated
        total = ClientInvoiceAdjustment.objects.filter(
            client=obj.client, applied_cycle=obj.cycle,
        ).aggregate(total=Sum('amount'))['total']
        return total or Decimal('0.00')
