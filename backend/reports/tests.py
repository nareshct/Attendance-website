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

from .views import AttendanceReportView, ClientAttendanceReportView


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
