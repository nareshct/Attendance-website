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
from .views import AttendanceRequestViewSet, AttendanceViewSet


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


class DateRangeFilterTests(APITestCase):
    """?start=/?end= (both inclusive) let a caller ask for just the window it
    needs instead of a trainer's entire history — see AttendanceViewSet.
    get_queryset(). Added so MarkAttendancePage/MyEarningsPage/TrainerDashboard
    could stop fetching everything unbounded, which broke outright once a
    trainer's lifetime total passed the API's page size.
    """

    def setUp(self):
        self.trainer = _make_trainer('trainer_date_range', Decimal('100'))
        course = Course.objects.create(name='Range Course', total_classes=24, rate_per_class=Decimal('300'))
        student = Student.objects.create(name='Range Kid', grade='5', source_type='B2C')
        self.enrollment = Enrollment.objects.create(
            student=student, course=course, trainer=self.trainer,
            start_date=datetime.date(2026, 1, 1), class_time='10:00', class_days='MON',
        )
        for day in (1, 10, 20):
            Attendance.objects.create(
                enrollment=self.enrollment, date=datetime.date(2026, 1, day), status='present', marked_by=self.trainer,
            )
        self.factory = APIRequestFactory()

    def _list(self, query=''):
        request = self.factory.get(f'/api/attendance/{query}')
        force_authenticate(request, user=self.trainer.user)
        response = AttendanceViewSet.as_view({'get': 'list'})(request)
        return [row['date'] for row in response.data['results']]

    def test_no_params_returns_everything(self):
        self.assertEqual(len(self._list()), 3)

    def test_start_excludes_earlier_dates(self):
        dates = self._list('?start=2026-01-10')
        self.assertEqual(sorted(dates), ['2026-01-10', '2026-01-20'])

    def test_end_excludes_later_dates(self):
        dates = self._list('?end=2026-01-10')
        self.assertEqual(sorted(dates), ['2026-01-01', '2026-01-10'])

    def test_start_and_end_together_bound_both_sides(self):
        dates = self._list('?start=2026-01-05&end=2026-01-15')
        self.assertEqual(dates, ['2026-01-10'])


class CrossTrainerEditBlockedTests(APITestCase):
    """A trainer can only edit/delete a class they personally marked_by —
    get_queryset()'s ?enrollment= branch deliberately broadens *read* access
    to a whole enrollment's history (including sessions from before a
    transfer), but that must never extend to write access. See
    AttendanceViewSet.perform_update/perform_destroy.
    """

    def setUp(self):
        self.trainer_a = _make_trainer('trainer_cross_a', Decimal('100'))
        self.trainer_b = _make_trainer('trainer_cross_b', Decimal('100'))
        course = Course.objects.create(name='Cross Course', total_classes=24, rate_per_class=Decimal('300'))
        student = Student.objects.create(name='Cross Kid', grade='5', source_type='B2C')
        # Enrollment now belongs to trainer_b (simulating a transfer already happened),
        # but this specific class was marked_by trainer_a beforehand.
        self.enrollment = Enrollment.objects.create(
            student=student, course=course, trainer=self.trainer_b,
            start_date=datetime.date(2026, 1, 1), class_time='10:00', class_days='MON',
        )
        self.attendance = Attendance.objects.create(
            enrollment=self.enrollment, date=datetime.date(2026, 1, 5), status='present', marked_by=self.trainer_a,
        )
        self.factory = APIRequestFactory()

    def test_new_trainer_cannot_edit_a_class_marked_by_the_previous_trainer(self):
        request = self.factory.patch(
            f'/api/attendance/{self.attendance.id}/?enrollment={self.enrollment.id}',
            {'topic_covered': 'hijacked'}, format='json',
        )
        force_authenticate(request, user=self.trainer_b.user)
        response = AttendanceViewSet.as_view({'patch': 'partial_update'})(request, pk=self.attendance.id)

        self.assertEqual(response.status_code, 403)
        self.attendance.refresh_from_db()
        self.assertNotEqual(self.attendance.topic_covered, 'hijacked')

    def test_new_trainer_cannot_delete_a_class_marked_by_the_previous_trainer(self):
        request = self.factory.delete(f'/api/attendance/{self.attendance.id}/?enrollment={self.enrollment.id}')
        force_authenticate(request, user=self.trainer_b.user)
        response = AttendanceViewSet.as_view({'delete': 'destroy'})(request, pk=self.attendance.id)

        self.assertEqual(response.status_code, 403)
        self.assertTrue(Attendance.objects.filter(id=self.attendance.id).exists())

    def test_the_original_trainer_can_still_edit_their_own_class(self):
        # No ?enrollment= here — that branch of get_queryset() scopes to the
        # enrollment's *current* trainer (trainer_b, post-transfer), so trainer_a
        # reaches their own record the normal way instead: the marked_by fallback
        # branch, exactly how MarkAttendancePage.jsx's real edit/delete calls work.
        request = self.factory.patch(
            f'/api/attendance/{self.attendance.id}/',
            {'topic_covered': 'updated by original trainer'}, format='json',
        )
        force_authenticate(request, user=self.trainer_a.user)
        response = AttendanceViewSet.as_view({'patch': 'partial_update'})(request, pk=self.attendance.id)

        self.assertEqual(response.status_code, 200, response.data)
        self.attendance.refresh_from_db()
        self.assertEqual(self.attendance.topic_covered, 'updated by original trainer')


