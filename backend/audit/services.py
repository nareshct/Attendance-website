from .models import AuditLog


def log_action(user, action, object_repr, detail=''):
    """Record a sensitive action to the audit trail. `user` may be an
    anonymous/unauthenticated request's user object — AuditLog.actor is
    nullable specifically so this never raises if called from a spot where
    request.user isn't a real authenticated account.
    """
    actor = user if getattr(user, 'is_authenticated', False) else None
    AuditLog.objects.create(actor=actor, action=action, object_repr=object_repr, detail=detail)
