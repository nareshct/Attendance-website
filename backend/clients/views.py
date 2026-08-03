from decimal import Decimal

from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from billing.models import BillingCycle, ClientInvoice
from billing.services import client_all_time_totals, client_current_cycle_totals, get_or_create_cycle
from config.permissions import IsAdmin

from .models import Client, ClientContact, ClientCourseRate
from .serializers import ClientContactSerializer, ClientCourseRateSerializer, ClientSerializer
from .services import client_totals


class ClientViewSet(ModelViewSet):
    queryset = Client.objects.annotate(
        pending_amount=Coalesce(
            Sum('invoices__total_amount', filter=Q(invoices__status='pending', invoices__cycle__status='closed')),
            Decimal('0.00'),
        )
    ).order_by('company_name')
    serializer_class = ClientSerializer
    permission_classes = [IsAdmin]
    # No DELETE — clients are only ever archived (see archive/unarchive below), never
    # hard-deleted, so their students'/invoices' history can never be lost.
    http_method_names = ['get', 'post', 'put', 'patch', 'head', 'options']

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Top-line stats for a dashboard header on the Clients list."""
        active_clients = Client.objects.filter(status='active').annotate(
            pending_amount=Coalesce(
                Sum('invoices__total_amount', filter=Q(invoices__status='pending', invoices__cycle__status='closed')),
                Decimal('0.00'),
            )
        )
        current_cycle, _ = get_or_create_cycle()

        total_pending = Decimal('0.00')
        for client in active_clients:
            current = client_current_cycle_totals(client, cycle=current_cycle)
            total_pending += current['total_revenue'] + (client.pending_amount or Decimal('0.00'))

        # All-time profit/classes across every client, active or archived — archiving
        # a client doesn't erase what was already earned from or taught to them.
        total_earning = Decimal('0.00')
        total_classes = 0
        for client in Client.objects.all():
            all_time = client_all_time_totals(client)
            total_earning += all_time['our_earning']
            total_classes += all_time['total_classes']

        return Response({
            'total_pending_amount': total_pending,
            'total_earning': total_earning,
            'total_classes': total_classes,
        })

    @action(detail=True, methods=['post'])
    def archive(self, request, pk=None):
        client = self.get_object()
        client.status = 'archived'
        client.save(update_fields=['status'])
        return Response(ClientSerializer(client).data)

    @action(detail=True, methods=['post'])
    def unarchive(self, request, pk=None):
        client = self.get_object()
        client.status = 'active'
        client.save(update_fields=['status'])
        return Response(ClientSerializer(client).data)

    @action(detail=True, methods=['get'])
    def earnings(self, request, pk=None):
        """Current cycle's live classes/billing, all-time profit, and outstanding pending pay-ins."""
        client = self.get_object()
        current = client_current_cycle_totals(client)
        all_time = client_all_time_totals(client)

        pending_amount = ClientInvoice.objects.filter(
            client=client, status='pending', cycle__status='closed',
        ).aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')

        return Response({
            'cycle_start': current['cycle_start'],
            'cycle_end': current['cycle_end'],
            'current_classes': current['total_classes'],
            'previous_classes': all_time['total_classes'] - current['total_classes'],
            'total_classes': all_time['total_classes'],
            'current_cycle_billed': current['total_revenue'],
            'carried_forward_amount': current['carried_forward_amount'],
            'carried_forward_count': current['carried_forward_count'],
            'pending_amount': pending_amount,
            'billed_to_client': current['total_revenue'] + pending_amount,
            'current_earning': current['our_earning'],
            'previous_earning': all_time['our_earning'] - current['our_earning'],
            'total_earning': all_time['our_earning'],
        })

    @action(detail=True, methods=['get'])
    def earnings_history(self, request, pk=None):
        """Per-cycle classes/revenue/earning for the last N cycles (chronological), for a trend chart."""
        client = self.get_object()
        limit = int(request.query_params.get('limit', 12))

        cycles = list(BillingCycle.objects.order_by('-cycle_start')[:limit])
        cycles.reverse()

        history = []
        for cycle in cycles:
            if cycle.status == 'open':
                totals = client_current_cycle_totals(client)
            else:
                totals = client_totals(client, cycle.cycle_start, cycle.cycle_end)
            history.append({
                'cycle_start': cycle.cycle_start,
                'cycle_end': cycle.cycle_end,
                'status': cycle.status,
                'total_classes': totals['total_classes'],
                'total_revenue': totals['total_revenue'],
                'our_earning': totals['our_earning'],
            })
        return Response(history)


class ClientCourseRateViewSet(ModelViewSet):
    queryset = ClientCourseRate.objects.select_related('client', 'course').all()
    serializer_class = ClientCourseRateSerializer
    permission_classes = [IsAdmin]

    def get_queryset(self):
        qs = super().get_queryset()
        client_id = self.request.query_params.get('client')
        if client_id:
            qs = qs.filter(client_id=client_id)
        return qs


class ClientContactViewSet(ModelViewSet):
    queryset = ClientContact.objects.select_related('client').all()
    serializer_class = ClientContactSerializer
    permission_classes = [IsAdmin]

    def get_queryset(self):
        qs = super().get_queryset()
        client_id = self.request.query_params.get('client')
        if client_id:
            qs = qs.filter(client_id=client_id)
        return qs
