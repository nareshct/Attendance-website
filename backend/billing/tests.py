import datetime
from decimal import Decimal
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from rest_framework.test import APIRequestFactory, APITestCase, force_authenticate

from attendance.models import Attendance
from clients.models import Client
from clients.services import client_totals
from courses.models import Course
from enrollments.models import Enrollment
from enrollments.services import create_payment_plan
from trainers.models import Trainer

from .invoice_pdf import render_invoice_pdf
from .models import BillingCycle, ClientInvoice, CycleRevenueSnapshot, Payout
from .services import (
    b2c_totals_for_range,
    compute_admin_alerts,
    cycle_bounds_for_date,
    cycle_revenue_totals,
    historical_rate,
    snapshot_cycle_revenue,
)
from .views import BillingCycleViewSet, CycleRevenueHistoryView


def _make_trainer(username, rate):
    user = get_user_model().objects.create_user(username=username, password='x')
    return Trainer.objects.create(user=user, name=username, phone_number='0000000000', place='Here', default_rate_per_class=rate)


class ClientTotalsAsOfTests(TestCase):
    """Regression coverage for the bug where snapshot_cycle_revenue() priced a
    closed cycle using today's live rate instead of the rate that was in
    effect when that cycle actually happened — see clients.services.client_totals
    and billing.services.snapshot_cycle_revenue.
    """

    def setUp(self):
        self.trainer = _make_trainer('trainer_a', Decimal('100'))
        self.client_obj = Client.objects.create(company_name='Acme School', contact_phone='123', rate_per_class=Decimal('200'))
        self.course = Course.objects.create(name='Python', total_classes=24, rate_per_class=Decimal('300'))
        from students.models import Student
        self.student = Student.objects.create(name='Kid A', grade='5', source_type='B2B', client=self.client_obj)
        self.enrollment = Enrollment.objects.create(
            student=self.student, course=self.course, trainer=self.trainer,
            start_date=datetime.date(2026, 1, 1), class_time='10:00', class_days='MON',
        )
        Attendance.objects.create(
            enrollment=self.enrollment, date=datetime.date(2026, 1, 5), status='present',
            topic_covered='intro', marked_by=self.trainer,
        )

    def test_live_rate_used_when_as_of_not_given(self):
        totals = client_totals(self.client_obj, datetime.date(2026, 1, 1), datetime.date(2026, 1, 31))
        self.assertEqual(totals['total_revenue'], Decimal('200.00'))

        # Bump the client's rate — a live (as_of=None) query should reflect it immediately.
        self.client_obj.rate_per_class = Decimal('500')
        self.client_obj.save()
        totals = client_totals(self.client_obj, datetime.date(2026, 1, 1), datetime.date(2026, 1, 31))
        self.assertEqual(totals['total_revenue'], Decimal('500.00'))

    def test_as_of_pins_the_rate_that_was_in_effect_back_then(self):
        # Rate changes today; a lookup as_of a date BEFORE the change must still
        # resolve to the original rate, not the new one.
        self.client_obj.rate_per_class = Decimal('500')
        self.client_obj.save()

        totals = client_totals(
            self.client_obj, datetime.date(2026, 1, 1), datetime.date(2026, 1, 31), as_of=datetime.date(2026, 1, 15),
        )
        self.assertEqual(totals['total_revenue'], Decimal('200.00'), 'as_of should ignore the later rate change')

        totals_today = client_totals(
            self.client_obj, datetime.date(2026, 1, 1), datetime.date(2026, 1, 31), as_of=datetime.date.today(),
        )
        self.assertEqual(totals_today['total_revenue'], Decimal('500.00'), 'as_of today should see the new rate')


