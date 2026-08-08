import re

from django.db import transaction
from django.http import HttpResponse
from rest_framework.decorators import action
from rest_framework.generics import ListAPIView
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from audit.services import log_action
from config.permissions import IsAdmin, IsTrainer

from .invoice_pdf import render_invoice_pdf
from .models import BillingCycle, ClientInvoice, Payout
from .serializers import BillingCycleSerializer, ClientInvoiceSerializer, PayoutSerializer
from .services import (
    calculate_client_invoices_for_cycle,
    calculate_payouts_for_cycle,
    client_invoices_with_carried_forward,
    compute_admin_alerts,
    current_cycle_summary,
    current_payouts_for_cycle,
    cycle_revenue_totals,
    get_or_create_cycle,
    payouts_with_carried_forward,
    snapshot_cycle_revenue,
)


class BillingCycleViewSet(ModelViewSet):
    queryset = BillingCycle.objects.all().order_by('-cycle_start')
    serializer_class = BillingCycleSerializer
    permission_classes = [IsAdmin]
    # No DELETE — cycles are only ever closed (see close below), never hard-deleted, so
    # the Payout/ClientInvoice/CycleRevenueSnapshot history tied to them can never be lost.
    http_method_names = ['get', 'post', 'put', 'patch', 'head', 'options']

    @action(detail=False, methods=['post'])
    def generate_current(self, request):
        cycle, created = get_or_create_cycle()
        return Response(BillingCycleSerializer(cycle).data, status=201 if created else 200)

    @action(detail=True, methods=['post'])
    def close(self, request, pk=None):
        self.get_object()  # 404 if missing, runs the standard permission checks

        # Locked for the duration of this transaction so two concurrent "close" clicks
        # can't both pass the status check before either writes 'closed' — see
        # attendance/views.py's classes_completed fix for the same pattern.
        with transaction.atomic():
            cycle = BillingCycle.objects.select_for_update().get(pk=pk)
            if cycle.status != 'open':
                return Response({'detail': f'Cycle is already {cycle.status}.'}, status=400)

            calculate_payouts_for_cycle(cycle)
            calculate_client_invoices_for_cycle(cycle)
            snapshot_cycle_revenue(cycle)
            cycle.status = 'closed'
            cycle.save(update_fields=['status'])
        return Response(BillingCycleSerializer(cycle).data)

    @action(detail=True, methods=['get'])
    def current_payouts(self, request, pk=None):
        """Live per-trainer payout preview for this (still-open) cycle — see
        current_payouts_for_cycle()."""
        cycle = self.get_object()
        return Response(current_payouts_for_cycle(cycle))


