import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory, APITestCase, force_authenticate

from attendance.views import AttendanceViewSet
from audit.models import AuditLog
from courses.models import Course
from students.models import Student
from trainers.models import Trainer

from .certificate_pdf import render_certificate_pdf
from .models import Enrollment, SubstituteAssignment
from .report_pdf import render_student_report_pdf
from .services import create_payment_plan, trainer_payment_gate, upfront_payment_for
from .views import EnrollmentViewSet, MyStudentsView, PaymentInstallmentViewSet


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


class PaymentPlanRecalculationTests(APITestCase):
    """Editing an ongoing B2C enrollment's classes_total must reprice its PaymentPlan
    (see EnrollmentSerializer.update() / services.recalculate_payment_plan()) — already
    paid installments are frozen, and the difference is spread across the still-pending
    ones, rounding remainder on the last."""

    def setUp(self):
        self.admin = get_user_model().objects.create_user(username='admin_recalc', password='x', is_staff=True)
        self.trainer = _make_trainer(username='trainer_recalc')
        self.factory = APIRequestFactory()

    def _patch_classes_total(self, enrollment, classes_total):
        request = self.factory.patch(
            f'/api/enrollments/{enrollment.id}/', {'classes_total': classes_total}, format='json',
        )
        force_authenticate(request, user=self.admin)
        return EnrollmentViewSet.as_view({'patch': 'partial_update'})(request, pk=enrollment.id)

    def test_extending_classes_total_spreads_difference_across_unpaid_with_rounding(self):
        # rate 833.33/class chosen so the recalculated difference doesn't split evenly
        # in cents, to exercise the remainder-on-last rounding.
        enrollment = _make_enrollment(self.trainer, rate_per_class=Decimal('833.33'))
        plan = create_payment_plan(enrollment, 'three_installments', Decimal('19999.92'))
        first, second, third = plan.installments.order_by('sequence')
        first.paid_status = 'paid'
        first.save(update_fields=['paid_status'])

        response = self._patch_classes_total(enrollment, 29)
        self.assertEqual(response.status_code, 200, response.data)

        plan.refresh_from_db()
        first.refresh_from_db()
        second.refresh_from_db()
        third.refresh_from_db()

        self.assertEqual(plan.total_amount, Decimal('24166.57'))
        # Paid installment is untouched — same amount, same status.
        self.assertEqual(first.amount, Decimal('5000.00'))
        self.assertEqual(first.paid_status, 'paid')
        # The 4166.65 increase splits across the two unpaid installments, with the
        # 1-paisa rounding remainder landing on the last one.
        self.assertEqual(second.amount, Decimal('9583.29'))
        self.assertEqual(third.amount, Decimal('9583.28'))
        self.assertEqual(first.amount + second.amount + third.amount, plan.total_amount)

    def test_fully_paid_plan_rejects_classes_total_edit(self):
        enrollment = _make_enrollment(self.trainer, rate_per_class=Decimal('1000'))
        plan = create_payment_plan(enrollment, 'two_installments', Decimal('24000'))
        for installment in plan.installments.all():
            installment.paid_status = 'paid'
            installment.save(update_fields=['paid_status'])

        response = self._patch_classes_total(enrollment, 28)
        self.assertEqual(response.status_code, 400)
        self.assertIn('fully paid', str(response.data))

        # Nothing changed — the whole update rolled back.
        plan.refresh_from_db()
        enrollment.refresh_from_db()
        self.assertEqual(plan.total_amount, Decimal('24000.00'))
        self.assertEqual(enrollment.classes_total, 24)

    def test_shrinking_below_pending_total_is_rejected(self):
        enrollment = _make_enrollment(self.trainer, rate_per_class=Decimal('1000'))
        plan = create_payment_plan(enrollment, 'two_installments', Decimal('24000'))
        first, second = plan.installments.order_by('sequence')
        first.paid_status = 'paid'
        first.save(update_fields=['paid_status'])
        # unpaid = second, worth 14000.00

        # New total at 1 class would be 1000 — reducing from 24000 needs 23000 out of
        # only 14000 of pending installments, which would floor below 0. Must be rejected.
        response = self._patch_classes_total(enrollment, 1)
        self.assertEqual(response.status_code, 400)
        self.assertIn('Handle this manually', str(response.data))

        plan.refresh_from_db()
        second.refresh_from_db()
        enrollment.refresh_from_db()
        self.assertEqual(plan.total_amount, Decimal('24000.00'))
        self.assertEqual(second.amount, Decimal('14000.00'))
        self.assertEqual(enrollment.classes_total, 24)

    def test_shrinking_within_pending_total_succeeds(self):
        enrollment = _make_enrollment(self.trainer, rate_per_class=Decimal('1000'))
        plan = create_payment_plan(enrollment, 'two_installments', Decimal('24000'))
        first, second = plan.installments.order_by('sequence')
        first.paid_status = 'paid'
        first.save(update_fields=['paid_status'])
        # unpaid = second, worth 14000.00

        # New total at 20 classes is 20000 — a 4000 reduction, comfortably absorbed by
        # the single 14000 pending installment.
        response = self._patch_classes_total(enrollment, 20)
        self.assertEqual(response.status_code, 200, response.data)

        plan.refresh_from_db()
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(plan.total_amount, Decimal('20000.00'))
        self.assertEqual(first.amount, Decimal('10000.00'))
        self.assertEqual(first.paid_status, 'paid')
        self.assertEqual(second.amount, Decimal('10000.00'))


