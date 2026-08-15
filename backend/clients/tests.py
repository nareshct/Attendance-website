import io
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from PIL import Image as PILImage
from rest_framework.test import APIClient, APIRequestFactory, APITestCase, force_authenticate

from attendance.models import Attendance
from audit.models import AuditLog
from billing.models import BillingCycle, ClientInvoice, ClientInvoiceAdjustment
from courses.models import Course
from enrollments.models import Enrollment
from students.models import Student
from trainers.models import Trainer

from config.models import AuthToken

from .models import Client, validate_logo_size
from .serializers import ClientSerializer
from .views import (
    ClientContactViewSet,
    ClientCourseRateViewSet,
    ClientViewSet,
    MyClientProfileView,
    MyClientStudentDetailView,
    MyClientStudentsView,
)


def _tiny_png(name='logo.png'):
    buf = io.BytesIO()
    PILImage.new('RGB', (10, 10), color=(37, 99, 235)).save(buf, format='PNG')
    return SimpleUploadedFile(name, buf.getvalue(), content_type='image/png')


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


class InvalidIntQueryParamsReturn400Tests(APITestCase):
    """A non-numeric ?limit=/?client= previously went straight into int()/a queryset
    filter with no validation, raising an unhandled ValueError (500) instead of a
    clean 400 — mirrors TrainerCourseRateViewSet's existing ?trainer= guard."""

    def setUp(self):
        self.admin = get_user_model().objects.create_user(username='admin_bad_query_params', password='x', is_staff=True)
        self.client_obj = Client.objects.create(company_name='Bad Params Co', contact_phone='123', rate_per_class=Decimal('200'))
        self.factory = APIRequestFactory()

    def test_earnings_history_rejects_a_malformed_limit(self):
        request = self.factory.get(f'/api/clients/{self.client_obj.id}/earnings-history/?limit=abc')
        force_authenticate(request, user=self.admin)
        response = ClientViewSet.as_view({'get': 'earnings_history'})(request, pk=self.client_obj.id)
        self.assertEqual(response.status_code, 400)

    def test_client_rates_rejects_a_malformed_client_filter(self):
        request = self.factory.get('/api/client-rates/?client=abc')
        force_authenticate(request, user=self.admin)
        response = ClientCourseRateViewSet.as_view({'get': 'list'})(request)
        self.assertEqual(response.status_code, 400)

    def test_client_contacts_rejects_a_malformed_client_filter(self):
        request = self.factory.get('/api/client-contacts/?client=abc')
        force_authenticate(request, user=self.admin)
        response = ClientContactViewSet.as_view({'get': 'list'})(request)
        self.assertEqual(response.status_code, 400)


