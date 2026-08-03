from rest_framework.throttling import AnonRateThrottle


class LoginRateThrottle(AnonRateThrottle):
    """Limits login attempts per client IP so credential-guessing can't be
    hammered at speed. Deliberately IP-scoped rather than per-account, so it
    can't itself be abused to lock a real user out by repeatedly failing their
    username. Rate set in settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'].
    """

    scope = 'login'


class PasswordResetRateThrottle(AnonRateThrottle):
    """Limits password-reset requests per client IP, so the endpoint can't be
    used to spam a mailbox with reset emails or hammer the confirm step."""

    scope = 'password_reset'
