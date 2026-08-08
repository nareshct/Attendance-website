from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIRequestFactory, APITestCase, force_authenticate

from attendance.models import Attendance
from billing.models import BillingCycle, ClientInvoice
from courses.models import Course
from enrollments.models import Enrollment
from students.models import Student
from trainers.models import Trainer

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


class ClientSummaryIncludesArchivedClientsTests(APITestCase):
    """summary()'s total_pending must keep counting an archived client's unpaid
    invoices — that money doesn't stop being owed just because the client was
    archived. Was previously silently dropped since summary() only looped over
    Client.objects.filter(status='active'). See ClientViewSet.summary().
    """

    def test_archived_clients_pending_invoice_still_counts(self):
        admin = get_user_model().objects.create_user(username='admin_summary_archived', password='x', is_staff=True)
        client_obj = Client.objects.create(
            company_name='Archived Co', contact_phone='123', rate_per_class=Decimal('200'), status='archived',
        )
        cycle = BillingCycle.objects.create(
            cycle_start=date.today() - timedelta(days=30), cycle_end=date.today() - timedelta(days=16), status='closed',
        )
        ClientInvoice.objects.create(client=client_obj, cycle=cycle, total_classes=5, total_amount=Decimal('1000.00'), status='pending')

        factory = APIRequestFactory()
        request = factory.get('/api/clients/summary/')
        force_authenticate(request, user=admin)
        response = ClientViewSet.as_view({'get': 'summary'})(request)

        self.assertEqual(response.data['total_pending_amount'], Decimal('1000.00'))


class ClientArchiveBlockersTests(APITestCase):
    """Checklist shown in ArchiveClientModal, and the same categories that hard-
    block ClientViewSet.archive() below — see ClientViewSet.archive_blockers /
    clients.services.get_archive_blockers.
    """

    def test_reports_active_students_and_pending_invoices(self):
        admin = get_user_model().objects.create_user(username='admin_client_blockers', password='x', is_staff=True)
        client_obj = Client.objects.create(company_name='Blocked Co', contact_phone='123', rate_per_class=Decimal('200'))
        trainer_user = get_user_model().objects.create_user(username='trainer_client_blockers', password='x')
        trainer = Trainer.objects.create(user=trainer_user, name='T One', phone_number='1', place='X', default_rate_per_class=Decimal('100'))
        course = Course.objects.create(name='Blockers Course', total_classes=10)
        student = Student.objects.create(name='Active Kid', grade='5', source_type='B2B', client=client_obj, status='active')
        Enrollment.objects.create(
            student=student, course=course, trainer=trainer, start_date=timezone.localdate(),
            status='ongoing', classes_completed=3, classes_total=10,
        )
        cycle = BillingCycle.objects.create(
            cycle_start=date.today() - timedelta(days=30), cycle_end=date.today() - timedelta(days=16), status='closed',
        )
        ClientInvoice.objects.create(client=client_obj, cycle=cycle, total_classes=3, total_amount=Decimal('600.00'), status='pending')

        factory = APIRequestFactory()
        request = factory.get(f'/api/clients/{client_obj.id}/archive-blockers/')
        force_authenticate(request, user=admin)
        response = ClientViewSet.as_view({'get': 'archive_blockers'})(request, pk=client_obj.id)

        self.assertEqual(len(response.data['active_students']), 1)
        self.assertEqual(response.data['active_students'][0]['name'], 'Active Kid')
        self.assertEqual(len(response.data['active_students'][0]['enrollments']), 1)
        enrollment_row = response.data['active_students'][0]['enrollments'][0]
        self.assertEqual(enrollment_row['course_name'], 'Blockers Course')
        self.assertEqual(enrollment_row['status'], 'ongoing')
        self.assertEqual(enrollment_row['classes_completed'], 3)
        self.assertEqual(len(response.data['pending_invoices']), 1)
        self.assertEqual(response.data['pending_invoices'][0]['amount'], Decimal('600.00'))

    def test_reports_nothing_for_a_clean_client(self):
        admin = get_user_model().objects.create_user(username='admin_client_blockers_clean', password='x', is_staff=True)
        client_obj = Client.objects.create(company_name='Clean Co', contact_phone='123', rate_per_class=Decimal('200'))

        factory = APIRequestFactory()
        request = factory.get(f'/api/clients/{client_obj.id}/archive-blockers/')
        force_authenticate(request, user=admin)
        response = ClientViewSet.as_view({'get': 'archive_blockers'})(request, pk=client_obj.id)

        self.assertEqual(response.data['active_students'], [])
        self.assertEqual(response.data['pending_invoices'], [])
        self.assertEqual(response.data['current_cycle_unbilled'], Decimal('0.00'))