class ClientLogoTaglineTests(APITestCase):
    """logo/tagline are purely cosmetic branding shown on a B2B client's
    students' PDFs (see enrollments/report_pdf.py's and certificate_pdf.py's
    _branding_client/_logo_flowable, and the batches equivalents) — this just
    covers that they're actually settable/servable through the API."""

    def _create(self, admin, **extra):
        factory = APIRequestFactory()
        data = {'company_name': 'Logo Co', 'contact_phone': '123', 'rate_per_class': '200', **extra}
        request = factory.post('/api/clients/', data=data, format='multipart')
        force_authenticate(request, user=admin)
        return ClientViewSet.as_view({'post': 'create'})(request)

    def setUp(self):
        self.admin = get_user_model().objects.create_user(username='admin_logo', password='x', is_staff=True)

    def test_can_create_a_client_with_a_logo_and_tagline(self):
        response = self._create(self.admin, logo=_tiny_png(), tagline='Excellence in Coding Education')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(response.data['logo'])
        self.assertEqual(response.data['tagline'], 'Excellence in Coding Education')

    def test_logo_and_tagline_are_optional(self):
        response = self._create(self.admin)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertFalse(response.data['logo'])
        self.assertEqual(response.data['tagline'], '')

    def test_can_update_tagline_and_logo_via_multipart_patch(self):
        client_obj = Client.objects.create(company_name='Patch Co', contact_phone='123', rate_per_class=Decimal('200'))
        factory = APIRequestFactory()
        request = factory.patch(
            f'/api/clients/{client_obj.id}/',
            data={'tagline': 'New Tagline', 'logo': _tiny_png()}, format='multipart',
        )
        force_authenticate(request, user=self.admin)
        response = ClientViewSet.as_view({'patch': 'partial_update'})(request, pk=client_obj.id)
        self.assertEqual(response.status_code, 200, response.data)
        client_obj.refresh_from_db()
        self.assertEqual(client_obj.tagline, 'New Tagline')
        self.assertTrue(client_obj.logo)

    def test_non_image_file_is_rejected(self):
        response = self._create(self.admin, logo=SimpleUploadedFile('not-a-logo.txt', b'hello', content_type='text/plain'))
        self.assertEqual(response.status_code, 400)
        self.assertIn('logo', response.data)

    def test_oversized_logo_is_rejected(self):
        oversized = type('F', (), {'size': 3 * 1024 * 1024})()
        with self.assertRaises(ValidationError):
            validate_logo_size(oversized)

    def test_can_remove_an_existing_logo(self):
        # A multipart PATCH has no native way to send "clear this field" — remove_logo
        # is the explicit signal for it. See ClientSerializer.update().
        client_obj = Client.objects.create(company_name='Remove Logo Co', contact_phone='123', rate_per_class=Decimal('200'))
        client_obj.logo = _tiny_png()
        client_obj.save()
        self.assertTrue(client_obj.logo)

        factory = APIRequestFactory()
        request = factory.patch(
            f'/api/clients/{client_obj.id}/', data={'remove_logo': 'true'}, format='multipart',
        )
        force_authenticate(request, user=self.admin)
        response = ClientViewSet.as_view({'patch': 'partial_update'})(request, pk=client_obj.id)

        self.assertEqual(response.status_code, 200, response.data)
        client_obj.refresh_from_db()
        self.assertFalse(client_obj.logo)

    def test_remove_logo_is_ignored_on_create(self):
        # remove_logo has a default, so DRF always includes it in validated_data even
        # when not sent — must not be passed through to Client.objects.create().
        response = self._create(self.admin, remove_logo='true')
        self.assertEqual(response.status_code, 201, response.data)

    def test_sending_a_new_logo_wins_over_remove_logo_in_the_same_request(self):
        client_obj = Client.objects.create(company_name='Both Fields Co', contact_phone='123', rate_per_class=Decimal('200'))
        client_obj.logo = _tiny_png('old.png')
        client_obj.save()

        factory = APIRequestFactory()
        request = factory.patch(
            f'/api/clients/{client_obj.id}/',
            data={'remove_logo': 'true', 'logo': _tiny_png('new.png')}, format='multipart',
        )
        force_authenticate(request, user=self.admin)
        response = ClientViewSet.as_view({'patch': 'partial_update'})(request, pk=client_obj.id)

        self.assertEqual(response.status_code, 200, response.data)
        client_obj.refresh_from_db()
        self.assertTrue(client_obj.logo)
        self.assertIn('new', client_obj.logo.name)

    def test_omitting_remove_logo_leaves_an_existing_logo_untouched(self):
        client_obj = Client.objects.create(company_name='Untouched Logo Co', contact_phone='123', rate_per_class=Decimal('200'))
        client_obj.logo = _tiny_png()
        client_obj.save()

        factory = APIRequestFactory()
        request = factory.patch(
            f'/api/clients/{client_obj.id}/', data={'tagline': 'Unrelated edit'}, format='multipart',
        )
        force_authenticate(request, user=self.admin)
        response = ClientViewSet.as_view({'patch': 'partial_update'})(request, pk=client_obj.id)

        self.assertEqual(response.status_code, 200, response.data)
        client_obj.refresh_from_db()
        self.assertTrue(client_obj.logo)


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

    def test_archive_and_unarchive_are_written_to_the_audit_log(self):
        admin = get_user_model().objects.create_user(username='admin_client_archive_audit', password='x', is_staff=True)
        client_obj = Client.objects.create(company_name='Audited Co', contact_phone='123', rate_per_class=Decimal('200'))

        self._archive(client_obj, admin)
        factory = APIRequestFactory()
        request = factory.post(f'/api/clients/{client_obj.id}/unarchive/')
        force_authenticate(request, user=admin)
        ClientViewSet.as_view({'post': 'unarchive'})(request, pk=client_obj.id)

        actions = list(AuditLog.objects.values_list('action', flat=True))
        self.assertIn('client_archive', actions)
        self.assertIn('client_unarchive', actions)


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

    def test_closed_cycle_includes_carried_forward_revenue(self):
        """Regression test: a closed cycle's history row must include any
        ClientInvoiceAdjustment applied to it (a late-approved class carried
        forward from an earlier, already-closed cycle) — same amount the real
        ClientInvoice for that cycle was actually generated with. Previously this
        action called client_totals() directly for closed cycles, which excludes
        carried-forward attendance entirely, under-reporting the cycle. See
        billing.tests.MyClientBillingHistoryViewTests's equivalent test for the
        client-facing twin of this same view."""
        admin = get_user_model().objects.create_user(username='admin_earnings_history_carried', password='x', is_staff=True)
        trainer_user = get_user_model().objects.create_user(username='trainer_earnings_history_carried', password='x')
        trainer = Trainer.objects.create(user=trainer_user, name='T Carried', phone_number='1', place='X', default_rate_per_class=Decimal('100'))
        client_obj = Client.objects.create(company_name='Carried History Co', contact_phone='123', rate_per_class=Decimal('200'))
        course = Course.objects.create(name='Carried History Course', total_classes=24)

        source_cycle = BillingCycle.objects.create(cycle_start=date(2026, 1, 1), cycle_end=date(2026, 1, 15), status='closed')
        applied_cycle = BillingCycle.objects.create(cycle_start=date(2026, 1, 16), cycle_end=date(2026, 1, 31), status='closed')
        student = Student.objects.create(name='Carried History Kid', grade='5', source_type='B2B', client=client_obj)
        enrollment = Enrollment.objects.create(
            student=student, course=course, trainer=trainer, start_date=date(2026, 1, 1), class_time='10:00', class_days='MON',
        )
        carried_attendance = Attendance.objects.create(enrollment=enrollment, date=date(2026, 1, 10), status='present', marked_by=trainer)
        ClientInvoiceAdjustment.objects.create(
            client=client_obj, attendance=carried_attendance, source_cycle=source_cycle,
            amount=Decimal('500.00'), trainer_cost=Decimal('250.00'), applied_cycle=applied_cycle,
        )

        factory = APIRequestFactory()
        request = factory.get(f'/api/clients/{client_obj.id}/earnings-history/?limit=20')
        force_authenticate(request, user=admin)
        response = ClientViewSet.as_view({'get': 'earnings_history'})(request, pk=client_obj.id)

        self.assertEqual(response.status_code, 200, response.data)
        row = next(r for r in response.data if r['cycle_start'] == applied_cycle.cycle_start)
        self.assertEqual(row['total_revenue'], Decimal('500.00'))