class DuplicatePendingAttendanceRequestTests(APITestCase):
    """Two pending AttendanceRequests for the same (enrollment, date) must never
    both reach approve() — Attendance has a UniqueConstraint on that pair, so
    the second approval would otherwise crash with an unhandled IntegrityError
    instead of a normal 400. See AttendanceViewSet.create()'s dedupe check and
    AttendanceRequestViewSet.approve()'s guard.
    """

    def setUp(self):
        self.trainer = _make_trainer('trainer_dup_pending', Decimal('100'))
        course = Course.objects.create(name='Dup Course', total_classes=24, rate_per_class=Decimal('300'))
        student = Student.objects.create(name='Dup Kid', grade='5', source_type='B2C')
        self.enrollment = Enrollment.objects.create(
            student=student, course=course, trainer=self.trainer,
            start_date=datetime.date(2026, 1, 1), class_time='10:00', class_days='MON',
        )
        BillingCycle.objects.create(
            cycle_start=datetime.date(2026, 1, 1), cycle_end=datetime.date(2026, 1, 15), status='closed',
        )
        self.factory = APIRequestFactory()

    def _submit(self):
        request = self.factory.post('/api/attendance/', {
            'enrollment': self.enrollment.id, 'date': '2026-01-05', 'topic_covered': 'late', 'status': 'present',
        }, format='json')
        force_authenticate(request, user=self.trainer.user)
        return AttendanceViewSet.as_view({'post': 'create'})(request)

    def test_resubmitting_the_same_closed_cycle_date_reuses_the_pending_request(self):
        first = self._submit()
        self.assertEqual(first.status_code, 202)
        second = self._submit()
        self.assertEqual(second.status_code, 202)
        self.assertEqual(first.data['request']['id'], second.data['request']['id'])
        self.assertEqual(
            AttendanceRequest.objects.filter(enrollment=self.enrollment, date=datetime.date(2026, 1, 5)).count(), 1,
        )

    def test_approving_when_a_class_already_exists_returns_400_not_a_crash(self):
        req = AttendanceRequest.objects.create(
            enrollment=self.enrollment, date=datetime.date(2026, 1, 5), topic_covered='dup',
            requested_by=self.trainer, status='pending',
        )
        Attendance.objects.create(
            enrollment=self.enrollment, date=datetime.date(2026, 1, 5), status='present', marked_by=self.trainer,
        )

        admin = _make_user('admin_dup_pending', is_staff=True)
        request = self.factory.post(f'/api/attendance-requests/{req.id}/approve/')
        force_authenticate(request, user=admin)
        response = AttendanceRequestViewSet.as_view({'post': 'approve'})(request, pk=req.id)

        self.assertEqual(response.status_code, 400)
        req.refresh_from_db()
        self.assertEqual(req.status, 'pending')
