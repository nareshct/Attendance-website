import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory, APITestCase, force_authenticate

from courses.models import Course
from students.models import Student
from trainers.models import Trainer

from .models import Enrollment
from .services import create_payment_plan, trainer_payment_gate, upfront_payment_for
from .views import EnrollmentViewSet


def _make_trainer(username='trainer'):
    user = get_user_model().objects.create_user(username=username, password='x')
    return Trainer.objects.create(user=user, name='Trainer', phone_number='0000000000', place='Here', default_rate_per_class=Decimal('100'))


def _make_enrollment(trainer, source_type='B2C', rate_per_class=Decimal('1000')):
    course = Course.objects.create(name='Course', total_classes=24, rate_per_class=rate_per_class)
    student = Student.objects.create(name='Kid', grade='5', source_type=source_type)
    return Enrollment.objects.create(
        student=student, course=course, trainer=trainer,
        start_date=datetime.date(2026, 1, 1), class_time='10:00', class_days='MON',
    )


class UpfrontPaymentTests(TestCase):
    """The upfront (first) installment is computed from this plan's own
    effective rate (total_amount / classes_total), not the course's flat
    rate_per_class — so a discounted total_amount lowers the upfront amount
    proportionally too. See upfront_payment_for()."""

    def test_two_installments_upfront_is_ten_classes_worth(self):
        # Effective rate 24000/24 = 1000/class -> upfront = 10 x 1000 = 10000.
        self.assertEqual(upfront_payment_for('two_installments', Decimal('24000'), 24), Decimal('10000.00'))

    def test_three_and_four_installments_upfront_is_six_classes_worth(self):
        self.assertEqual(upfront_payment_for('three_installments', Decimal('24000'), 24), Decimal('6000.00'))
        self.assertEqual(upfront_payment_for('four_installments', Decimal('24000'), 24), Decimal('6000.00'))

    def test_discounted_total_lowers_the_upfront_proportionally(self):
        # 20000/24 = 833.3333... effective rate/class; 10 classes' worth rounds to the nearest rupee.
        self.assertEqual(upfront_payment_for('two_installments', Decimal('20000'), 24), Decimal('8333.00'))


class CreatePaymentPlanTests(TestCase):
    """The installments must always sum to exactly total_amount, including
    when the split doesn't divide evenly (rounding is absorbed by the last
    installment)."""

    def setUp(self):
        self.trainer = _make_trainer()
        self.enrollment = _make_enrollment(self.trainer, rate_per_class=Decimal('1000'))

    def test_two_installments_even_split(self):
        # classes_total=24 -> effective rate 15000/24=625; upfront = 10 x 625 = 6250.
        plan = create_payment_plan(self.enrollment, 'two_installments', Decimal('15000'))
        installments = list(plan.installments.all())
        self.assertEqual(len(installments), 2)
        self.assertEqual(installments[0].due_at_classes, None)
        self.assertEqual(installments[0].amount, Decimal('6250.00'))
        self.assertEqual(installments[1].due_at_classes, 10)
        self.assertEqual(installments[1].amount, Decimal('8750.00'))
        self.assertEqual(sum(i.amount for i in installments), Decimal('15000.00'))

    def test_four_installments_uneven_split_absorbed_by_last(self):
        # classes_total=24 -> effective rate 7001/24; upfront (6 classes) rounds to 1750.
        # Remaining 5251 split across 3 -> 1750.33 + 1750.33 + 1750.34.
        plan = create_payment_plan(self.enrollment, 'four_installments', Decimal('7001'))
        installments = list(plan.installments.all())
        self.assertEqual(len(installments), 4)
        self.assertEqual(installments[0].amount, Decimal('1750.00'))
        self.assertEqual(sum(i.amount for i in installments), Decimal('7001.00'), 'rounding must not lose or gain money')
        self.assertEqual(installments[1].amount, Decimal('1750.33'))
        self.assertEqual(installments[2].amount, Decimal('1750.33'))
        self.assertEqual(installments[3].amount, Decimal('1750.34'))

    def test_four_installments_milestones(self):
        plan = create_payment_plan(self.enrollment, 'four_installments', Decimal('8000'))
        due_dates = [i.due_at_classes for i in plan.installments.all()]
        self.assertEqual(due_dates, [None, 6, 11, 18])