class ClosedCycleSnapshotTests(TestCase):
    """Regression test for the exact bug found in this session: closing (or
    lazily backfilling) an OLD cycle must price it using that cycle's own
    date range and the rate in effect at the time — not today's date range or
    today's rate.
    """

    def setUp(self):
        self.trainer = _make_trainer('trainer_b', Decimal('100'))
        self.client_obj = Client.objects.create(company_name='Old Client', contact_phone='123', rate_per_class=Decimal('200'))
        self.course = Course.objects.create(name='Scratch', total_classes=24, rate_per_class=Decimal('300'))
        from students.models import Student
        self.student = Student.objects.create(name='Kid B', grade='4', source_type='B2B', client=self.client_obj)
        self.enrollment = Enrollment.objects.create(
            student=self.student, course=self.course, trainer=self.trainer,
            start_date=datetime.date(2025, 1, 1), class_time='11:00', class_days='TUE',
        )
        # A class taught back in an old, already-closed cycle.
        Attendance.objects.create(
            enrollment=self.enrollment, date=datetime.date(2025, 1, 7), status='present',
            topic_covered='intro', marked_by=self.trainer,
        )
        self.old_cycle = BillingCycle.objects.create(
            cycle_start=datetime.date(2025, 1, 1), cycle_end=datetime.date(2025, 1, 15), status='closed',
        )

    def test_backfill_prices_at_the_cycle_own_date_range_and_rate(self):
        # Snapshot once, at the "correct" rate (200/class).
        snapshot = snapshot_cycle_revenue(self.old_cycle)
        self.assertEqual(snapshot.b2b_revenue, Decimal('200.00'))

        # Now bump the client's rate, as if months have passed since this cycle closed.
        self.client_obj.rate_per_class = Decimal('900')
        self.client_obj.save()

        # Simulate "never snapshotted until now" by deleting it, then backfilling —
        # this is exactly what CycleRevenueView's lazy backfill does.
        CycleRevenueSnapshot.objects.filter(cycle=self.old_cycle).delete()
        result = cycle_revenue_totals(self.old_cycle)

        self.assertEqual(
            result['b2b_revenue'], Decimal('200.00'),
            'A closed cycle must stay priced at its own historical rate, not a later rate change.',
        )
        self.assertEqual(result['b2b_classes'], 1)

    def test_open_cycle_still_uses_live_rate(self):
        # The open-cycle path must NOT be pinned to a past rate — only closed/frozen cycles are.
        today = datetime.date.today()
        start, end = cycle_bounds_for_date(today)
        open_cycle = BillingCycle.objects.create(cycle_start=start, cycle_end=end, status='open')
        Attendance.objects.create(
            enrollment=self.enrollment, date=today, status='present', topic_covered='x', marked_by=self.trainer,
        )
        self.client_obj.rate_per_class = Decimal('700')
        self.client_obj.save()

        result = cycle_revenue_totals(open_cycle)
        self.assertEqual(result['b2b_revenue'], Decimal('700.00'), 'the open cycle should reflect the live current rate')


class B2CTotalsTests(TestCase):
    def test_b2c_revenue_uses_course_flat_rate(self):
        trainer = _make_trainer('trainer_c', Decimal('100'))
        course = Course.objects.create(name='Robotics', total_classes=24, rate_per_class=Decimal('1000'))
        from students.models import Student
        student = Student.objects.create(name='Kid C', grade='6', source_type='B2C')
        enrollment = Enrollment.objects.create(
            student=student, course=course, trainer=trainer,
            start_date=datetime.date(2026, 1, 1), class_time='12:00', class_days='WED',
        )
        Attendance.objects.create(
            enrollment=enrollment, date=datetime.date(2026, 1, 7), status='present',
            topic_covered='intro', marked_by=trainer,
        )

        totals = b2c_totals_for_range(datetime.date(2026, 1, 1), datetime.date(2026, 1, 31))
        self.assertEqual(totals['total_classes'], 1)
        self.assertEqual(totals['total_revenue'], Decimal('1000.00'))
        self.assertEqual(totals['trainer_cost'], Decimal('100.00'))
        self.assertEqual(totals['our_earning'], Decimal('900.00'))


