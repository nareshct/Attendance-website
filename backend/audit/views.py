from rest_framework.exceptions import ValidationError
from rest_framework.viewsets import ReadOnlyModelViewSet

from config.permissions import IsAdmin

from .models import AuditLog
from .serializers import AuditLogSerializer


class AuditLogViewSet(ReadOnlyModelViewSet):
    """Admin-facing, read-only activity feed. Capped at 200 rows by default
    (no pagination in this project yet) — pass ?limit=N for a different cap.
    """

    queryset = AuditLog.objects.select_related('actor', 'actor__trainer').all()
    serializer_class = AuditLogSerializer
    permission_classes = [IsAdmin]

    def get_queryset(self):
        qs = super().get_queryset()
        limit = self.request.query_params.get('limit')
        if not limit:
            return qs[:200]
        try:
            limit = int(limit)
        except ValueError:
            raise ValidationError({'detail': 'limit must be a number.'})
        return qs[:limit]