class TrainerPaymentGateTests(TestCase):
    """The three-state visibility gate a trainer sees for a B2C enrollment:
    hidden until the first payment is marked paid, blocked once a later
    milestone is reached with that installment still unpaid, clear otherwise."""

    def setUp(self):
        self.trainer = _make_trainer()
        self.enrollment = _make_enrollment(self.trainer, source_type='B2C', rate_per_class=Decimal('1000'))

    def test_no_payment_plan_is_clear(self):
        self.assertEqual(trainer_payment_gate(self.enrollment), 'clear')

    def test_hidden_until_first_payment_marked_paid(self):
        create_payment_plan(self.enrollment, 'three_installments', Decimal('9000'))
        self.assertEqual(trainer_payment_gate(self.enrollment), 'hidden')

    def test_clear_once_first_payment_paid_and_no_milestone_reached(self):
        plan = create_payment_plan(self.enrollment, 'three_installments', Decimal('9000'))
        first = plan.installments.get(sequence=1)
        first.paid_status = 'paid'
        first.save()
        self.assertEqual(trainer_payment_gate(self.enrollment), 'clear')

    def test_blocked_once_milestone_reached_with_next_installment_unpaid(self):
        plan = create_payment_plan(self.enrollment, 'three_installments', Decimal('9000'))
        first = plan.installments.get(sequence=1)
        first.paid_status = 'paid'
        first.save()

        # Second installment is due before class 6 -> reached once classes_completed >= 5.
        self.enrollment.classes_completed = 5
        self.enrollment.save()
        self.assertEqual(trainer_payment_gate(self.enrollment), 'blocked')

        # One class short of the milestone: not yet blocked.
        self.enrollment.classes_completed = 4
        self.enrollment.save()
        self.assertEqual(trainer_payment_gate(self.enrollment), 'clear')


class PaymentInstallmentIsDueSerializerTests(TestCase):
    """PaymentInstallmentSerializer.is_due must match the same milestone check
    used by the dashboard's "installments due" alert and the trainer payment
    gate, so the admin-facing student profile can show which installment is
    actually due right now (see StudentProfileView.jsx)."""

    def setUp(self):
        self.trainer = _make_trainer()
        self.enrollment = _make_enrollment(self.trainer, source_type='B2C', rate_per_class=Decimal('1000'))

    def test_first_installment_is_always_due(self):
        from .serializers import PaymentInstallmentSerializer

        plan = create_payment_plan(self.enrollment, 'three_installments', Decimal('9000'))
        first = plan.installments.get(sequence=1)
        self.assertTrue(PaymentInstallmentSerializer(first).data['is_due'])

    def test_later_installment_not_due_until_its_milestone(self):
        from .serializers import PaymentInstallmentSerializer

        plan = create_payment_plan(self.enrollment, 'three_installments', Decimal('9000'))
        second = plan.installments.get(sequence=2)  # due_at_classes=6

        self.assertFalse(PaymentInstallmentSerializer(second).data['is_due'])

        self.enrollment.classes_completed = 5
        self.enrollment.save()
        self.assertTrue(PaymentInstallmentSerializer(second).data['is_due'])


class B2CEnrollmentDiscountCapTests(APITestCase):
    """A B2C enrollment's discount_percent (applied to the course's standard
    price, rate_per_class x total_classes) may be at most 15 — see
    EnrollmentSerializer's discount_percent field and total_amount_for_discount()."""

    def setUp(self):
        self.admin = get_user_model().objects.create_user(username='admin_discount', password='x', is_staff=True)
        self.trainer = _make_trainer(username='trainer_discount')
        self.course = Course.objects.create(name='Discount Course', total_classes=24, rate_per_class=Decimal('1000'))
        self.student = Student.objects.create(name='Discount Kid', grade='5', source_type='B2C')
        self.factory = APIRequestFactory()

    def _post(self, discount_percent=None, payment_type='two_installments'):
        body = {
            'student': self.student.id, 'course': self.course.id, 'trainer': self.trainer.id,
            'class_time': '10:00', 'class_days': 'MON',
            'payment_type': payment_type,
        }
        if discount_percent is not None:
            body['discount_percent'] = str(discount_percent)
        request = self.factory.post('/api/enrollments/', body, format='json')
        force_authenticate(request, user=self.admin)
        return EnrollmentViewSet.as_view({'post': 'create'})(request)

    def test_exactly_15_percent_off_is_allowed(self):
        response = self._post(discount_percent=Decimal('15'))
        self.assertEqual(response.status_code, 201, response.data)

    def test_more_than_15_percent_off_is_rejected(self):
        response = self._post(discount_percent=Decimal('20'))
        self.assertEqual(response.status_code, 400)

    def test_no_discount_percent_given_defaults_to_no_discount(self):
        response = self._post(discount_percent=None)
        self.assertEqual(response.status_code, 201, response.data)
        from enrollments.models import PaymentPlan
        plan = PaymentPlan.objects.get(enrollment_id=response.data['id'])
        self.assertEqual(plan.total_amount, Decimal('24000.00'))

    def test_discount_is_applied_to_total_amount(self):
        # 24000 standard price, 10% off -> 21600.
        response = self._post(discount_percent=Decimal('10'))
        self.assertEqual(response.status_code, 201, response.data)
        from enrollments.models import PaymentPlan
        plan = PaymentPlan.objects.get(enrollment_id=response.data['id'])
        self.assertEqual(plan.total_amount, Decimal('21600.00'))