class HistoricalRateTests(TestCase):
    def test_no_history_returns_none(self):
        client_obj = Client.objects.create(company_name='Fresh Client', contact_phone='123', rate_per_class=Decimal('200'))
        # rate_per_class was set at creation via .create(), which bypasses the
        # save()-diff logging path (no prior value to diff against) — so there's
        # no RateHistory row yet, and historical_rate() must say so honestly.
        self.assertIsNone(historical_rate(client_obj, None, datetime.date(2020, 1, 1)))

    def test_rate_change_is_logged_and_queryable(self):
        client_obj = Client.objects.create(company_name='Tracked Client', contact_phone='123', rate_per_class=Decimal('200'))
        before_change = datetime.date.today() - datetime.timedelta(days=1)

        client_obj.rate_per_class = Decimal('500')
        client_obj.save()

        self.assertEqual(historical_rate(client_obj, None, before_change), Decimal('200.00'))
        self.assertEqual(historical_rate(client_obj, None, datetime.date.today()), Decimal('500.00'))


class AdminAlertsTests(TestCase):
    """compute_admin_alerts() powers both AdminAlertsView and the
    send_admin_digest management command — regression coverage for what
    counts as overdue (invoices) / due (installments)."""

    def test_overdue_invoice_is_reported_recent_one_is_not(self):
        client_obj = Client.objects.create(company_name='Alert Client', contact_phone='123', rate_per_class=Decimal('200'))
        old_cycle = BillingCycle.objects.create(
            cycle_start=datetime.date.today() - datetime.timedelta(days=30),
            cycle_end=datetime.date.today() - datetime.timedelta(days=16),
            status='closed',
        )
        recent_cycle = BillingCycle.objects.create(
            cycle_start=datetime.date.today() - datetime.timedelta(days=2),
            cycle_end=datetime.date.today(),
            status='closed',
        )
        overdue_invoice = ClientInvoice.objects.create(
            client=client_obj, cycle=old_cycle, total_classes=1, total_amount=Decimal('200'), status='pending',
        )
        # Within the 3-day grace period — not overdue yet.
        ClientInvoice.objects.create(
            client=client_obj, cycle=recent_cycle, total_classes=1, total_amount=Decimal('200'), status='pending',
        )

        alerts = compute_admin_alerts()
        reported_ids = [row['id'] for row in alerts['overdue_invoices']]
        self.assertEqual(reported_ids, [overdue_invoice.id])

    def test_installment_reported_once_its_milestone_is_reached(self):
        trainer = _make_trainer('alert_trainer', Decimal('100'))
        course = Course.objects.create(name='Alert Course', total_classes=24, rate_per_class=Decimal('1000'))
        from students.models import Student
        student = Student.objects.create(name='Alert Kid', grade='5', source_type='B2C')
        enrollment = Enrollment.objects.create(
            student=student, course=course, trainer=trainer,
            start_date=datetime.date(2026, 1, 1), class_time='10:00', class_days='MON',
        )
        plan = create_payment_plan(enrollment, 'three_installments', Decimal('9000'))
        first = plan.installments.get(sequence=1)
        first.paid_status = 'paid'
        first.save()
        second = plan.installments.get(sequence=2)  # due_at_classes=6

        due_ids = [row['id'] for row in compute_admin_alerts()['due_installments']]
        self.assertNotIn(second.id, due_ids, 'not due yet at 0 classes completed')

        enrollment.classes_completed = 5
        enrollment.save()
        due_ids = [row['id'] for row in compute_admin_alerts()['due_installments']]
        self.assertIn(second.id, due_ids)


