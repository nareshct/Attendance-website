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


class ParentLinkRateThrottle(AnonRateThrottle):
    """Limits requests per client IP to the public, unauthenticated parent
    share-link endpoints (ParentShareView/ParentCertificateView). The token
    itself is a UUID4 — brute-forcing it isn't practical — but these are the
    only endpoints in the app with no login at all, so a per-IP cap still
    guards against scraping/DoS since nothing else stands between a request
    and the database."""

    scope = 'parent_link'
