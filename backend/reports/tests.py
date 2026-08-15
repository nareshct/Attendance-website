import csv
import datetime
import io
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory, APITestCase, force_authenticate

from attendance.models import Attendance
from clients.models import Client
from courses.models import Course
from enrollments.models import Enrollment
from students.models import Student
from trainers.models import Trainer

from .views import (
    AttendanceReportView,
    ClientAttendanceReportView,
    MyAttendanceReportView,
    MyClientAttendanceReportView,
    PayoutsReportView,
)


class CsvFormulaInjectionEscapedTests(APITestCase):
    """A trainer-typed topic_covered starting with =, +, -, or @ must not reach
    the CSV cell as-is — Excel/Sheets treats a leading one of those characters
    as the start of a formula, so an admin merely opening the exported file
    could trigger it. See reports.views.csv_safe().
    """

    def setUp(self):
        self.admin = get_user_model().objects.create_user(username='admin_csv_injection', password='x', is_staff=True)
        trainer_user = get_user_model().objects.create_user(username='trainer_csv_injection', password='x')
        self.trainer = Trainer.objects.create(
            user=trainer_user, name='CSV Trainer', phone_number='0000000000', place='Here',
            default_rate_per_class=Decimal('100'),
        )
        self.client_obj = Client.objects.create(company_name='CSV Client Co', contact_phone='123', rate_per_class=Decimal('200'))
        course = Course.objects.create(name='CSV Course', total_classes=24, rate_per_class=Decimal('300'))
        self.student = Student.objects.create(name='CSV Kid', grade='5', source_type='B2B', client=self.client_obj)
        self.enrollment = Enrollment.objects.create(
            student=self.student, course=course, trainer=self.trainer,
            start_date=datetime.date(2026, 1, 1), class_time='10:00', class_days='MON',
        )
        Attendance.objects.create(
            enrollment=self.enrollment, date=datetime.date(2026, 1, 5), status='present',
            marked_by=self.trainer, topic_covered='=SUM(A1:A9)',
        )
        self.factory = APIRequestFactory()

    def _rows(self, response):
        return list(csv.reader(io.StringIO(response.content.decode())))

    def test_client_attendance_report_escapes_a_formula_looking_topic(self):
        request = self.factory.get(f'/api/reports/client/{self.client_obj.id}/attendance/')
        force_authenticate(request, user=self.admin)
        response = ClientAttendanceReportView.as_view()(request, client_id=self.client_obj.id)

        rows = self._rows(response)
        topic_cell = rows[1][-1]
        self.assertTrue(topic_cell.startswith("'"), topic_cell)
        self.assertEqual(topic_cell, "'=SUM(A1:A9)")

    def test_attendance_report_escapes_a_formula_looking_topic(self):
        request = self.factory.get('/api/reports/attendance/')
        force_authenticate(request, user=self.admin)
        response = AttendanceReportView.as_view()(request)

        rows = self._rows(response)
        topic_cell = rows[1][-1]
        self.assertTrue(topic_cell.startswith("'"), topic_cell)
        self.assertEqual(topic_cell, "'=SUM(A1:A9)")

    def test_ordinary_topic_is_left_unchanged(self):
        Attendance.objects.create(
            enrollment=self.enrollment, date=datetime.date(2026, 1, 6), status='present',
            marked_by=self.trainer, topic_covered='Loops and conditionals',
        )
        request = self.factory.get('/api/reports/attendance/')
        force_authenticate(request, user=self.admin)
        response = AttendanceReportView.as_view()(request)

        rows = self._rows(response)
        topics = [row[-1] for row in rows[1:]]
        self.assertIn('Loops and conditionals', topics)