class CycleRevenueHistoryLimitParamTests(APITestCase):
    """A malformed ?limit= must return a clean 400, not a raw 500 — see
    CycleRevenueHistoryView.get()."""

    def setUp(self):
        self.admin = get_user_model().objects.create_user(username='admin_limit_param', password='x', is_staff=True)
        self.factory = APIRequestFactory()

    def test_non_numeric_limit_returns_400(self):
        request = self.factory.get('/api/cycle-revenue-history/?limit=abc')
        force_authenticate(request, user=self.admin)
        response = CycleRevenueHistoryView.as_view()(request)
        self.assertEqual(response.status_code, 400)

    def test_numeric_limit_still_works(self):
        BillingCycle.objects.create(cycle_start=datetime.date(2026, 1, 1), cycle_end=datetime.date(2026, 1, 15), status='closed')
        BillingCycle.objects.create(cycle_start=datetime.date(2026, 1, 16), cycle_end=datetime.date(2026, 1, 31), status='closed')
        request = self.factory.get('/api/cycle-revenue-history/?limit=1')
        force_authenticate(request, user=self.admin)
        response = CycleRevenueHistoryView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)


class BillingCycleCloseTests(APITestCase):
    """Closing a cycle generates its Payout/ClientInvoice/CycleRevenueSnapshot rows and
    freezes it — see BillingCycleViewSet.close(). The status check + mutation run inside
    a transaction with select_for_update() on the cycle row, so two concurrent closes
    can't both pass the 'already closed' check before either writes 'closed' — this
    confirms that lock didn't break the ordinary happy-path / already-closed behavior."""

    def setUp(self):
        from students.models import Student

        self.admin = get_user_model().objects.create_user(username='admin_close_cycle', password='x', is_staff=True)
        self.trainer = _make_trainer('trainer_close_cycle', Decimal('100'))
        self.client_obj = Client.objects.create(
            company_name='Close Cycle Co', contact_phone='123', rate_per_class=Decimal('200'),
        )
        self.course = Course.objects.create(name='Close Cycle Course', total_classes=24, rate_per_class=Decimal('300'))
        self.student = Student.objects.create(name='Close Cycle Kid', grade='5', source_type='B2B', client=self.client_obj)
        self.enrollment = Enrollment.objects.create(
            student=self.student, course=self.course, trainer=self.trainer,
            start_date=datetime.date(2026, 1, 1), class_time='10:00', class_days='MON',
        )
        self.cycle = BillingCycle.objects.create(
            cycle_start=datetime.date(2026, 1, 1), cycle_end=datetime.date(2026, 1, 15), status='open',
        )
        Attendance.objects.create(
            enrollment=self.enrollment, date=datetime.date(2026, 1, 5), status='present', marked_by=self.trainer,
        )
        self.factory = APIRequestFactory()

    def _close(self):
        request = self.factory.post(f'/api/billing-cycles/{self.cycle.id}/close/')
        force_authenticate(request, user=self.admin)
        return BillingCycleViewSet.as_view({'post': 'close'})(request, pk=self.cycle.id)

    def test_close_generates_payout_invoice_and_snapshot_and_freezes_the_cycle(self):
        response = self._close()
        self.assertEqual(response.status_code, 200, response.data)

        self.cycle.refresh_from_db()
        self.assertEqual(self.cycle.status, 'closed')

        payout = Payout.objects.get(trainer=self.trainer, cycle=self.cycle)
        self.assertEqual(payout.total_amount, Decimal('100.00'))
        invoice = ClientInvoice.objects.get(client=self.client_obj, cycle=self.cycle)
        self.assertEqual(invoice.total_amount, Decimal('200.00'))
        self.assertTrue(CycleRevenueSnapshot.objects.filter(cycle=self.cycle).exists())

    def test_closing_an_already_closed_cycle_returns_400_and_does_not_reprocess(self):
        first = self._close()
        self.assertEqual(first.status_code, 200, first.data)
        payout_count_after_first_close = Payout.objects.filter(cycle=self.cycle).count()

        second = self._close()
        self.assertEqual(second.status_code, 400)
        self.assertIn('already', second.data['detail'])

        # No duplicate Payout rows were created by the second, rejected attempt.
        self.assertEqual(Payout.objects.filter(cycle=self.cycle).count(), payout_count_after_first_close)

    def test_non_admin_cannot_close_a_cycle(self):
        trainer = _make_trainer('trainer_close_cycle_denied', Decimal('50'))
        request = self.factory.post(f'/api/billing-cycles/{self.cycle.id}/close/')
        force_authenticate(request, user=trainer.user)
        response = BillingCycleViewSet.as_view({'post': 'close'})(request, pk=self.cycle.id)
        self.assertEqual(response.status_code, 403)

        self.cycle.refresh_from_db()
        self.assertEqual(self.cycle.status, 'open')


