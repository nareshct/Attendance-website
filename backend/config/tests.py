import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIRequestFactory, force_authenticate

from audit.models import AuditLog
from clients.models import Client
from trainers.models import Trainer

from .models import AuthToken
from .views import (
    ChangePasswordView,
    LoginView,
    LogoutView,
    MeView,
    PasswordResetConfirmView,
    PasswordResetRequestView,
    UpdateEmailView,
)


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


class LoginViewTests(TestCase):
    """Activity Log frames itself as "who did what, when" — a login previously left
    no trace there at all."""

    def setUp(self):
        cache.clear()
        self.factory = APIRequestFactory()

    def test_successful_login_returns_token_and_role(self):
        get_user_model().objects.create_user(username='login_admin', password='CorrectPass123!', is_staff=True)
        request = self.factory.post('/api/auth/login/', {'username': 'login_admin', 'password': 'CorrectPass123!'}, format='json')
        response = LoginView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['role'], 'admin')
        self.assertTrue(response.data['token'])

    def test_successful_login_writes_an_audit_log_entry(self):
        user = get_user_model().objects.create_user(username='login_audit_admin', password='CorrectPass123!', is_staff=True)
        request = self.factory.post('/api/auth/login/', {'username': 'login_audit_admin', 'password': 'CorrectPass123!'}, format='json')
        LoginView.as_view()(request)
        entry = AuditLog.objects.get(action='login', object_repr='login_audit_admin')
        self.assertEqual(entry.actor_id, user.id)

    def test_failed_login_does_not_write_an_audit_log_entry(self):
        get_user_model().objects.create_user(username='login_fail_admin', password='CorrectPass123!')
        request = self.factory.post('/api/auth/login/', {'username': 'login_fail_admin', 'password': 'WrongPass'}, format='json')
        response = LoginView.as_view()(request)
        self.assertEqual(response.status_code, 401)
        self.assertFalse(AuditLog.objects.filter(action='login', object_repr='login_fail_admin').exists())

    def test_trainer_login_logs_the_trainer_name_not_the_username(self):
        user = get_user_model().objects.create_user(username='login_trainer_user', password='CorrectPass123!')
        Trainer.objects.create(user=user, name='Login Trainer', phone_number='0000000000', place='Here', default_rate_per_class=100)
        request = self.factory.post('/api/auth/login/', {'username': 'login_trainer_user', 'password': 'CorrectPass123!'}, format='json')
        LoginView.as_view()(request)
        entry = AuditLog.objects.get(action='login', object_repr='Login Trainer')
        self.assertEqual(entry.detail, 'trainer')

    def test_client_login_returns_client_role(self):
        user = get_user_model().objects.create_user(username='login_client_user', password='CorrectPass123!')
        Client.objects.create(company_name='Login Client Co', contact_phone='123', rate_per_class=200, user=user)
        request = self.factory.post('/api/auth/login/', {'username': 'login_client_user', 'password': 'CorrectPass123!'}, format='json')
        response = LoginView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['role'], 'client')
        self.assertEqual(response.data['name'], 'Login Client Co')

    def test_client_login_logs_the_company_name_not_the_username(self):
        user = get_user_model().objects.create_user(username='login_client_audit_user', password='CorrectPass123!')
        Client.objects.create(company_name='Audit Client Co', contact_phone='123', rate_per_class=200, user=user)
        request = self.factory.post('/api/auth/login/', {'username': 'login_client_audit_user', 'password': 'CorrectPass123!'}, format='json')
        LoginView.as_view()(request)
        entry = AuditLog.objects.get(action='login', object_repr='Audit Client Co')
        self.assertEqual(entry.detail, 'client')

    def test_logging_in_again_from_another_device_does_not_invalidate_the_first(self):
        get_user_model().objects.create_user(username='multi_device_user', password='CorrectPass123!')
        body = {'username': 'multi_device_user', 'password': 'CorrectPass123!'}
        first = LoginView.as_view()(self.factory.post('/api/auth/login/', body, format='json'))
        second = LoginView.as_view()(self.factory.post('/api/auth/login/', body, format='json'))

        self.assertNotEqual(first.data['token'], second.data['token'], 'each login should get its own token')
        self.assertTrue(AuthToken.objects.filter(key=first.data['token']).exists(), "device A's token must still work")
        self.assertTrue(AuthToken.objects.filter(key=second.data['token']).exists())


