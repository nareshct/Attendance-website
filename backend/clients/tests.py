from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory, APITestCase, force_authenticate

from .models import Client
from .serializers import ClientSerializer
from .views import ClientViewSet


class ClientHardDeleteBlockedTests(APITestCase):
    """Clients are only ever archived, never hard-deleted — see
    ClientViewSet.http_method_names and the archive/unarchive actions.
    """

    def test_delete_is_not_allowed(self):
        admin = get_user_model().objects.create_user(username='admin_no_delete_client', password='x', is_staff=True)
        client_obj = Client.objects.create(company_name='Keep Me Inc', contact_phone='123', rate_per_class=Decimal('200'))
        factory = APIRequestFactory()

        request = factory.delete(f'/api/clients/{client_obj.id}/')
        force_authenticate(request, user=admin)
        response = ClientViewSet.as_view({'delete': 'destroy'})(request, pk=client_obj.id)

        self.assertEqual(response.status_code, 405)
        self.assertTrue(Client.objects.filter(id=client_obj.id).exists())


class ClientRateValidationTests(APITestCase):
    def test_negative_rate_per_class_is_rejected(self):
        serializer = ClientSerializer(data={'company_name': 'Bad Co', 'contact_phone': '123', 'rate_per_class': '-500.00'})
        self.assertFalse(serializer.is_valid())
        self.assertIn('rate_per_class', serializer.errors)