class InvalidFilterParamsReturn400Tests(APITestCase):
    """trainer/cycle/start/end query params previously went straight into a queryset
    filter with no validation — a malformed value raised an unhandled ValueError/
    ValidationError (500) instead of a clean 400, since these are plain APIViews and
    DRF's exception handler never sees a built-in exception like that."""

    def setUp(self):
        self.admin = get_user_model().objects.create_user(username='admin_bad_filters', password='x', is_staff=True)
        self.client_obj = Client.objects.create(company_name='Bad Filter Client', contact_phone='123', rate_per_class=Decimal('200'))
        self.factory = APIRequestFactory()

    def test_payouts_report_rejects_a_non_numeric_trainer_id(self):
        request = self.factory.get('/api/reports/payouts/?trainer=not-a-number')
        force_authenticate(request, user=self.admin)
        response = PayoutsReportView.as_view()(request)
        self.assertEqual(response.status_code, 400)

    def test_payouts_report_rejects_a_non_numeric_cycle_id(self):
        request = self.factory.get('/api/reports/payouts/?cycle=not-a-number')
        force_authenticate(request, user=self.admin)
        response = PayoutsReportView.as_view()(request)
        self.assertEqual(response.status_code, 400)

    def test_attendance_report_rejects_a_non_numeric_trainer_id(self):
        request = self.factory.get('/api/reports/attendance/?trainer=not-a-number')
        force_authenticate(request, user=self.admin)
        response = AttendanceReportView.as_view()(request)
        self.assertEqual(response.status_code, 400)

    def test_attendance_report_rejects_a_malformed_start_date(self):
        request = self.factory.get('/api/reports/attendance/?start=not-a-date')
        force_authenticate(request, user=self.admin)
        response = AttendanceReportView.as_view()(request)
        self.assertEqual(response.status_code, 400)

    def test_client_attendance_report_rejects_a_malformed_end_date(self):
        request = self.factory.get(f'/api/reports/client/{self.client_obj.id}/attendance/?end=not-a-date')
        force_authenticate(request, user=self.admin)
        response = ClientAttendanceReportView.as_view()(request, client_id=self.client_obj.id)
        self.assertEqual(response.status_code, 400)

    def test_attendance_report_still_works_with_valid_params(self):
        request = self.factory.get('/api/reports/attendance/?start=2026-01-01&end=2026-01-31')
        force_authenticate(request, user=self.admin)
        response = AttendanceReportView.as_view()(request)
        self.assertEqual(response.status_code, 200)


class MyClientAttendanceReportViewTests(APITestCase):
    """Client-facing self-service CSV export — see MyClientAttendanceReportView."""

    def _rows(self, response):
        return list(csv.reader(io.StringIO(response.content.decode())))

    def setUp(self):
        trainer_user = get_user_model().objects.create_user(username='my_client_csv_trainer', password='x')
        self.trainer = Trainer.objects.create(
            user=trainer_user, name='My Client CSV Trainer', phone_number='1', place='X', default_rate_per_class=Decimal('100'),
        )
        self.course = Course.objects.create(name='My Client CSV Course', total_classes=24)

        self.client_user = get_user_model().objects.create_user(username='my_client_csv_client', password='x')
        self.client_obj = Client.objects.create(
            company_name='My Client CSV Co', contact_phone='123', rate_per_class=Decimal('200'), user=self.client_user,
        )
        self.other_client_user = get_user_model().objects.create_user(username='other_my_client_csv_client', password='x')
        self.other_client = Client.objects.create(
            company_name='Other My Client CSV Co', contact_phone='123', rate_per_class=Decimal('200'), user=self.other_client_user,
        )

        self.student = Student.objects.create(name='CSV Export Kid', grade='5', source_type='B2B', client=self.client_obj)
        self.enrollment = Enrollment.objects.create(
            student=self.student, course=self.course, trainer=self.trainer,
            start_date=datetime.date(2026, 1, 1), class_time='10:00', class_days='MON',
        )
        Attendance.objects.create(
            enrollment=self.enrollment, date=datetime.date(2026, 1, 5), status='present',
            marked_by=self.trainer, topic_covered='Loops',
        )

        other_student = Student.objects.create(name='Not Mine CSV Kid', grade='5', source_type='B2B', client=self.other_client)
        other_enrollment = Enrollment.objects.create(
            student=other_student, course=self.course, trainer=self.trainer,
            start_date=datetime.date(2026, 1, 1), class_time='10:00', class_days='MON',
        )
        Attendance.objects.create(
            enrollment=other_enrollment, date=datetime.date(2026, 1, 5), status='present', marked_by=self.trainer,
        )

        self.factory = APIRequestFactory()

    def test_non_client_user_is_forbidden(self):
        stranger = get_user_model().objects.create_user(username='my_client_csv_stranger', password='x')
        request = self.factory.get('/api/reports/my-client-attendance/')
        force_authenticate(request, user=stranger)
        response = MyClientAttendanceReportView.as_view()(request)
        self.assertEqual(response.status_code, 403)

    def test_client_only_sees_their_own_students_in_the_csv(self):
        request = self.factory.get('/api/reports/my-client-attendance/')
        force_authenticate(request, user=self.client_user)
        response = MyClientAttendanceReportView.as_view()(request)

        rows = self._rows(response)
        names = [row[1] for row in rows[1:]]
        self.assertEqual(names, ['CSV Export Kid'])

    def test_date_range_filters_the_csv(self):
        request = self.factory.get('/api/reports/my-client-attendance/?start=2026-02-01&end=2026-02-28')
        force_authenticate(request, user=self.client_user)
        response = MyClientAttendanceReportView.as_view()(request)

        rows = self._rows(response)
        self.assertEqual(len(rows), 1)  # header only

    def test_rejects_a_malformed_date(self):
        request = self.factory.get('/api/reports/my-client-attendance/?start=not-a-date')
        force_authenticate(request, user=self.client_user)
        response = MyClientAttendanceReportView.as_view()(request)
        self.assertEqual(response.status_code, 400)