class ClientInvoiceViewSet(ReadOnlyModelViewSet):
    queryset = ClientInvoice.objects.select_related('client', 'cycle').order_by('-cycle__cycle_start')
    serializer_class = ClientInvoiceSerializer
    permission_classes = [IsAdmin]

    def get_queryset(self):
        qs = super().get_queryset()
        client_id = self.request.query_params.get('client')
        cycle_id = self.request.query_params.get('cycle')
        if client_id:
            qs = qs.filter(client_id=client_id)
        if cycle_id:
            qs = qs.filter(cycle_id=cycle_id)
        return client_invoices_with_carried_forward(qs)

    @action(detail=True, methods=['post'])
    def mark_received(self, request, pk=None):
        invoice = self.get_object()
        if invoice.status == 'received':
            return Response({'detail': 'Invoice is already marked as received.'}, status=400)
        invoice.status = 'received'
        invoice.save(update_fields=['status'])
        log_action(
            request.user, 'invoice_mark_received',
            f'{invoice.client.company_name} — {invoice.cycle}', f'₹{invoice.total_amount}',
        )
        return Response(ClientInvoiceSerializer(invoice).data)

    @action(detail=True, methods=['get'])
    def pdf(self, request, pk=None):
        invoice = self.get_object()
        pdf_bytes = render_invoice_pdf(invoice)

        slug = re.sub(r'[^A-Za-z0-9]+', '-', invoice.client.company_name).strip('-').lower()
        filename = f'invoice-{slug}-{invoice.cycle.cycle_start}.pdf'

        response = HttpResponse(pdf_bytes, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response


class PayoutViewSet(ReadOnlyModelViewSet):
    queryset = Payout.objects.select_related('trainer', 'cycle').order_by('-cycle__cycle_start')
    serializer_class = PayoutSerializer
    permission_classes = [IsAdmin]

    def get_queryset(self):
        qs = super().get_queryset()
        trainer_id = self.request.query_params.get('trainer')
        cycle_id = self.request.query_params.get('cycle')
        if trainer_id:
            qs = qs.filter(trainer_id=trainer_id)
        if cycle_id:
            qs = qs.filter(cycle_id=cycle_id)
        return payouts_with_carried_forward(qs)

    @action(detail=True, methods=['post'])
    def mark_paid(self, request, pk=None):
        payout = self.get_object()
        if payout.paid_status != 'pending':
            return Response({'detail': f'Payout is already {payout.paid_status}.'}, status=400)
        payout.paid_status = 'paid'
        payout.save(update_fields=['paid_status'])
        log_action(
            request.user, 'payout_mark_paid',
            f'{payout.trainer.name} — {payout.cycle}', f'₹{payout.total_amount}',
        )
        return Response(PayoutSerializer(payout).data)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        payout = self.get_object()
        if payout.paid_status != 'pending':
            return Response({'detail': f'Payout is already {payout.paid_status}.'}, status=400)
        payout.paid_status = 'cancelled'
        payout.save(update_fields=['paid_status'])
        log_action(
            request.user, 'payout_cancel',
            f'{payout.trainer.name} — {payout.cycle}', f'₹{payout.total_amount}',
        )
        return Response(PayoutSerializer(payout).data)


class MyEarningsView(ListAPIView):
    """Trainer-facing: their own payout history."""

    serializer_class = PayoutSerializer
    permission_classes = [IsTrainer]

    def get_queryset(self):
        qs = Payout.objects.select_related('cycle', 'trainer').filter(
            trainer=self.request.user.trainer
        ).order_by('-cycle__cycle_start')
        cycle_id = self.request.query_params.get('cycle')
        if cycle_id:
            qs = qs.filter(cycle_id=cycle_id)
        return payouts_with_carried_forward(qs)


class CycleRevenueView(APIView):
    """Admin-facing: B2B + B2C revenue, trainer cost, and profit for a single
    billing cycle — powers the dashboard's cycle revenue card and is what the
    admin/owners use to work out that cycle's profit share. Defaults to the
    current in-progress cycle; pass ?cycle=<id> for a past one.

    Profit per side is revenue minus the trainer cost *of that side's own
    classes* — e.g. a B2B client billed at ₹200/class whose trainer is paid
    ₹100/class nets ₹100 profit; a B2C parent billed at ₹300/class on the same
    trainer's ₹100/class rate nets ₹200. Trainer payouts themselves are never
    split by B2B/B2C (see trainer_totals_for_range) — this view only splits the
    cost back out afterwards, for reporting. See cycle_revenue_totals() for how
    a closed cycle stays frozen against later rate changes.
    """

    permission_classes = [IsAdmin]

    def get(self, request):
        cycle_id = request.query_params.get('cycle')
        if cycle_id:
            try:
                cycle = BillingCycle.objects.get(pk=cycle_id)
            except BillingCycle.DoesNotExist:
                return Response({'detail': 'Cycle not found.'}, status=404)
        else:
            cycle, _ = get_or_create_cycle()

        return Response(cycle_revenue_totals(cycle))


class CycleRevenueHistoryView(APIView):
    """Admin-facing: the same B2B/B2C revenue/profit breakdown as
    CycleRevenueView, for every billing cycle (most recent first) — powers the
    dashboard's revenue-by-cycle history list. Pass ?limit=N to cap it.
    """

    permission_classes = [IsAdmin]

    def get(self, request):
        cycles = BillingCycle.objects.order_by('-cycle_start')
        limit = request.query_params.get('limit')
        if limit:
            try:
                limit = int(limit)
            except ValueError:
                return Response({'detail': 'limit must be a number.'}, status=400)
            cycles = cycles[:limit]
        return Response([cycle_revenue_totals(cycle) for cycle in cycles])


class MyCurrentCycleView(APIView):
    """Trainer-facing: live totals for the in-progress cycle, ahead of it being closed into a Payout."""

    permission_classes = [IsTrainer]

    def get(self, request):
        return Response(current_cycle_summary(request.user.trainer))


class AdminAlertsView(APIView):
    """Admin-facing: things needing attention right now — overdue B2B invoices
    and B2C installments that have reached their due milestone but are still
    unpaid. Computed live on every request rather than stored, the same way
    "current cycle" figures are elsewhere in the app — there's no scheduler in
    this project to generate notifications ahead of time, so this just
    re-derives the current state each time it's viewed.
    """

    permission_classes = [IsAdmin]

    def get(self, request):
        return Response(compute_admin_alerts())
