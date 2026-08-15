from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db.models import Count, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import filters, status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet

from audit.services import log_action
from billing.models import BillingCycle, ClientInvoice
from billing.services import client_all_time_totals, client_current_cycle_totals, get_or_create_cycle
from config.models import AuthToken
from config.permissions import IsAdmin, IsClient
from students.models import Student

from .models import Client, ClientContact, ClientCourseRate
from .serializers import ClientContactSerializer, ClientCourseRateSerializer, ClientSerializer
from .services import client_students_with_progress, get_archive_blockers


class ClientViewSet(ModelViewSet):
    serializer_class = ClientSerializer
    permission_classes = [IsAdmin]
    # ?search= matches company name OR contact phone (case-insensitive substring) — same
    # server-side search pattern as TrainerViewSet/StudentViewSet, used by both the
    # Clients list page and any async-search client picker (see SearchableSelect).
    filter_backends = [filters.SearchFilter]
    search_fields = ['company_name', 'contact_phone']
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
        cutoff = timezone.localdate() - timedelta(days=ClientInvoice.OVERDUE_GRACE_DAYS)
        active_students = (
            Student.objects.filter(client=OuterRef('pk'), status='active')
            .order_by().values('client').annotate(c=Count('id')).values('c')
        )
        overdue_invoices = (
            ClientInvoice.objects.filter(client=OuterRef('pk'), status='pending', cycle__cycle_end__lt=cutoff)
            .order_by().values('client').annotate(c=Count('id')).values('c')
        )
        qs = Client.objects.annotate(
            pending_amount=Coalesce(
                Sum('invoices__total_amount', filter=Q(invoices__status='pending', invoices__cycle__status='closed')),
                Decimal('0.00'),
            ),
            active_student_count=Coalesce(Subquery(active_students), 0),
            overdue_invoice_count=Coalesce(Subquery(overdue_invoices), 0),
        ).order_by('company_name')
        status_param = self.request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param)
        return qs

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
        # Most clients have no login at all (see set_up_login below) — guard for that,
        # mirroring TrainerViewSet.archive's is_active=False (blocks future login and
        # immediately invalidates any live token) for the clients that do have one.
        if client.user_id:
            client.user.is_active = False
            client.user.save(update_fields=['is_active'])
        log_action(request.user, 'client_archive', client.company_name)
        return Response(ClientSerializer(client).data)

    @action(detail=True, methods=['post'])
    def unarchive(self, request, pk=None):
        client = self.get_object()
        client.status = 'active'
        client.save(update_fields=['status'])
        if client.user_id:
            client.user.is_active = True
            client.user.save(update_fields=['is_active'])
        log_action(request.user, 'client_unarchive', client.company_name)
        return Response(ClientSerializer(client).data)

    @action(detail=True, methods=['post'], url_path='set-up-login')
    def set_up_login(self, request, pk=None):
        """Grants a client portal access — unlike Trainer, this is optional and can
        happen any time after the client itself was created (see Client.user's
        nullable field)."""
        client = self.get_object()
        if client.status == 'archived':
            return Response(
                {'detail': 'This client is archived — unarchive it first before granting a login.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if client.user_id:
            return Response(
                {'detail': 'This client already has a login — use reset-password instead.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        username = request.data.get('username')
        password = request.data.get('password')
        if not username or not password:
            return Response(
                {'detail': 'username and password are required.'}, status=status.HTTP_400_BAD_REQUEST
            )
        if User.objects.filter(username=username).exists():
            return Response({'username': 'A user with this username already exists.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            validate_password(password)
        except ValidationError as exc:
            return Response({'detail': ' '.join(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.create_user(username=username, password=password)
        client.user = user
        client.save(update_fields=['user'])
        log_action(request.user, 'client_set_up_login', client.company_name, username)
        return Response(ClientSerializer(client).data)

    @action(detail=True, methods=['post'], url_path='reset-password')
    def reset_password(self, request, pk=None):
        client = self.get_object()
        if not client.user_id:
            return Response({'detail': 'This client has no login set up yet.'}, status=status.HTTP_400_BAD_REQUEST)

        new_password = request.data.get('new_password')
        if not new_password:
            return Response({'detail': 'new_password is required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            validate_password(new_password, user=client.user)
        except ValidationError as exc:
            return Response({'detail': ' '.join(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)

        client.user.set_password(new_password)
        client.user.save(update_fields=['password'])
        # Kill every session (every device's token) the client is currently logged in
        # with — mirrors TrainerViewSet.reset_password exactly.
        AuthToken.objects.filter(user=client.user).delete()
        log_action(request.user, 'client_reset_password', client.company_name)
        return Response(status=status.HTTP_204_NO_CONTENT)

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
        limit_param = request.query_params.get('limit', '12')
        if not limit_param.isdigit():
            raise DRFValidationError({'limit': 'Invalid limit — must be a positive integer.'})
        limit = int(limit_param)

        cycles = list(BillingCycle.objects.order_by('-cycle_start')[:limit])
        cycles.reverse()

        history = []
        for cycle in cycles:
            # Always pass this exact cycle (not the default "today's" one — normally the
            # only 'open' cycle is today's anyway, but BillingCycleViewSet.reopen() can
            # put an old cycle back to 'open' too). Used for every cycle, not just open
            # ones: client_current_cycle_totals() also folds in any ClientInvoiceAdjustment
            # already assigned to it (a late-approved class carried forward from an
            # earlier, already-closed cycle) — client_totals() alone excludes those, which
            # would under-report a closed cycle relative to the real ClientInvoice actually
            # sent for it.
            totals = client_current_cycle_totals(client, cycle=cycle)
            history.append({
                'cycle_start': cycle.cycle_start,
                'cycle_end': cycle.cycle_end,
                'status': cycle.status,
                'total_classes': totals['total_classes'],
                'total_revenue': totals['total_revenue'],
                'our_earning': totals['our_earning'],
            })
        return Response(history)


class MyClientProfileView(APIView):
    """Client-facing: their own profile. ClientSerializer is already margin-free
    (pending_amount is live billing, not our earning), so it's safe to reuse
    directly here — unlike ClientViewSet.earnings/earnings_history, which must
    never be exposed to the client themselves (see MyClientCurrentCycleView in
    billing/views.py)."""

    permission_classes = [IsClient]

    def get(self, request):
        return Response(ClientSerializer(request.user.client).data)


class MyClientStudentsView(APIView):
    """Client-facing: their own students, with course/batch + progress —
    server-side version of ClientDetailPage.jsx's studentPrimaryEnrollment/
    studentPrimaryBatchEnrollment picking logic. See client_students_with_progress."""

    permission_classes = [IsClient]

    def get(self, request):
        return Response(client_students_with_progress(request.user.client))


class MyClientStudentDetailView(APIView):
    """Client-facing: one of their own students' enrollments, batch memberships,
    and recent class history. Same narrow, read-only shape as
    students.views.ParentShareView (no rates, no payment/installment amounts,
    no other students) — get_object_or_404's client=request.user.client filter
    is what keeps this scoped to the caller's own students; another client's
    (or a B2C student's) id 404s here rather than ever being serialized."""

    permission_classes = [IsClient]

    def get(self, request, student_id):
        student = get_object_or_404(Student, id=student_id, client=request.user.client)

        enrollments = (
            student.enrollments.select_related('course', 'trainer')
            .prefetch_related('attendance_records')
            .order_by('-start_date')
        )
        enrollment_rows = [
            {
                'id': e.id,
                'course_name': e.course.name,
                'trainer_name': e.trainer.name,
                'batch_number': e.batch_number,
                'classes_completed': e.classes_completed,
                'classes_total': e.classes_total,
                'status': e.status,
                'start_date': e.start_date,
                'class_time': e.class_time,
                'class_days': e.class_days,
                'recent_classes': [
                    {'date': a.date, 'topic_covered': a.topic_covered}
                    for a in e.attendance_records.filter(status='present').order_by('-date')
                ],
            }
            for e in enrollments
        ]

        batch_enrollments = student.batch_enrollments.select_related('batch__course').order_by('-joined_date')
        batch_rows = [
            {
                'id': be.id,
                'batch_name': be.batch.name,
                'course_name': be.batch.course.name,
                'status': be.status,
                'joined_date': be.joined_date,
            }
            for be in batch_enrollments
        ]

        return Response({
            'id': student.id,
            'student_id': student.student_id,
            'name': student.name,
            'grade': student.grade,
            'status': student.status,
            'enrollments': enrollment_rows,
            'batch_enrollments': batch_rows,
        })


class ClientCourseRateViewSet(ModelViewSet):
    queryset = ClientCourseRate.objects.select_related('client', 'course').all()
    serializer_class = ClientCourseRateSerializer
    permission_classes = [IsAdmin]

    def get_queryset(self):
        qs = super().get_queryset()
        client_id = self.request.query_params.get('client')
        if client_id:
            if not client_id.isdigit():
                raise DRFValidationError({'client': 'Invalid client filter.'})
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
            if not client_id.isdigit():
                raise DRFValidationError({'client': 'Invalid client filter.'})
            qs = qs.filter(client_id=client_id)
        return qs