class ClientLoginProvisioningTests(APITestCase):
    """Client login is optional and granted after the fact — see
    ClientViewSet.set_up_login. Contrast with Trainer, where a login is
    mandatory at creation."""

    def setUp(self):
        self.admin = get_user_model().objects.create_user(username='admin_client_login', password='x', is_staff=True)
        self.client_obj = Client.objects.create(company_name='Set Up Login Co', contact_phone='123', rate_per_class=Decimal('200'))
        self.factory = APIRequestFactory()

    def _set_up_login(self, username='client_user_1', password='ClientPass123!'):
        request = self.factory.post(f'/api/clients/{self.client_obj.id}/set-up-login/', {
            'username': username, 'password': password,
        }, format='json')
        force_authenticate(request, user=self.admin)
        return ClientViewSet.as_view({'post': 'set_up_login'})(request, pk=self.client_obj.id)

    def test_set_up_login_links_a_working_user_account(self):
        response = self._set_up_login()
        self.assertEqual(response.status_code, 200, response.data)
        self.client_obj.refresh_from_db()
        self.assertIsNotNone(self.client_obj.user_id)
        self.assertTrue(self.client_obj.user.check_password('ClientPass123!'))
        self.assertTrue(response.data['has_login'])

    def test_client_login_resolves_to_client_role(self):
        from config.views import LoginView

        self._set_up_login(username='client_role_check', password='ClientPass123!')
        request = self.factory.post('/api/auth/login/', {'username': 'client_role_check', 'password': 'ClientPass123!'}, format='json')
        response = LoginView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['role'], 'client')
        self.assertEqual(response.data['name'], 'Set Up Login Co')

    def test_missing_username_or_password_is_rejected(self):
        request = self.factory.post(f'/api/clients/{self.client_obj.id}/set-up-login/', {'username': 'onlyusername'}, format='json')
        force_authenticate(request, user=self.admin)
        response = ClientViewSet.as_view({'post': 'set_up_login'})(request, pk=self.client_obj.id)
        self.assertEqual(response.status_code, 400)
        self.client_obj.refresh_from_db()
        self.assertIsNone(self.client_obj.user_id)

    def test_duplicate_username_is_rejected(self):
        get_user_model().objects.create_user(username='taken_username', password='x')
        request = self.factory.post(f'/api/clients/{self.client_obj.id}/set-up-login/', {
            'username': 'taken_username', 'password': 'ClientPass123!',
        }, format='json')
        force_authenticate(request, user=self.admin)
        response = ClientViewSet.as_view({'post': 'set_up_login'})(request, pk=self.client_obj.id)
        self.assertEqual(response.status_code, 400)

    def test_calling_set_up_login_again_once_linked_is_rejected(self):
        self._set_up_login()
        response = self._set_up_login(username='client_user_2')
        self.assertEqual(response.status_code, 400)

    def test_archived_client_cannot_be_granted_a_login(self):
        self.client_obj.status = 'archived'
        self.client_obj.save(update_fields=['status'])
        response = self._set_up_login()
        self.assertEqual(response.status_code, 400)
        self.client_obj.refresh_from_db()
        self.assertIsNone(self.client_obj.user_id)


