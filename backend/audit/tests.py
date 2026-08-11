from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from rest_framework.test import APIRequestFactory, APITestCase, force_authenticate

from trainers.models import Trainer

from .models import AuditLog
from .services import log_action
from .views import AuditLogViewSet


class AuditLogPermissionTests(APITestCase):
    """AuditLogViewSet is admin-only, read-only — the compliance trail itself
    shouldn't be editable, and a trainer has no business reading other
    people's activity."""

    def setUp(self):
        self.admin = get_user_model().objects.create_user(username='audit_admin', password='x', is_staff=True)
        trainer_user = get_user_model().objects.create_user(username='audit_trainer', password='x')
        self.trainer = Trainer.objects.create(
            user=trainer_user, name='Audit Trainer', phone_number='0000000000', place='Here', default_rate_per_class=100,
        )
        self.factory = APIRequestFactory()
        AuditLog.objects.create(action='course_rate_change', object_repr='Scratch', detail='₹100 → ₹150')

    def test_admin_can_list_audit_log(self):
        request = self.factory.get('/api/audit-log/')
        force_authenticate(request, user=self.admin)
        response = AuditLogViewSet.as_view({'get': 'list'})(request)
        self.assertEqual(response.status_code, 200)

    def test_trainer_cannot_list_audit_log(self):
        request = self.factory.get('/api/audit-log/')
        force_authenticate(request, user=self.trainer.user)
        response = AuditLogViewSet.as_view({'get': 'list'})(request)
        self.assertEqual(response.status_code, 403)

    def test_anonymous_cannot_list_audit_log(self):
        request = self.factory.get('/api/audit-log/')
        response = AuditLogViewSet.as_view({'get': 'list'})(request)
        self.assertIn(response.status_code, (401, 403))

    def test_viewset_has_no_write_actions(self):
        # ReadOnlyModelViewSet — create/update/destroy simply don't exist here, so
        # there's nothing a router could ever wire DELETE/POST/PUT to. The compliance
        # trail itself can't be edited or erased through this API.
        self.assertFalse(hasattr(AuditLogViewSet, 'destroy'))
        self.assertFalse(hasattr(AuditLogViewSet, 'create'))
        self.assertFalse(hasattr(AuditLogViewSet, 'update'))


class AuditLogLimitParamTests(APITestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_user(username='audit_limit_admin', password='x', is_staff=True)
        self.factory = APIRequestFactory()
        for i in range(5):
            AuditLog.objects.create(action='login', object_repr=f'user{i}', detail='admin')

    def test_invalid_limit_returns_400_not_a_crash(self):
        request = self.factory.get('/api/audit-log/?limit=not-a-number')
        force_authenticate(request, user=self.admin)
        response = AuditLogViewSet.as_view({'get': 'list'})(request)
        self.assertEqual(response.status_code, 400)

    def test_valid_limit_caps_the_results(self):
        # ?limit= slices the queryset itself, ahead of the standard page-numbered
        # pagination (PAGE_SIZE=100 — see REST_FRAMEWORK settings) wrapping the response.
        request = self.factory.get('/api/audit-log/?limit=2')
        force_authenticate(request, user=self.admin)
        response = AuditLogViewSet.as_view({'get': 'list'})(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), 2)

    def test_no_limit_returns_everything_under_the_default_cap(self):
        request = self.factory.get('/api/audit-log/')
        force_authenticate(request, user=self.admin)
        response = AuditLogViewSet.as_view({'get': 'list'})(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), 5)

    def test_most_recent_entry_is_listed_first(self):
        newest = AuditLog.objects.create(action='login', object_repr='newest', detail='admin')
        request = self.factory.get('/api/audit-log/')
        force_authenticate(request, user=self.admin)
        response = AuditLogViewSet.as_view({'get': 'list'})(request)
        self.assertEqual(response.data['results'][0]['id'], newest.id)


class LogActionAnonymousActorTests(APITestCase):
    """log_action() must never raise just because it's called from a spot where
    request.user isn't a real authenticated account (e.g. a failed login attempt,
    or any future caller that passes an AnonymousUser) — actor is nullable
    specifically to support this."""

    def test_anonymous_user_leaves_actor_null(self):
        log_action(AnonymousUser(), 'login', 'someone', 'attempted')
        entry = AuditLog.objects.get(action='login', object_repr='someone')
        self.assertIsNone(entry.actor)

    def test_none_leaves_actor_null(self):
        log_action(None, 'login', 'someone-else', 'attempted')
        entry = AuditLog.objects.get(action='login', object_repr='someone-else')
        self.assertIsNone(entry.actor)

    def test_real_authenticated_user_is_recorded_as_actor(self):
        user = get_user_model().objects.create_user(username='audit_real_actor', password='x', is_staff=True)
        log_action(user, 'login', 'admin', 'admin')
        entry = AuditLog.objects.get(action='login', object_repr='admin')
        self.assertEqual(entry.actor_id, user.id)


class AuditLogSerializerActorNameTests(APITestCase):
    def test_actor_name_falls_back_to_system_for_a_null_actor(self):
        from .serializers import AuditLogSerializer

        entry = AuditLog.objects.create(action='batch_delete', object_repr='Old batch')
        data = AuditLogSerializer(entry).data
        self.assertEqual(data['actor_name'], 'System')

    def test_actor_name_uses_trainer_name_when_actor_is_a_trainer(self):
        from .serializers import AuditLogSerializer

        user = get_user_model().objects.create_user(username='audit_serializer_trainer', password='x')
        trainer = Trainer.objects.create(
            user=user, name='Serializer Trainer', phone_number='0000000000', place='Here', default_rate_per_class=100,
        )
        entry = AuditLog.objects.create(actor=user, action='login', object_repr=trainer.name)
        data = AuditLogSerializer(entry).data
        self.assertEqual(data['actor_name'], 'Serializer Trainer')

    def test_actor_name_uses_username_for_a_non_trainer_actor(self):
        from .serializers import AuditLogSerializer

        admin = get_user_model().objects.create_user(username='audit_serializer_admin', password='x', is_staff=True)
        entry = AuditLog.objects.create(actor=admin, action='login', object_repr='admin')
        data = AuditLogSerializer(entry).data
        self.assertEqual(data['actor_name'], 'audit_serializer_admin')
