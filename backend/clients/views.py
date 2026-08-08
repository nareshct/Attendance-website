from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from billing.models import BillingCycle, ClientInvoice
from billing.services import client_all_time_totals, client_current_cycle_totals, get_or_create_cycle
from config.permissions import IsAdmin
from students.models import Student

from .models import Client, ClientContact, ClientCourseRate
from .serializers import ClientContactSerializer, ClientCourseRateSerializer, ClientSerializer
from .services import client_totals, get_archive_blockers


class ClientViewSet(ModelViewSet):
    serializer_class = ClientSerializer
    permission_classes = [IsAdmin]
    # No DELETE — clients are only ever archived (see archive/unarchive below), never
    # hard-deleted, so their students'/invoices' history can never be lost.
    http_method_names = ['get', 'post', 'put', 'patch', 'head', 'options']

    def get_queryset(self):
        # active_student_count/overdue_invoice_count are Subquery annotations rather than
        # folded into the same .annotate() as pending_amount's invoices Sum — aggregating
        # over two different reverse relations (students vs invoices) in one annotate()
        # call multiplies rows before aggregating (Django's multi-relation fan-out), which
        # would silently inflate pending_amount. A Subquery is independent of the outer
        # join and of each other, so this sidesteps that entirely.
        cutoff = date.today() - timedelta(days=ClientInvoice.OVERDUE_GRACE_DAYS)
        active_students = (
            Student.objects.filter(client=OuterRef('pk'), status='active')
            .order_by().values('client').annotate(c=Count('id')).values('c')
        )
        overdue_invoices = (
            ClientInvoice.objects.filter(client=OuterRef('pk'), status='pending', cycle__cycle_end__lt=cutoff)
            .order_by().values('client').annotate(c=Count('id')).values('c')
        )
        return Client.objects.annotate(
            pending_amount=Coalesce(
                Sum('invoices__total_amount', filter=Q(invoices__status='pending', invoices__cycle__status='closed')),
                Decimal('0.00'),
            ),
            active_student_count=Coalesce(Subquery(active_students), 0),
            overdue_invoice_count=Coalesce(Subquery(overdue_invoices), 0),
        ).order_by('company_name')

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Top-line stats for a dashboard header on the Clients list."""
        # Every client, not just active ones — an archived client can still have real
        # unpaid invoices or unbilled current-cycle revenue, and that money doesn't
        # stop being owed just because the client was archived. Mirrors
        # billing.services.compute_admin_alerts(), which deliberately doesn't filter
        # overdue_invoices by client status either.
        all_clients = Client.objects.annotate(
            pending_amount=Coalesce(
                Sum('invoices__total_amount', filter=Q(invoices__status='pending', invoices__cycle__status='closed')),
                Decimal('0.00'),
            )
        )
        current_cycle, _ = get_or_create_cycle()

        total_pending = Decimal('0.00')
        for client in all_clients:
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

    @action(detail=True, methods=['get'], url_path='archive-blockers')
    def archive_blockers(self, request, pk=None):
        """Everything still tying this client to active/unresolved billing — the
        frontend fetches this to build the archive warning checklist, and
        `archive()` below re-checks the same thing server-side so it can't be
        bypassed by calling the API directly. See services.get_archive_blockers."""
        client = self.get_object()
        return Response(get_archive_blockers(client))

    @action(detail=True, methods=['post'])
    def archive(self, request, pk=None):
        client = self.get_object()
        blockers = get_archive_blockers(client)
        if blockers['active_students'] or blockers['pending_invoices'] or Decimal(blockers['current_cycle_unbilled']) > 0:
            return Response(
                {
                    'detail': 'This client still has active students, pending invoices, or unbilled '
                    'current-cycle classes — resolve them first.',
                    'blockers': blockers,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
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
                # Pass this exact cycle, not the default (today's) one — normally the
                # only 'open' cycle is today's anyway, but BillingCycleViewSet.reopen()
                # can put an old cycle back to 'open' too, and this loop would otherwise
                # show today's totals against that old cycle's row instead of its own.
                totals = client_current_cycle_totals(client, cycle=cycle)
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
