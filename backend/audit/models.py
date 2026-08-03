from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    """A human-readable trail of sensitive admin actions — who did what, and
    when. Not exhaustive coverage of every write in the app; just the actions
    where "who changed this" actually matters for a small business handling
    real money: marking things paid/received, permanent reassignments, and
    deleting records that affect billing history. See audit.services.log_action().
    """

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='audit_logs'
    )
    action = models.CharField(max_length=60)
    object_repr = models.CharField(max_length=255)
    detail = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.action} — {self.object_repr}'
