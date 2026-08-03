from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from rest_framework import filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from billing.services import current_cycle_summary
from config.permissions import IsAdmin

from .models import Trainer, TrainerCourseRate
from .serializers import TrainerCourseRateSerializer, TrainerSerializer


class TrainerViewSet(ModelViewSet):
    # prefetch_related('course_rates') because TrainerSerializer nests every trainer's
    # course-rate overrides — without it, listing trainers triggers one extra query per
    # row (same class of bug as StudentViewSet's client_name, see reports/scale_audit.py).
    queryset = Trainer.objects.all().order_by('name').prefetch_related('course_rates')
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

    @action(detail=True, methods=['post'])
    def archive(self, request, pk=None):
        trainer = self.get_object()
        trainer.status = 'archived'
        trainer.save(update_fields=['status'])
        return Response(TrainerSerializer(trainer).data)

    @action(detail=True, methods=['post'])
    def unarchive(self, request, pk=None):
        trainer = self.get_object()
        trainer.status = 'active'
        trainer.save(update_fields=['status'])
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
            qs = qs.filter(trainer_id=trainer_id)
        return qs
