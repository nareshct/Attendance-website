from decimal import Decimal

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db.models import Count, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce
from rest_framework import filters, status
from rest_framework.authtoken.models import Token
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from audit.services import log_action
from billing.models import Payout
from billing.serializers import PayoutSerializer
from billing.services import AlreadyDecidedCycleMismatch, current_cycle_summary, settle_trainer_current_cycle
from config.permissions import IsAdmin

from .models import Trainer, TrainerCourseRate
from .serializers import TrainerCourseRateSerializer, TrainerSerializer
from .services import get_archive_blockers


class TrainerViewSet(ModelViewSet):
    serializer_class = TrainerSerializer
    permission_classes = [IsAdmin]
    # ?search= matches name OR trainer_id OR place (case-insensitive substring) — mirrors
    # TrainersPage.jsx's search box, now run server-side so it covers every trainer, not
    # just whichever page happens to be loaded.
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'trainer_id', 'place']
    # No DELETE — trainers are only ever archived (see archive/unarchive below), never
    # hard-deleted, so their attendance/payout history can never be lost.
    http_method_names = ['get', 'post', 'put', 'patch', 'head', 'options']

    def get_queryset(self):
        # prefetch_related('course_rates') because TrainerSerializer nests every trainer's
        # course-rate overrides — without it, listing trainers triggers one extra query per
        # row (same class of bug as StudentViewSet's client_name, see reports/scale_audit.py).
        # active_student_count is annotated for the same reason.
        #
        # pending_payout_amount is a Subquery rather than a second Sum/Count folded into
        # this same .annotate() — aggregating over two different reverse relations
        # (enrollments vs payouts) in one annotate() call multiplies rows before
        # aggregating (Django's multi-relation fan-out), which would silently inflate
        # active_student_count. A Subquery is independent of the outer join, so it
        # sidesteps that entirely — see ClientViewSet.get_queryset() for the same pattern.
        pending_payouts = (
            Payout.objects.filter(trainer=OuterRef('pk'), paid_status='pending')
            .order_by().values('trainer').annotate(total=Sum('total_amount')).values('total')
        )
        qs = Trainer.objects.all().order_by('name').prefetch_related('course_rates').annotate(
            active_student_count=Count('enrollments', filter=Q(enrollments__status='ongoing')),
            pending_payout_amount=Coalesce(Subquery(pending_payouts), Decimal('0.00')),
        )
        status_param = self.request.query_params.get('status')
        if status_param:
            qs = qs.filter(status=status_param)
        return qs

    @action(detail=True, methods=['get'], url_path='archive-blockers')
    def archive_blockers(self, request, pk=None):
        """Everything still tying this trainer to active/unresolved work — the
        frontend fetches this to build the archive warning checklist, and
        `archive()` below re-checks the same thing server-side so it can't be
        bypassed by calling the API directly."""
        trainer = self.get_object()
        return Response(get_archive_blockers(trainer))

    @action(detail=True, methods=['post'], url_path='settle-current-cycle')
    def settle_current_cycle(self, request, pk=None):
        """Materializes this trainer's still-open current cycle into a real,
        immediately payable Payout row — see billing.services.settle_trainer_
        current_cycle. Resolves the 'current_cycle_earnings' archive blocker
        without waiting for the shared cycle to close for every trainer."""
        trainer = self.get_object()
        try:
            payout = settle_trainer_current_cycle(trainer)
        except AlreadyDecidedCycleMismatch as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        if payout is None:
            return Response({'detail': 'No unpaid current-cycle earnings to settle.'}, status=status.HTTP_400_BAD_REQUEST)
        log_action(request.user, 'payout_settle_current_cycle', f'{trainer.name} — {payout.cycle}', f'₹{payout.total_amount}')
        return Response(PayoutSerializer(payout).data)

    @action(detail=True, methods=['post'])
    def archive(self, request, pk=None):
        trainer = self.get_object()
        blockers = get_archive_blockers(trainer)
        if any(blockers.values()):
            return Response(
                {
                    'detail': 'This trainer still has ongoing batches/enrollments, pending attendance '
                    'requests, or pending payouts — resolve them first.',
                    'blockers': blockers,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        trainer.status = 'archived'
        trainer.save(update_fields=['status'])
        # is_active=False both blocks a future login (authenticate()) and immediately
        # invalidates any session/token they're already logged in with (DRF's
        # TokenAuthentication rejects inactive users on every request) — an archived
        # trainer loses access right away, not just on their next login attempt.
        trainer.user.is_active = False
        trainer.user.save(update_fields=['is_active'])
        log_action(request.user, 'trainer_archive', trainer.name)
        return Response(TrainerSerializer(trainer).data)

    @action(detail=True, methods=['post'])
    def unarchive(self, request, pk=None):
        trainer = self.get_object()
        trainer.status = 'active'
        trainer.save(update_fields=['status'])
        trainer.user.is_active = True
        trainer.user.save(update_fields=['is_active'])
        log_action(request.user, 'trainer_unarchive', trainer.name)
        return Response(TrainerSerializer(trainer).data)

    @action(detail=True, methods=['post'], url_path='reset-password')
    def reset_password(self, request, pk=None):
        trainer = self.get_object()
        new_password = request.data.get('new_password')
        if not new_password:
            return Response({'detail': 'new_password is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            validate_password(new_password, user=trainer.user)
        except ValidationError as exc:
            return Response({'detail': ' '.join(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)

        trainer.user.set_password(new_password)
        trainer.user.save(update_fields=['password'])
        # Kill any session the trainer is currently logged in with — an admin-triggered
        # reset (e.g. after a leaked password) should cut off existing access immediately,
        # not just block the old password going forward. They'll get a fresh token on
        # their next login (Token.objects.get_or_create in LoginView).
        Token.objects.filter(user=trainer.user).delete()
        log_action(request.user, 'trainer_reset_password', trainer.name)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['get'], url_path='current-cycle')
    def current_cycle(self, request, pk=None):
        """Admin-facing: live totals for this trainer's in-progress cycle, ahead of it closing into a Payout."""
        trainer = self.get_object()
        return Response(current_cycle_summary(trainer))


class TrainerCourseRateViewSet(ModelViewSet):
    queryset = TrainerCourseRate.objects.select_related('trainer', 'course').all()
    serializer_class = TrainerCourseRateSerializer
    permission_classes = [IsAdmin]

    def get_queryset(self):
        qs = super().get_queryset()
        trainer_id = self.request.query_params.get('trainer')
        if trainer_id:
            if not trainer_id.isdigit():
                raise DRFValidationError({'trainer': 'Invalid trainer filter.'})
            qs = qs.filter(trainer_id=trainer_id)
        return qs