class EnrollmentStatusSyncOnClassesTotalChangeTests(APITestCase):
    """Extending a completed enrollment's batch count must reopen it (status back to
    'ongoing') so the trainer can mark the newly added classes — see
    Enrollment.sync_completion_status() and
    services.sync_enrollment_status_after_classes_total_change(). Shrinking it while
    classes_completed still meets the new, lower total must leave status untouched."""

    def setUp(self):
        self.admin = get_user_model().objects.create_user(username='admin_status_sync', password='x', is_staff=True)
        self.trainer = _make_trainer(username='trainer_status_sync')
        self.course = Course.objects.create(name='Status Sync Course', total_classes=24, rate_per_class=Decimal('1000'))
        self.student = Student.objects.create(name='Status Sync Kid', grade='5', source_type='B2C')
        self.factory = APIRequestFactory()

    def _patch_classes_total(self, enrollment, classes_total):
        request = self.factory.patch(
            f'/api/enrollments/{enrollment.id}/', {'classes_total': classes_total}, format='json',
        )
        force_authenticate(request, user=self.admin)
        return EnrollmentViewSet.as_view({'patch': 'partial_update'})(request, pk=enrollment.id)

    def test_extending_a_completed_enrollment_reopens_it_and_allows_marking_the_new_class(self):
        enrollment = Enrollment.objects.create(
            student=self.student, course=self.course, trainer=self.trainer, status='completed',
            classes_completed=24, classes_total=24,
            start_date=datetime.date(2026, 1, 1), class_time='10:00', class_days='MON',
        )

        response = self._patch_classes_total(enrollment, 28)
        self.assertEqual(response.status_code, 200, response.data)

        enrollment.refresh_from_db()
        self.assertEqual(enrollment.status, 'ongoing')
        self.assertEqual(enrollment.classes_total, 28)

        log = AuditLog.objects.filter(action='enrollment_status_change').latest('created_at')
        self.assertIn('completed → ongoing', log.detail)
        self.assertIn('classes_total 24 → 28', log.detail)

        # The trainer can now mark the 25th class — previously blocked forever by
        # AttendanceSerializer.validate_enrollment() rejecting a 'completed' enrollment.
        attendance_request = self.factory.post('/api/attendance/', {
            'enrollment': enrollment.id, 'date': '2026-02-01', 'topic_covered': 'Class 25', 'status': 'present',
        }, format='json')
        force_authenticate(attendance_request, user=self.trainer.user)
        attendance_response = AttendanceViewSet.as_view({'post': 'create'})(attendance_request)
        self.assertEqual(attendance_response.status_code, 201, attendance_response.data)

        enrollment.refresh_from_db()
        self.assertEqual(enrollment.classes_completed, 25)
        self.assertEqual(enrollment.status, 'ongoing')

    def test_lowering_classes_total_while_still_at_or_above_classes_completed_stays_completed(self):
        # Constructed directly (not a normally-reachable state) to exercise the "should
        # stay completed" branch specifically: classes_completed already meets the new,
        # lower classes_total, so the edit must not disturb status.
        enrollment = Enrollment.objects.create(
            student=self.student, course=self.course, trainer=self.trainer, status='completed',
            classes_completed=24, classes_total=28,
            start_date=datetime.date(2026, 1, 1), class_time='10:00', class_days='MON',
        )

        response = self._patch_classes_total(enrollment, 24)
        self.assertEqual(response.status_code, 200, response.data)

        enrollment.refresh_from_db()
        self.assertEqual(enrollment.status, 'completed')
        self.assertEqual(enrollment.classes_total, 24)
        self.assertFalse(AuditLog.objects.filter(action='enrollment_status_change').exists())