class ClientResetPasswordTests(APITestCase):
    """Mirrors trainers.tests.TrainerResetPasswordTests — see ClientViewSet.reset_password."""

    def setUp(self):
        self.admin = get_user_model().objects.create_user(username='admin_client_reset_pw', password='x', is_staff=True)
        self.user = get_user_model().objects.create_user(username='reset_me_client', password='oldpw12345')
        self.client_obj = Client.objects.create(
            company_name='Reset Me Co', contact_phone='123', rate_per_class=Decimal('200'), user=self.user,
        )
        self.factory = APIRequestFactory()

    def _reset(self, new_password='BrandNewPass456!'):
        request = self.factory.post(f'/api/clients/{self.client_obj.id}/reset-password/', {
            'new_password': new_password,
        }, format='json')
        force_authenticate(request, user=self.admin)
        return ClientViewSet.as_view({'post': 'reset_password'})(request, pk=self.client_obj.id)

    def test_reset_deletes_the_clients_existing_tokens(self):
        token = AuthToken.objects.create(user=self.user)
        response = self._reset()
        self.assertEqual(response.status_code, 204)
        self.assertFalse(AuthToken.objects.filter(key=token.key).exists())

    def test_reset_is_written_to_the_audit_log(self):
        self._reset()
        self.assertTrue(AuditLog.objects.filter(action='client_reset_password').exists())

    def test_reset_on_a_client_with_no_login_yet_fails_cleanly(self):
        no_login_client = Client.objects.create(company_name='No Login Co', contact_phone='123', rate_per_class=Decimal('200'))
        request = self.factory.post(f'/api/clients/{no_login_client.id}/reset-password/', {
            'new_password': 'BrandNewPass456!',
        }, format='json')
        force_authenticate(request, user=self.admin)
        response = ClientViewSet.as_view({'post': 'reset_password'})(request, pk=no_login_client.id)
        self.assertEqual(response.status_code, 400)


