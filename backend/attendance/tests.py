import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from rest_framework.test import APIRequestFactory, APITestCase, force_authenticate

from billing.models import BillingCycle, ClientInvoiceAdjustment, PayoutAdjustment
from billing.services import get_or_create_cycle
from clients.models import Client
from courses.models import Course
from enrollments.models import Enrollment
from students.models import Student
from trainers.models import Trainer

from .models import Attendance, AttendanceRequest
from .views import AttendanceRequestViewSet


def _make_user(username, is_staff=False):
    return get_user_model().objects.create_user(username=username, password='x', is_staff=is_staff)


def _make_trainer(username, rate):
    user = _make_user(username)
    return Trainer.objects.create(user=user, name=username, phone_number='0000000000', place='Here', default_rate_per_class=rate)


class LateApprovalPricingTests(APITestCase):
    """A late-approved class (from an already-closed cycle) must bill at the
    rate that was in effect on the class's own date, not whatever the rate
    happens to be on the day admin approves it — see
    billing.services.historical_rate() and AttendanceRequestViewSet.approve().
    """

    def setUp(self):
        self.admin = _make_user('admin', is_staff=True)
        self.trainer = _make_trainer('trainer', Decimal('100'))
        self.client_obj = Client.objects.create(company_name='Client Co', contact_phone='123', rate_per_class=Decimal('200'))
        self.course = Course.objects.create(name='Course', total_classes=24, rate_per_class=Decimal('300'))
        self.student = Student.objects.create(name='Kid', grade='5', source_type='B2B', client=self.client_obj)
        self.enrollment = Enrollment.objects.create(
            student=self.student, course=self.course, trainer=self.trainer,
            start_date=datetime.date(2026, 1, 1), class_time='10:00', class_days='MON',
        )
        self.closed_cycle = BillingCycle.objects.create(
            cycle_start=datetime.date(2026, 1, 1), cycle_end=datetime.date(2026, 1, 15), status='closed',
        )
        self.factory = APIRequestFactory()

    def test_approval_uses_the_historical_rate_not_todays(self):
        # The rate changes AFTER the cycle in question already closed.
        self.trainer.default_rate_per_class = Decimal('150')
        self.trainer.save()
        self.client_obj.rate_per_class = Decimal('500')
        self.client_obj.save()

        req = AttendanceRequest.objects.create(
            enrollment=self.enrollment, date=datetime.date(2026, 1, 5), topic_covered='late class',
            requested_by=self.trainer, status='pending',
        )
        request = self.factory.post(f'/api/attendance-requests/{req.id}/approve/')
        force_authenticate(request, user=self.admin)
        response = AttendanceRequestViewSet.as_view({'post': 'approve'})(request, pk=req.id)
        self.assertEqual(response.status_code, 200)

        attendance = Attendance.objects.get(enrollment=self.enrollment, date=datetime.date(2026, 1, 5))
        payout_adj = PayoutAdjustment.objects.get(attendance=attendance)
        invoice_adj = ClientInvoiceAdjustment.objects.get(attendance=attendance)

        current_cycle, _ = get_or_create_cycle()

        self.assertEqual(payout_adj.amount, Decimal('100.00'), 'must use the trainer rate from Jan, not the later 150')
        self.assertEqual(invoice_adj.amount, Decimal('200.00'), 'must use the client rate from Jan, not the later 500')
        self.assertEqual(payout_adj.applied_cycle, current_cycle, "money lands on today's current open cycle")
        self.assertEqual(payout_adj.source_cycle, self.closed_cycle, 'but is attributed back to its real cycle')


class WithdrawnEnrollmentBlocksAttendanceTests(APITestCase):
    def test_cannot_mark_attendance_for_a_withdrawn_enrollment(self):
        trainer = _make_trainer('trainer2', Decimal('100'))
        course = Course.objects.create(name='Course', total_classes=24, rate_per_class=Decimal('300'))
        student = Student.objects.create(name='Kid', grade='5', source_type='B2C')
        enrollment = Enrollment.objects.create(
            student=student, course=course, trainer=trainer, status='withdrawn',
            start_date=datetime.date(2026, 1, 1), class_time='10:00', class_days='MON',
        )

        from .serializers import AttendanceSerializer

        class FakeRequest:
            user = trainer.user

        serializer = AttendanceSerializer(
            data={'enrollment': enrollment.id, 'date': '2026-01-05', 'topic_covered': 'x', 'status': 'present'},
            context={'request': FakeRequest()},
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn('enrollment', serializer.errors)


class DuplicateAndOverCompletionGuardTests(APITestCase):
    """A class only happens once (no duplicate enrollment+date row), and a
    completed enrollment can't take further classes past its course length —
    see AttendanceSerializer.validate()/validate_enrollment().
    """

    def setUp(self):
        self.trainer = _make_trainer('trainer3', Decimal('100'))
        self.course = Course.objects.create(name='Course', total_classes=24, rate_per_class=Decimal('300'))
        self.student = Student.objects.create(name='Kid', grade='5', source_type='B2C')

        class FakeRequest:
            user = self.trainer.user

        self.FakeRequest = FakeRequest

    def _serializer(self, enrollment, date, **overrides):
        from .serializers import AttendanceSerializer

        data = {'enrollment': enrollment.id, 'date': date, 'topic_covered': 'x', 'status': 'present', **overrides}
        return AttendanceSerializer(data=data, context={'request': self.FakeRequest()})

    def test_duplicate_attendance_same_enrollment_and_date_is_rejected(self):
        enrollment = Enrollment.objects.create(
            student=self.student, course=self.course, trainer=self.trainer,
            start_date=datetime.date(2026, 1, 1), class_time='10:00', class_days='MON',
        )
        Attendance.objects.create(enrollment=enrollment, date=datetime.date(2026, 1, 5), status='present', marked_by=self.trainer)

        serializer = self._serializer(enrollment, '2026-01-05')
        self.assertFalse(serializer.is_valid())
        self.assertIn('non_field_errors', serializer.errors)

    def test_different_date_for_same_enrollment_is_allowed(self):
        enrollment = Enrollment.objects.create(
            student=self.student, course=self.course, trainer=self.trainer,
            start_date=datetime.date(2026, 1, 1), class_time='10:00', class_days='MON',
        )
        Attendance.objects.create(enrollment=enrollment, date=datetime.date(2026, 1, 5), status='present', marked_by=self.trainer)

        serializer = self._serializer(enrollment, '2026-01-06')
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_cannot_mark_attendance_for_a_completed_enrollment(self):
        enrollment = Enrollment.objects.create(
            student=self.student, course=self.course, trainer=self.trainer, status='completed',
            classes_completed=24, classes_total=24,
            start_date=datetime.date(2026, 1, 1), class_time='10:00', class_days='MON',
        )

        serializer = self._serializer(enrollment, '2026-02-01')
        self.assertFalse(serializer.is_valid())
        self.assertIn('enrollment', serializer.errors)