class PdfGenerationEscapesUserTextTests(TestCase):
    """A name containing markup-like characters must not break PDF generation — see
    certificate_pdf.py/report_pdf.py's use of xml.sax.saxutils.escape() before passing
    user text into ReportLab's Paragraph(), which otherwise interprets a small
    HTML-like markup subset and would raise a parse error on malformed input like an
    unclosed tag.
    """

    def setUp(self):
        self.trainer = _make_trainer(username='trainer_pdf_escape')
        self.trainer.name = 'Trainer <b>Bold</b> & Co'
        self.trainer.save(update_fields=['name'])

    def test_certificate_pdf_survives_a_malicious_student_name(self):
        enrollment = _make_enrollment(self.trainer)
        enrollment.student.name = '<script>alert(1)</script> <unclosed'
        enrollment.student.save(update_fields=['name'])
        enrollment.classes_completed = enrollment.classes_total
        enrollment.status = 'completed'
        enrollment.save(update_fields=['classes_completed', 'status'])

        pdf_bytes = render_certificate_pdf(enrollment)
        self.assertTrue(pdf_bytes.startswith(b'%PDF'))

    def test_student_report_pdf_survives_a_malicious_student_name(self):
        enrollment = _make_enrollment(self.trainer)
        enrollment.student.name = '<font size="999">HUGE</font> <unclosed'
        enrollment.student.save(update_fields=['name'])

        pdf_bytes = render_student_report_pdf(enrollment)
        self.assertTrue(pdf_bytes.startswith(b'%PDF'))


class TransferActionTests(APITestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_user(username='admin_transfer', password='x', is_staff=True)
        self.trainer = _make_trainer(username='trainer_transfer_from')
        self.trainer.name = 'Original Trainer'
        self.trainer.save(update_fields=['name'])
        self.new_trainer = _make_trainer(username='trainer_transfer_to')
        self.new_trainer.name = 'New Trainer'
        self.new_trainer.save(update_fields=['name'])
        self.enrollment = _make_enrollment(self.trainer)
        self.factory = APIRequestFactory()

    def _transfer(self, trainer_id):
        request = self.factory.post(
            f'/api/enrollments/{self.enrollment.id}/transfer/', {'trainer': trainer_id}, format='json',
        )
        force_authenticate(request, user=self.admin)
        return EnrollmentViewSet.as_view({'post': 'transfer'})(request, pk=self.enrollment.id)

    def test_transfer_reassigns_the_trainer_and_logs_it(self):
        response = self._transfer(self.new_trainer.id)
        self.assertEqual(response.status_code, 200, response.data)

        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.trainer_id, self.new_trainer.id)

        log = AuditLog.objects.filter(action='enrollment_transfer').latest('created_at')
        self.assertIn('Original Trainer', log.detail)
        self.assertIn('New Trainer', log.detail)

    def test_cannot_transfer_a_non_ongoing_enrollment(self):
        self.enrollment.status = 'completed'
        self.enrollment.save(update_fields=['status'])

        response = self._transfer(self.new_trainer.id)
        self.assertEqual(response.status_code, 400)
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.trainer_id, self.trainer.id)


class WithdrawActionTests(APITestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_user(username='admin_withdraw', password='x', is_staff=True)
        self.trainer = _make_trainer(username='trainer_withdraw')
        self.enrollment = _make_enrollment(self.trainer, rate_per_class=Decimal('1000'))
        self.plan = create_payment_plan(self.enrollment, 'two_installments', Decimal('24000'))
        self.factory = APIRequestFactory()

    def _withdraw(self, **body):
        request = self.factory.post(f'/api/enrollments/{self.enrollment.id}/withdraw/', body, format='json')
        force_authenticate(request, user=self.admin)
        return EnrollmentViewSet.as_view({'post': 'withdraw'})(request, pk=self.enrollment.id)

    def test_withdraw_cancels_pending_installments_and_logs_refund(self):
        response = self._withdraw(refund_amount='5000', refund_note='parent requested refund')
        self.assertEqual(response.status_code, 200, response.data)

        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.status, 'withdrawn')

        self.plan.refresh_from_db()
        self.assertEqual(self.plan.refunded_amount, Decimal('5000.00'))
        self.assertEqual(self.plan.refund_note, 'parent requested refund')
        self.assertFalse(self.plan.installments.filter(paid_status='pending').exists())
        self.assertEqual(self.plan.installments.filter(paid_status='cancelled').count(), 2)

        log = AuditLog.objects.filter(action='enrollment_withdraw').latest('created_at')
        self.assertIn('refunded ₹5000', log.object_repr)
        self.assertIn('installment(s) cancelled', log.object_repr)
        self.assertEqual(log.detail, 'parent requested refund')

    def test_withdraw_without_refund_amount_leaves_refunded_amount_at_zero(self):
        response = self._withdraw()
        self.assertEqual(response.status_code, 200, response.data)

        self.plan.refresh_from_db()
        self.assertEqual(self.plan.refunded_amount, Decimal('0.00'))
        self.assertEqual(self.plan.installments.filter(paid_status='cancelled').count(), 2)

    def test_cannot_withdraw_a_non_ongoing_enrollment(self):
        self.enrollment.status = 'withdrawn'
        self.enrollment.save(update_fields=['status'])

        response = self._withdraw()
        self.assertEqual(response.status_code, 400)