class ScheduleConflictOnCreateAndEditTests(APITestCase):
    """Double-booking a trainer at the same day/time must be rejected on enrollment
    create and on a schedule edit — not just on Transfer/Substitute (see
    EnrollmentSerializer.validate() / find_schedule_conflict())."""

    def setUp(self):
        self.admin = get_user_model().objects.create_user(username='admin_conflict', password='x', is_staff=True)
        self.trainer = _make_trainer(username='trainer_conflict')
        self.course = Course.objects.create(name='Conflict Course', total_classes=24, rate_per_class=Decimal('1000'))
        self.factory = APIRequestFactory()

        # An existing ongoing enrollment: Monday 10:00 with this trainer.
        self.existing_student = Student.objects.create(name='Existing Kid', grade='5', source_type='B2C')
        self.existing = Enrollment.objects.create(
            student=self.existing_student, course=self.course, trainer=self.trainer,
            start_date=datetime.date(2026, 1, 1), class_time='10:00', class_days='MON',
        )

    def _create(self, student, class_time, class_days):
        request = self.factory.post('/api/enrollments/', {
            'student': student.id, 'course': self.course.id, 'trainer': self.trainer.id,
            'class_time': class_time, 'class_days': class_days,
            'payment_type': 'two_installments',
        }, format='json')
        force_authenticate(request, user=self.admin)
        return EnrollmentViewSet.as_view({'post': 'create'})(request)

    def test_create_at_same_trainer_time_and_day_is_rejected(self):
        other_student = Student.objects.create(name='New Kid', grade='5', source_type='B2C')
        response = self._create(other_student, '10:00', 'MON')
        self.assertEqual(response.status_code, 400)

    def test_create_at_same_time_but_different_day_is_allowed(self):
        other_student = Student.objects.create(name='New Kid 2', grade='5', source_type='B2C')
        response = self._create(other_student, '10:00', 'TUE')
        self.assertEqual(response.status_code, 201, response.data)

    def test_editing_schedule_into_a_clash_is_rejected(self):
        other_student = Student.objects.create(name='New Kid 3', grade='5', source_type='B2C')
        other = Enrollment.objects.create(
            student=other_student, course=self.course, trainer=self.trainer,
            start_date=datetime.date(2026, 1, 1), class_time='11:00', class_days='WED',
        )
        request = self.factory.patch(f'/api/enrollments/{other.id}/', {
            'class_time': '10:00', 'class_days': 'MON',
        }, format='json')
        force_authenticate(request, user=self.admin)
        response = EnrollmentViewSet.as_view({'patch': 'partial_update'})(request, pk=other.id)
        self.assertEqual(response.status_code, 400)

    def test_editing_the_existing_enrollment_itself_is_not_a_self_conflict(self):
        # Re-saving the same enrollment with its own unchanged time/day must not
        # trip the conflict check against itself.
        request = self.factory.patch(f'/api/enrollments/{self.existing.id}/', {
            'class_time': '10:00', 'class_days': 'MON',
        }, format='json')
        force_authenticate(request, user=self.admin)
        response = EnrollmentViewSet.as_view({'patch': 'partial_update'})(request, pk=self.existing.id)
        self.assertEqual(response.status_code, 200, response.data)


class EnrollmentSearchTests(APITestCase):
    """?search= must match student name OR course name OR trainer name
    server-side (see EnrollmentViewSet.search_fields), so a match is found
    regardless of which page it would otherwise fall on.
    """

    def setUp(self):
        self.admin = get_user_model().objects.create_user(username='admin_search_enrollment', password='x', is_staff=True)
        self.trainer = _make_trainer(username='trainer_search')
        self.factory = APIRequestFactory()
        self.enrollment = _make_enrollment(self.trainer, rate_per_class=Decimal('1000'))
        self.enrollment.student.name = 'Ishani Warrier'
        self.enrollment.student.save(update_fields=['name'])

    def _search(self, term):
        request = self.factory.get(f'/api/enrollments/?search={term}')
        force_authenticate(request, user=self.admin)
        return EnrollmentViewSet.as_view({'get': 'list'})(request)

    def test_search_by_student_name_finds_the_enrollment(self):
        response = self._search('warrier')
        student_names = [row['student_name'] for row in response.data['results']]
        self.assertIn('Ishani Warrier', student_names)

    def test_search_with_no_match_returns_empty(self):
        response = self._search('nonexistent-name-xyz')
        self.assertEqual(response.data['results'], [])