class InvoicePdfEscapesUserTextTests(TestCase):
    """A client's name/phone/email containing markup-like characters must not break PDF
    generation — see invoice_pdf.py's use of xml.sax.saxutils.escape() before passing
    user text into ReportLab's Paragraph()."""

    def test_invoice_pdf_survives_a_malicious_client_name(self):
        client_obj = Client.objects.create(
            company_name='<script>alert(1)</script> & <unclosed',
            contact_phone='<b>unclosed',
            contact_email='parent@example.com',
            rate_per_class=Decimal('200'),
        )
        cycle = BillingCycle.objects.create(
            cycle_start=datetime.date(2026, 1, 1), cycle_end=datetime.date(2026, 1, 15), status='closed',
        )
        invoice = ClientInvoice.objects.create(
            client=client_obj, cycle=cycle, total_classes=5, total_amount=Decimal('1000.00'), status='pending',
        )

        pdf_bytes = render_invoice_pdf(invoice)
        self.assertTrue(pdf_bytes.startswith(b'%PDF'))


class CloseBillingCycleCommandTests(TestCase):
    """The close_billing_cycle management command wraps the same close logic as
    BillingCycleViewSet.close() for ops/cron use — see billing/management/commands/
    close_billing_cycle.py."""

    def setUp(self):
        from students.models import Student

        self.trainer = _make_trainer('trainer_close_cmd', Decimal('100'))
        self.client_obj = Client.objects.create(
            company_name='Close Cmd Co', contact_phone='123', rate_per_class=Decimal('200'),
        )
        self.course = Course.objects.create(name='Close Cmd Course', total_classes=24, rate_per_class=Decimal('300'))
        self.student = Student.objects.create(name='Close Cmd Kid', grade='5', source_type='B2B', client=self.client_obj)
        self.enrollment = Enrollment.objects.create(
            student=self.student, course=self.course, trainer=self.trainer,
            start_date=datetime.date(2026, 1, 1), class_time='10:00', class_days='MON',
        )
        self.cycle = BillingCycle.objects.create(
            cycle_start=datetime.date(2026, 1, 1), cycle_end=datetime.date(2026, 1, 15), status='open',
        )
        Attendance.objects.create(
            enrollment=self.enrollment, date=datetime.date(2026, 1, 5), status='present', marked_by=self.trainer,
        )

    def test_closes_the_specified_cycle_and_generates_payouts(self):
        out = StringIO()
        call_command('close_billing_cycle', self.cycle.id, stdout=out)

        self.cycle.refresh_from_db()
        self.assertEqual(self.cycle.status, 'closed')
        self.assertTrue(Payout.objects.filter(trainer=self.trainer, cycle=self.cycle).exists())
        self.assertTrue(ClientInvoice.objects.filter(client=self.client_obj, cycle=self.cycle).exists())
        self.assertIn('Closed cycle', out.getvalue())

    def test_defaults_to_the_oldest_open_cycle_when_no_id_given(self):
        out = StringIO()
        call_command('close_billing_cycle', stdout=out)

        self.cycle.refresh_from_db()
        self.assertEqual(self.cycle.status, 'closed')

    def test_raises_command_error_for_an_already_closed_cycle(self):
        self.cycle.status = 'closed'
        self.cycle.save(update_fields=['status'])
        with self.assertRaises(CommandError):
            call_command('close_billing_cycle', self.cycle.id)

    def test_raises_command_error_when_no_open_cycles_and_no_id_given(self):
        self.cycle.delete()
        with self.assertRaises(CommandError):
            call_command('close_billing_cycle')

    def test_raises_command_error_for_unknown_cycle_id(self):
        with self.assertRaises(CommandError):
            call_command('close_billing_cycle', 999999)
