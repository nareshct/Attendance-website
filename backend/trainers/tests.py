from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory, APITestCase, force_authenticate

from .models import Trainer
from .views import TrainerViewSet


class TrainerSearchTests(APITestCase):
    """?search= must match name OR trainer_id OR place server-side (see
    TrainerViewSet.search_fields), so a match is found regardless of which
    page it would otherwise fall on.
    """

    def setUp(self):
        self.admin = get_user_model().objects.create_user(username='admin_search_trainer', password='x', is_staff=True)
        self.factory = APIRequestFactory()
        user = get_user_model().objects.create_user(username='neha_search', password='x')
        self.target = Trainer.objects.create(
            user=user, name='Neha Suresh', phone_number='0000000000', place='Chennai',
            default_rate_per_class=Decimal('100'),
        )
        other_user = get_user_model().objects.create_user(username='other_search', password='x')
        Trainer.objects.create(
            user=other_user, name='Someone Else', phone_number='1111111111', place='Mumbai',
            default_rate_per_class=Decimal('100'),
        )

    def _search(self, term):
        request = self.factory.get(f'/api/trainers/?search={term}')
        force_authenticate(request, user=self.admin)
        return TrainerViewSet.as_view({'get': 'list'})(request)

    def test_search_by_name_finds_the_trainer(self):
        response = self._search('neha')
        names = [row['name'] for row in response.data['results']]
        self.assertEqual(names, ['Neha Suresh'])

    def test_search_by_place_finds_the_trainer(self):
        response = self._search('chennai')
        names = [row['name'] for row in response.data['results']]
        self.assertEqual(names, ['Neha Suresh'])

    def test_search_by_trainer_id_finds_the_trainer(self):
        response = self._search(self.target.trainer_id)
        names = [row['name'] for row in response.data['results']]
        self.assertEqual(names, ['Neha Suresh'])


class TrainerHardDeleteBlockedTests(APITestCase):
    """Trainers are only ever archived, never hard-deleted — see
    TrainerViewSet.http_method_names and the archive/unarchive actions.
    """

    def test_delete_is_not_allowed(self):
        admin = get_user_model().objects.create_user(username='admin_no_delete_trainer', password='x', is_staff=True)
        user = get_user_model().objects.create_user(username='keep_me_trainer', password='x')
        trainer = Trainer.objects.create(
            user=user, name='Keep Me', phone_number='0000000000', place='Here', default_rate_per_class=Decimal('100'),
        )
        factory = APIRequestFactory()

        request = factory.delete(f'/api/trainers/{trainer.id}/')
        force_authenticate(request, user=admin)
        response = TrainerViewSet.as_view({'delete': 'destroy'})(request, pk=trainer.id)

        self.assertEqual(response.status_code, 405)
        self.assertTrue(Trainer.objects.filter(id=trainer.id).exists())