class MyAttendanceReportViewTests(APITestCase):
    """Trainer-facing self-service CSV export — see MyAttendanceReportView."""

    def _rows(self, response):
        return list(csv.reader(io.StringIO(response.content.decode())))

    def setUp(self):
        trainer_user = get_user_model().objects.create_user(username='my_attendance_csv_trainer', password='x')
        self.trainer = Trainer.objects.create(
            user=trainer_user, name='My Attendance CSV Trainer', phone_number='1', place='X', default_rate_per_class=Decimal('100'),
        )
        other_trainer_user = get_user_model().objects.create_user(username='other_my_attendance_csv_trainer', password='x')
        self.other_trainer = Trainer.objects.create(
            user=other_trainer_user, name='Other Trainer', phone_number='2', place='X', default_rate_per_class=Decimal('100'),
        )
        self.course = Course.objects.create(name='My Attendance CSV Course', total_classes=24)
        client_obj = Client.objects.create(company_name='My Attendance CSV Co', contact_phone='123', rate_per_class=Decimal('200'))
        self.student = Student.objects.create(name='Attendance CSV Kid', grade='5', source_type='B2B', client=client_obj)

        self.enrollment = Enrollment.objects.create(
            student=self.student, course=self.course, trainer=self.trainer,
            start_date=datetime.date(2026, 1, 1), class_time='10:00', class_days='MON',
        )
        Attendance.objects.create(
            enrollment=self.enrollment, date=datetime.date(2026, 1, 5), status='present',
            marked_by=self.trainer, topic_covered='Functions',
        )
        # Marked by a different trainer (e.g. a substitute) — must not appear in this
        # trainer's own CSV even though it's the same enrollment.
        Attendance.objects.create(
            enrollment=self.enrollment, date=datetime.date(2026, 1, 6), status='present', marked_by=self.other_trainer,
        )

        self.factory = APIRequestFactory()

    def test_non_trainer_user_is_forbidden(self):
        stranger = get_user_model().objects.create_user(username='my_attendance_csv_stranger', password='x', is_staff=True)
        request = self.factory.get('/api/reports/my-attendance/')
        force_authenticate(request, user=stranger)
        response = MyAttendanceReportView.as_view()(request)
        self.assertEqual(response.status_code, 403)

    def test_trainer_only_sees_their_own_classes_in_the_csv(self):
        request = self.factory.get('/api/reports/my-attendance/')
        force_authenticate(request, user=self.trainer.user)
        response = MyAttendanceReportView.as_view()(request)

        rows = self._rows(response)
        self.assertEqual(len(rows), 2)  # header + the one class this trainer marked
        self.assertEqual(rows[1][0], '2026-01-05')

    def test_date_range_filters_the_csv(self):
        request = self.factory.get('/api/reports/my-attendance/?start=2026-02-01&end=2026-02-28')
        force_authenticate(request, user=self.trainer.user)
        response = MyAttendanceReportView.as_view()(request)

        rows = self._rows(response)
        self.assertEqual(len(rows), 1)  # header only

    def test_rejects_a_malformed_date(self):
        request = self.factory.get('/api/reports/my-attendance/?end=not-a-date')
        force_authenticate(request, user=self.trainer.user)
        response = MyAttendanceReportView.as_view()(request)
        self.assertEqual(response.status_code, 400)
