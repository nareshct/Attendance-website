from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIRequestFactory

from .views import LoginView


class LoginThrottleTests(TestCase):
    """LoginRateThrottle caps repeated bad-credential attempts from the same
    client so brute-forcing can't be hammered at speed — see
    config/throttling.py and DEFAULT_THROTTLE_RATES in settings.py.
    """

    def setUp(self):
        # DRF throttle state lives in Django's cache, which persists across
        # tests unless cleared — without this, an earlier test's attempts
        # would carry over and this test could start out already throttled.
        cache.clear()

    def test_excessive_login_attempts_are_throttled(self):
        factory = APIRequestFactory()
        view = LoginView.as_view()
        statuses = []
        for _ in range(6):
            request = factory.post('/api/auth/login/', {'username': 'nope', 'password': 'wrong'}, format='json')
            response = view(request)
            statuses.append(response.status_code)

        self.assertEqual(statuses[:5], [401] * 5, 'the configured rate (5/min) should allow exactly 5 attempts through')
        self.assertEqual(statuses[5], 429, 'the 6th attempt within the window must be throttled')