class LogoutViewTests(TestCase):
    def test_logout_deletes_the_auth_token(self):
        user = get_user_model().objects.create_user(username='logout_user', password='x')
        token = AuthToken.objects.create(user=user)
        request = APIRequestFactory().post('/api/auth/logout/')
        force_authenticate(request, user=user, token=token)
        response = LogoutView.as_view()(request)
        self.assertEqual(response.status_code, 204)
        self.assertFalse(AuthToken.objects.filter(key=token.key).exists())

    def test_logout_leaves_other_devices_tokens_alone(self):
        user = get_user_model().objects.create_user(username='logout_multi_device_user', password='x')
        this_device = AuthToken.objects.create(user=user)
        other_device = AuthToken.objects.create(user=user)
        request = APIRequestFactory().post('/api/auth/logout/')
        force_authenticate(request, user=user, token=this_device)
        response = LogoutView.as_view()(request)
        self.assertEqual(response.status_code, 204)
        self.assertFalse(AuthToken.objects.filter(key=this_device.key).exists())
        self.assertTrue(AuthToken.objects.filter(key=other_device.key).exists())


class ChangePasswordViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='change_pw_user', password='OldPass123!')
        self.factory = APIRequestFactory()

    def _post(self, **body):
        request = self.factory.post('/api/auth/change-password/', body, format='json')
        force_authenticate(request, user=self.user)
        return ChangePasswordView.as_view()(request)

    def test_wrong_current_password_is_rejected(self):
        response = self._post(current_password='WrongPass', new_password='NewPass456!')
        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('OldPass123!'))

    def test_correct_current_password_changes_it(self):
        response = self._post(current_password='OldPass123!', new_password='NewPass456!')
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NewPass456!'))

    def test_missing_fields_returns_400(self):
        response = self._post(current_password='OldPass123!')
        self.assertEqual(response.status_code, 400)

    def test_changing_password_rotates_the_auth_token(self):
        old_token = AuthToken.objects.create(user=self.user)
        response = self._post(current_password='OldPass123!', new_password='NewPass456!')
        self.assertEqual(response.status_code, 200)
        self.assertIn('token', response.data)
        self.assertNotEqual(response.data['token'], old_token.key)
        self.assertFalse(AuthToken.objects.filter(key=old_token.key).exists())
        self.assertTrue(AuthToken.objects.filter(user=self.user, key=response.data['token']).exists())

    def test_changing_password_signs_out_every_other_device(self):
        other_device = AuthToken.objects.create(user=self.user)
        response = self._post(current_password='OldPass123!', new_password='NewPass456!')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(AuthToken.objects.filter(key=other_device.key).exists())

    def test_successful_change_writes_an_audit_log_entry(self):
        response = self._post(current_password='OldPass123!', new_password='NewPass456!')
        self.assertEqual(response.status_code, 200)
        entry = AuditLog.objects.get(action='password_change', object_repr='change_pw_user')
        self.assertEqual(entry.actor_id, self.user.id)

    def test_wrong_current_password_does_not_write_an_audit_log_entry(self):
        self._post(current_password='WrongPass', new_password='NewPass456!')
        self.assertFalse(AuditLog.objects.filter(action='password_change').exists())


class MeViewTests(TestCase):
    def test_returns_admin_profile(self):
        user = get_user_model().objects.create_user(username='me_admin', password='x', email='me@example.com', is_staff=True)
        request = APIRequestFactory().get('/api/auth/me/')
        force_authenticate(request, user=user)
        response = MeView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['username'], 'me_admin')
        self.assertEqual(response.data['email'], 'me@example.com')
        self.assertEqual(response.data['role'], 'admin')

    def test_returns_trainer_profile_with_trainer_name_and_role(self):
        user = get_user_model().objects.create_user(username='me_trainer', password='x')
        Trainer.objects.create(user=user, name='Priya T', phone_number='0000000000', place='Here', default_rate_per_class=100)
        request = APIRequestFactory().get('/api/auth/me/')
        force_authenticate(request, user=user)
        response = MeView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['name'], 'Priya T')
        self.assertEqual(response.data['role'], 'trainer')

    def test_returns_client_profile_with_company_name_and_role(self):
        user = get_user_model().objects.create_user(username='me_client', password='x')
        Client.objects.create(company_name='Me Client Co', contact_phone='123', rate_per_class=200, user=user)
        request = APIRequestFactory().get('/api/auth/me/')
        force_authenticate(request, user=user)
        response = MeView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['name'], 'Me Client Co')
        self.assertEqual(response.data['role'], 'client')


class UpdateEmailViewTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='update_email_user', password='x')
        self.factory = APIRequestFactory()

    def _post(self, email):
        request = self.factory.post('/api/auth/update-email/', {'email': email}, format='json')
        force_authenticate(request, user=self.user)
        return UpdateEmailView.as_view()(request)

    def test_valid_email_is_saved(self):
        response = self._post('new@example.com')
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'new@example.com')

    def test_invalid_email_is_rejected(self):
        response = self._post('not-an-email')
        self.assertEqual(response.status_code, 400)

    def test_empty_email_is_rejected(self):
        response = self._post('')
        self.assertEqual(response.status_code, 400)