class ClientArchiveHardBlockTests(APITestCase):
    """archive() must refuse (mirroring TrainerViewSet.archive) rather than let
    a client with active students or unresolved billing be archived, since
    that would let it slip out of the default active-tab view while it still
    has real, unresolved obligations. See ClientViewSet.archive.
    """

    def _archive(self, client_obj, admin):
        factory = APIRequestFactory()
        request = factory.post(f'/api/clients/{client_obj.id}/archive/')
        force_authenticate(request, user=admin)
        return ClientViewSet.as_view({'post': 'archive'})(request, pk=client_obj.id)

    def test_active_student_blocks_archive(self):
        admin = get_user_model().objects.create_user(username='admin_archive_block_student', password='x', is_staff=True)
        client_obj = Client.objects.create(company_name='Has Student Co', contact_phone='123', rate_per_class=Decimal('200'))
        Student.objects.create(name='Active Kid', grade='5', source_type='B2B', client=client_obj, status='active')

        response = self._archive(client_obj, admin)

        self.assertEqual(response.status_code, 400)
        client_obj.refresh_from_db()
        self.assertEqual(client_obj.status, 'active')

    def test_pending_invoice_blocks_archive(self):
        admin = get_user_model().objects.create_user(username='admin_archive_block_invoice', password='x', is_staff=True)
        client_obj = Client.objects.create(company_name='Has Invoice Co', contact_phone='123', rate_per_class=Decimal('200'))
        cycle = BillingCycle.objects.create(
            cycle_start=date.today() - timedelta(days=30), cycle_end=date.today() - timedelta(days=16), status='closed',
        )
        ClientInvoice.objects.create(client=client_obj, cycle=cycle, total_classes=3, total_amount=Decimal('600.00'), status='pending')

        response = self._archive(client_obj, admin)

        self.assertEqual(response.status_code, 400)
        client_obj.refresh_from_db()
        self.assertEqual(client_obj.status, 'active')

    def test_clean_client_archives_successfully(self):
        admin = get_user_model().objects.create_user(username='admin_archive_clean', password='x', is_staff=True)
        client_obj = Client.objects.create(company_name='Clean Archive Co', contact_phone='123', rate_per_class=Decimal('200'))

        response = self._archive(client_obj, admin)

        self.assertEqual(response.status_code, 200)
        client_obj.refresh_from_db()
        self.assertEqual(client_obj.status, 'archived')


class ClientEarningsHistoryReopenedCycleTests(APITestCase):
    """earnings_history() must use each 'open' cycle's own date range, not
    silently default to today's — normally only today's cycle is ever 'open',
    but BillingCycleViewSet.reopen() can put an old one back to 'open' too.
    See ClientViewSet.earnings_history.
    """

    def test_a_reopened_past_cycle_shows_its_own_totals_not_todays(self):
        from .views import ClientViewSet

        admin = get_user_model().objects.create_user(username='admin_earnings_history_reopen', password='x', is_staff=True)
        trainer_user = get_user_model().objects.create_user(username='trainer_earnings_history_reopen', password='x')
        trainer = Trainer.objects.create(user=trainer_user, name='T Hist', phone_number='1', place='X', default_rate_per_class=Decimal('100'))
        client_obj = Client.objects.create(company_name='History Reopen Co', contact_phone='123', rate_per_class=Decimal('200'))
        course = Course.objects.create(name='History Course', total_classes=24)
        student = Student.objects.create(name='History Kid', grade='5', source_type='B2B', client=client_obj)
        enrollment = Enrollment.objects.create(
            student=student, course=course, trainer=trainer, start_date=date(2026, 1, 1),
            class_time='10:00', class_days='MON',
        )
        past_start, past_end = date(2026, 1, 1), date(2026, 1, 15)
        cycle = BillingCycle.objects.create(cycle_start=past_start, cycle_end=past_end, status='open')
        Attendance.objects.create(enrollment=enrollment, date=date(2026, 1, 5), status='present', marked_by=trainer)

        factory = APIRequestFactory()
        request = factory.get(f'/api/clients/{client_obj.id}/earnings-history/?limit=1')
        force_authenticate(request, user=admin)
        response = ClientViewSet.as_view({'get': 'earnings_history'})(request, pk=client_obj.id)

        self.assertEqual(response.status_code, 200, response.data)
        row = response.data[0]
        self.assertEqual(row['cycle_start'], past_start)
        self.assertEqual(row['total_classes'], 1)
        self.assertEqual(row['total_revenue'], Decimal('200.00'))