class ClientArchiveLoginTests(APITestCase):
    """Mirrors trainers.tests.TrainerArchiveLoginTests — see ClientViewSet.archive/
    unarchive's nullable-safe user.is_active guard (most clients have no login at all,
    unlike Trainer where one is mandatory)."""

    def _archive(self, client_obj, admin):
        factory = APIRequestFactory()
        request = factory.post(f'/api/clients/{client_obj.id}/archive/')
        force_authenticate(request, user=admin)
        return ClientViewSet.as_view({'post': 'archive'})(request, pk=client_obj.id)

    def _unarchive(self, client_obj, admin):
        factory = APIRequestFactory()
        request = factory.post(f'/api/clients/{client_obj.id}/unarchive/')
        force_authenticate(request, user=admin)
        return ClientViewSet.as_view({'post': 'unarchive'})(request, pk=client_obj.id)

    def test_archiving_a_client_with_a_login_deactivates_it_immediately(self):
        admin = get_user_model().objects.create_user(username='admin_archive_client_login', password='x', is_staff=True)
        user = get_user_model().objects.create_user(username='archive_me_client', password='pw12345')
        client_obj = Client.objects.create(
            company_name='Archive Login Co', contact_phone='123', rate_per_class=Decimal('200'), user=user,
        )
        token = AuthToken.objects.create(user=user)
        api_client = APIClient()
        api_client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
        self.assertEqual(api_client.get('/api/auth/me/').status_code, 200)

        response = self._archive(client_obj, admin)

        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertFalse(user.is_active)
        self.assertEqual(api_client.get('/api/auth/me/').status_code, 401)

    def test_unarchiving_reactivates_the_login(self):
        admin = get_user_model().objects.create_user(username='admin_unarchive_client_login', password='x', is_staff=True)
        user = get_user_model().objects.create_user(username='unarchive_me_client', password='pw12345')
        client_obj = Client.objects.create(
            company_name='Unarchive Login Co', contact_phone='123', rate_per_class=Decimal('200'), user=user,
        )
        self._archive(client_obj, admin)
        response = self._unarchive(client_obj, admin)
        self.assertEqual(response.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.is_active)

    def test_archiving_a_client_without_a_login_succeeds_cleanly(self):
        """The common case — most clients never get a login at all (see
        ClientLoginProvisioningTests) — must not crash on None.is_active."""
        admin = get_user_model().objects.create_user(username='admin_archive_no_login', password='x', is_staff=True)
        client_obj = Client.objects.create(company_name='No Login Archive Co', contact_phone='123', rate_per_class=Decimal('200'))

        response = self._archive(client_obj, admin)

        self.assertEqual(response.status_code, 200)
        client_obj.refresh_from_db()
        self.assertEqual(client_obj.status, 'archived')


class MyClientProfileViewTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='profile_view_client', password='x')
        self.client_obj = Client.objects.create(
            company_name='Profile View Co', contact_phone='123', rate_per_class=Decimal('200'), user=self.user,
        )
        self.factory = APIRequestFactory()

    def test_non_client_user_is_forbidden(self):
        other_user = get_user_model().objects.create_user(username='not_a_client_user', password='x')
        request = self.factory.get('/api/my-client-profile/')
        force_authenticate(request, user=other_user)
        response = MyClientProfileView.as_view()(request)
        self.assertEqual(response.status_code, 403)

    def test_client_sees_their_own_profile(self):
        request = self.factory.get('/api/my-client-profile/')
        force_authenticate(request, user=self.user)
        response = MyClientProfileView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['company_name'], 'Profile View Co')
        # ClientSerializer must never leak margin fields even indirectly — this locks
        # in that MyClientProfileView's direct reuse of it stays safe.
        self.assertNotIn('our_earning', response.data)
        self.assertNotIn('trainer_cost', response.data)