class AssignSubstituteActionTests(APITestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_user(username='admin_assign_sub', password='x', is_staff=True)
        self.trainer = _make_trainer(username='trainer_sub_owner')
        self.substitute = _make_trainer(username='trainer_sub_covering')
        self.enrollment = _make_enrollment(self.trainer)
        self.factory = APIRequestFactory()

    def _assign(self, **body):
        request = self.factory.post(
            f'/api/enrollments/{self.enrollment.id}/assign_substitute/', body, format='json',
        )
        force_authenticate(request, user=self.admin)
        return EnrollmentViewSet.as_view({'post': 'assign_substitute'})(request, pk=self.enrollment.id)

    def test_assign_substitute_creates_coverage_and_logs_it(self):
        response = self._assign(trainer=self.substitute.id, start_date='2026-02-01', end_date='2026-02-07')
        self.assertEqual(response.status_code, 201, response.data)

        self.assertTrue(SubstituteAssignment.objects.filter(
            enrollment=self.enrollment, substitute_trainer=self.substitute,
            start_date=datetime.date(2026, 2, 1), end_date=datetime.date(2026, 2, 7),
        ).exists())
        self.assertTrue(AuditLog.objects.filter(action='substitute_assign').exists())

    def test_cannot_assign_substitute_to_a_non_ongoing_enrollment(self):
        self.enrollment.status = 'completed'
        self.enrollment.save(update_fields=['status'])

        response = self._assign(trainer=self.substitute.id, start_date='2026-02-01', end_date='2026-02-07')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(SubstituteAssignment.objects.filter(enrollment=self.enrollment).exists())


class InstallmentMarkPaidRevokeTests(APITestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_user(username='admin_installment', password='x', is_staff=True)
        self.trainer = _make_trainer(username='trainer_installment')
        self.enrollment = _make_enrollment(self.trainer, rate_per_class=Decimal('1000'))
        self.plan = create_payment_plan(self.enrollment, 'two_installments', Decimal('24000'))
        self.installment = self.plan.installments.get(sequence=1)
        self.factory = APIRequestFactory()

    def test_mark_paid_flips_status_sets_paid_date_and_logs_it(self):
        request = self.factory.post(f'/api/installments/{self.installment.id}/mark_paid/')
        force_authenticate(request, user=self.admin)
        response = PaymentInstallmentViewSet.as_view({'post': 'mark_paid'})(request, pk=self.installment.id)
        self.assertEqual(response.status_code, 200, response.data)

        self.installment.refresh_from_db()
        self.assertEqual(self.installment.paid_status, 'paid')
        self.assertEqual(self.installment.paid_date, datetime.date.today())
        self.assertTrue(AuditLog.objects.filter(action='installment_mark_paid').exists())

    def test_revoke_reverts_to_pending_and_clears_paid_date(self):
        self.installment.paid_status = 'paid'
        self.installment.paid_date = datetime.date.today()
        self.installment.save(update_fields=['paid_status', 'paid_date'])

        request = self.factory.post(f'/api/installments/{self.installment.id}/revoke/')
        force_authenticate(request, user=self.admin)
        response = PaymentInstallmentViewSet.as_view({'post': 'revoke'})(request, pk=self.installment.id)
        self.assertEqual(response.status_code, 200, response.data)

        self.installment.refresh_from_db()
        self.assertEqual(self.installment.paid_status, 'pending')
        self.assertIsNone(self.installment.paid_date)
        self.assertTrue(AuditLog.objects.filter(action='installment_revoke').exists())


class MyStudentsExcludesArchivedStudentsTests(APITestCase):
    """An archived student must disappear from a trainer's own view entirely —
    My Students, the dashboard's weekly schedule, and the attendance-marking
    picker all read from this same endpoint. See MyStudentsView.get_queryset().
    """

    def _list(self, trainer):
        factory = APIRequestFactory()
        request = factory.get('/api/my-students/')
        force_authenticate(request, user=trainer.user)
        return MyStudentsView.as_view()(request)

    def test_archived_students_enrollment_is_excluded(self):
        trainer = _make_trainer(username='trainer_archived_student_check')
        enrollment = _make_enrollment(trainer)
        enrollment.student.status = 'archived'
        enrollment.student.save(update_fields=['status'])

        response = self._list(trainer)

        self.assertEqual(response.data, [])

    def test_active_students_enrollment_still_shows(self):
        trainer = _make_trainer(username='trainer_active_student_check')
        _make_enrollment(trainer)

        response = self._list(trainer)

        self.assertEqual(len(response.data), 1)