class PasswordResetRequestViewTests(TestCase):
    def setUp(self):
        # See LoginThrottleTests — PasswordResetRateThrottle shares this cache too.
        cache.clear()

    def test_existing_user_with_email_gets_generic_response_and_email_sent(self):
        get_user_model().objects.create_user(username='reset_user', password='x', email='reset@example.com')
        request = APIRequestFactory().post('/api/auth/password-reset/', {'username': 'reset_user'}, format='json')
        response = PasswordResetRequestView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['detail'], PasswordResetRequestView.GENERIC_MESSAGE)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('reset@example.com', mail.outbox[0].to)

    def test_nonexistent_user_gets_same_generic_response_and_no_email(self):
        request = APIRequestFactory().post('/api/auth/password-reset/', {'username': 'nobody'}, format='json')
        response = PasswordResetRequestView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['detail'], PasswordResetRequestView.GENERIC_MESSAGE)
        self.assertEqual(len(mail.outbox), 0)


class PasswordResetConfirmViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user(
            username='confirm_reset_user', password='OldPass123!', email='confirm@example.com',
        )
        self.uidb64 = urlsafe_base64_encode(force_bytes(self.user.pk))
        self.token = default_token_generator.make_token(self.user)
        self.factory = APIRequestFactory()

    def test_valid_uid_and_token_resets_the_password(self):
        request = self.factory.post('/api/auth/password-reset/confirm/', {
            'uid': self.uidb64, 'token': self.token, 'new_password': 'BrandNewPass789!',
        }, format='json')
        response = PasswordResetConfirmView.as_view()(request)
        self.assertEqual(response.status_code, 204)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('BrandNewPass789!'))

    def test_resetting_the_password_deletes_any_existing_auth_token(self):
        old_token = AuthToken.objects.create(user=self.user)
        request = self.factory.post('/api/auth/password-reset/confirm/', {
            'uid': self.uidb64, 'token': self.token, 'new_password': 'BrandNewPass789!',
        }, format='json')
        response = PasswordResetConfirmView.as_view()(request)
        self.assertEqual(response.status_code, 204)
        self.assertFalse(AuthToken.objects.filter(key=old_token.key).exists())

    def test_successful_reset_writes_an_audit_log_entry(self):
        request = self.factory.post('/api/auth/password-reset/confirm/', {
            'uid': self.uidb64, 'token': self.token, 'new_password': 'BrandNewPass789!',
        }, format='json')
        response = PasswordResetConfirmView.as_view()(request)
        self.assertEqual(response.status_code, 204)
        entry = AuditLog.objects.get(action='password_reset', object_repr='confirm_reset_user')
        self.assertEqual(entry.actor_id, self.user.id)

    def test_invalid_token_is_rejected(self):
        request = self.factory.post('/api/auth/password-reset/confirm/', {
            'uid': self.uidb64, 'token': 'garbage-token', 'new_password': 'BrandNewPass789!',
        }, format='json')
        response = PasswordResetConfirmView.as_view()(request)
        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('OldPass123!'))

    def test_invalid_uid_is_rejected(self):
        request = self.factory.post('/api/auth/password-reset/confirm/', {
            'uid': 'not-valid-base64', 'token': self.token, 'new_password': 'BrandNewPass789!',
        }, format='json')
        response = PasswordResetConfirmView.as_view()(request)
        self.assertEqual(response.status_code, 400)


class ErrorLoggingEmailsAdminsTests(TestCase):
    """See LOGGING in config/settings.py — an ERROR-level log through the 'django'
    logger must reach ADMINS by email, since Render's console output doesn't survive
    a dyno restart and no external error tracker is configured."""

    @override_settings(DEBUG=False, ADMINS=[('Test Admin', 'admin@example.com')])
    def test_error_level_log_emails_admins_when_debug_is_false(self):
        logger = logging.getLogger('django')
        try:
            raise ValueError('simulated error for logging test')
        except ValueError:
            logger.error('Simulated unhandled exception', exc_info=True)

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('admin@example.com', mail.outbox[0].to)
        self.assertIn('simulated error for logging test', mail.outbox[0].body)

    @override_settings(DEBUG=True, ADMINS=[('Test Admin', 'admin@example.com')])
    def test_error_level_log_does_not_email_admins_when_debug_is_true(self):
        # RequireDebugFalse must keep this quiet during local dev.
        logger = logging.getLogger('django')
        logger.error('Simulated error during local dev')

        self.assertEqual(len(mail.outbox), 0)