class MyClientStudentsViewTests(APITestCase):
    def setUp(self):
        self.trainer_user = get_user_model().objects.create_user(username='students_view_trainer', password='x')
        self.trainer = Trainer.objects.create(
            user=self.trainer_user, name='Students View Trainer', phone_number='1', place='X', default_rate_per_class=Decimal('100'),
        )
        self.course = Course.objects.create(name='Students View Course', total_classes=24)

        self.client_user = get_user_model().objects.create_user(username='students_view_client', password='x')
        self.client_obj = Client.objects.create(
            company_name='Students View Co', contact_phone='123', rate_per_class=Decimal('200'), user=self.client_user,
        )
        self.other_client_user = get_user_model().objects.create_user(username='other_students_view_client', password='x')
        self.other_client = Client.objects.create(
            company_name='Other Students View Co', contact_phone='123', rate_per_class=Decimal('200'), user=self.other_client_user,
        )
        self.factory = APIRequestFactory()

    def _get(self, user):
        request = self.factory.get('/api/my-client-students/')
        force_authenticate(request, user=user)
        return MyClientStudentsView.as_view()(request)

    def test_client_only_sees_their_own_students(self):
        Student.objects.create(name='My Kid', grade='5', source_type='B2B', client=self.client_obj)
        Student.objects.create(name='Their Kid', grade='5', source_type='B2B', client=self.other_client)

        response = self._get(self.client_user)

        self.assertEqual(response.status_code, 200)
        names = [row['name'] for row in response.data]
        self.assertEqual(names, ['My Kid'])

    def test_includes_both_active_and_archived_students_with_their_status(self):
        Student.objects.create(name='Active Kid', grade='5', source_type='B2B', client=self.client_obj, status='active')
        Student.objects.create(name='Archived Kid', grade='5', source_type='B2B', client=self.client_obj, status='archived')

        response = self._get(self.client_user)

        statuses = {row['name']: row['status'] for row in response.data}
        self.assertEqual(statuses, {'Active Kid': 'active', 'Archived Kid': 'archived'})

    def test_enrollment_student_shows_course_batch_and_progress(self):
        student = Student.objects.create(name='Enrolled Kid', grade='5', source_type='B2B', client=self.client_obj)
        Enrollment.objects.create(
            student=student, course=self.course, trainer=self.trainer, start_date=date(2026, 1, 1),
            class_time='10:00', class_days='MON', classes_completed=3, classes_total=24,
        )

        response = self._get(self.client_user)

        row = response.data[0]
        self.assertIn('Students View Course', row['course_batch'])
        self.assertEqual(row['progress'], '3/24')

    def test_batch_only_student_shows_no_fabricated_progress(self):
        from batches.models import Batch, BatchEnrollment

        student = Student.objects.create(name='Batch Kid', grade='5', source_type='B2B', client=self.client_obj)
        batch = Batch.objects.create(
            name='Batch View Batch', course=self.course, total_classes=10, fee_per_student=Decimal('1000'),
            start_date=date(2026, 1, 1),
        )
        BatchEnrollment.objects.create(batch=batch, student=student, joined_date=date(2026, 1, 1))

        response = self._get(self.client_user)

        row = response.data[0]
        self.assertIn('Batch View Batch', row['course_batch'])
        self.assertIsNone(row['progress'])


class MyClientStudentDetailViewTests(APITestCase):
    def setUp(self):
        self.trainer_user = get_user_model().objects.create_user(username='student_detail_trainer', password='x')
        self.trainer = Trainer.objects.create(
            user=self.trainer_user, name='Student Detail Trainer', phone_number='1', place='X', default_rate_per_class=Decimal('100'),
        )
        self.course = Course.objects.create(name='Student Detail Course', total_classes=24)

        self.client_user = get_user_model().objects.create_user(username='student_detail_client', password='x')
        self.client_obj = Client.objects.create(
            company_name='Student Detail Co', contact_phone='123', rate_per_class=Decimal('200'), user=self.client_user,
        )
        self.other_client_user = get_user_model().objects.create_user(username='other_student_detail_client', password='x')
        self.other_client = Client.objects.create(
            company_name='Other Student Detail Co', contact_phone='123', rate_per_class=Decimal('200'), user=self.other_client_user,
        )
        self.factory = APIRequestFactory()

    def _get(self, user, student_id):
        request = self.factory.get(f'/api/my-client-students/{student_id}/')
        force_authenticate(request, user=user)
        return MyClientStudentDetailView.as_view()(request, student_id=student_id)

    def test_client_can_view_their_own_student(self):
        student = Student.objects.create(name='Detail Kid', grade='5', source_type='B2B', client=self.client_obj)
        enrollment = Enrollment.objects.create(
            student=student, course=self.course, trainer=self.trainer, start_date=date(2026, 1, 1),
            class_time='10:00', class_days='MON', classes_completed=2, classes_total=24,
        )
        Attendance.objects.create(enrollment=enrollment, date=date(2026, 1, 5), status='present', marked_by=self.trainer, topic_covered='Loops')

        response = self._get(self.client_user, student.id)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['name'], 'Detail Kid')
        row = response.data['enrollments'][0]
        self.assertEqual(row['course_name'], 'Student Detail Course')
        self.assertEqual(row['classes_completed'], 2)
        self.assertEqual(row['recent_classes'][0]['topic_covered'], 'Loops')

    def test_client_cannot_view_another_clients_student(self):
        other_student = Student.objects.create(name='Not Mine', grade='5', source_type='B2B', client=self.other_client)
        response = self._get(self.client_user, other_student.id)
        self.assertEqual(response.status_code, 404)

    def test_client_cannot_view_a_b2c_student(self):
        b2c_student = Student.objects.create(name='B2C Kid', grade='5', source_type='B2C')
        response = self._get(self.client_user, b2c_student.id)
        self.assertEqual(response.status_code, 404)
