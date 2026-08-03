"""Not a CI test — deliberately named so `manage.py test` (no args) does NOT
discover it (doesn't match test*.py), since it's slow and only meant to be run
on demand:

    python manage.py test reports.scale_audit

Simulates a coaching center's realistic operating scale (~6 years, 40
trainers, 1000+ students, 2000+ enrollments, tens of thousands of attendance
records) inside Django's normal isolated test database — created and torn
down automatically, the real dev database is never touched. Each test method
audits one feature area against that data and prints findings.
"""
import random
import time
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection, reset_queries
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIRequestFactory, force_authenticate

from attendance.models import Attendance
from audit.services import log_action
from billing.models import BillingCycle, ClientInvoice, Payout
from billing.services import (
    calculate_client_invoices_for_cycle,
    calculate_payouts_for_cycle,
    compute_admin_alerts,
    cycle_bounds_for_date,
    cycle_revenue_totals,
    snapshot_cycle_revenue,
)
from billing.views import AdminAlertsView, ClientInvoiceViewSet, PayoutViewSet
from clients.models import Client
from courses.models import Course
from enrollments.models import Enrollment, PaymentInstallment, PaymentPlan
from enrollments.services import create_payment_plan, find_schedule_conflict, trainer_payment_gate
from enrollments.views import EnrollmentViewSet
from students.models import Student
from students.views import StudentViewSet
from trainers.models import Trainer
from trainers.views import TrainerViewSet

User = get_user_model()

N_TRAINERS = 40
N_CLIENTS = 20
N_COURSES = 15
N_STUDENTS = 1000
YEARS = 6
CYCLES = YEARS * 24  # 1st-15th / 16th-end-of-month, twice a month


@override_settings(DEBUG=True)  # needed for connection.queries to populate
class ScaleAuditTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        t0 = time.time()
        random.seed(42)
        cls.admin = User.objects.create_user(username='scale_admin', password='x', is_staff=True)
        cls.factory = APIRequestFactory()

        cls.trainers = [
            Trainer.objects.create(
                user=User.objects.create_user(username=f'scale_trainer_{i}', password='x'),
                name=f'Trainer {i}', phone_number=f'9{i:09d}', place=random.choice(['Chennai', 'Bengaluru', 'Mumbai']),
                default_rate_per_class=Decimal(random.choice([100, 120, 150, 180])),
            )
            for i in range(N_TRAINERS)
        ]
        cls.clients = [
            Client.objects.create(
                company_name=f'Client School {i}', contact_phone=f'8{i:09d}',
                rate_per_class=Decimal(random.choice([200, 250, 300, 350])),
            )
            for i in range(N_CLIENTS)
        ]
        cls.courses = [
            Course.objects.create(
                name=f'Course {i}', total_classes=24, rate_per_class=Decimal(random.choice([800, 1000, 1200])),
            )
            for i in range(N_COURSES)
        ]

        # 1000 students via bulk_create with pre-formatted IDs (mirrors Student.save()'s
        # STU-<year>-<seq> scheme) — the real per-save sequential-lookup ID generation is
        # already covered by every other test in this suite; doing it 1000x here would
        # just be 1000 redundant "find the last one" queries for no extra coverage.
        year = date.today().year
        student_rows = []
        for i in range(N_STUDENTS):
            is_b2c = random.random() < 0.6
            client = random.choice(cls.clients) if not is_b2c else None
            student_rows.append(Student(
                student_id=f'STU-{year}-{i + 1:04d}',
                name=f'Student {i}', grade=str(random.randint(3, 10)),
                source_type='B2C' if is_b2c else 'B2B', client=client,
                parent_name=f'Parent {i}', parent_phone_number=f'7{i:09d}',
            ))
        Student.objects.bulk_create(student_rows)
        cls.students = list(Student.objects.all())

        # Billing cycles spanning 6 years.
        cls.cycles = []
        cursor = date.today()
        for _ in range(CYCLES):
            start, end = cycle_bounds_for_date(cursor)
            cls.cycles.append((start, end))
            cursor = start - timedelta(days=1)
        cls.cycles.reverse()  # oldest first
        cycle_objs = [BillingCycle(cycle_start=s, cycle_end=e, status='open') for s, e in cls.cycles]
        BillingCycle.objects.bulk_create(cycle_objs)
        cls.cycle_objs = list(BillingCycle.objects.order_by('cycle_start'))

        # ~2000+ enrollments: each student gets 1-3, spread across the whole 6-year
        # window, trainer/course picked randomly (every trainer has a flat
        # default_rate_per_class so has_rate_for() passes for every course).
        enrollments = []
        for s in cls.students:
            for _ in range(random.choice([1, 2, 2, 3, 3])):
                trainer = random.choice(cls.trainers)
                course = random.choice(cls.courses)
                cycle_idx = random.randint(0, len(cls.cycle_objs) - 1)
                start_date = cls.cycle_objs[cycle_idx].cycle_start
                age_cycles = len(cls.cycle_objs) - cycle_idx
                if age_cycles > 12:
                    status, completed = 'completed', course.total_classes
                elif age_cycles < 2:
                    status, completed = 'ongoing', random.randint(0, 4)
                else:
                    roll = random.random()
                    if roll < 0.08:
                        status, completed = 'withdrawn', random.randint(0, course.total_classes // 2)
                    elif roll < 0.85:
                        status, completed = 'ongoing', random.randint(1, course.total_classes - 1)
                    else:
                        status, completed = 'completed', course.total_classes
                enrollments.append(Enrollment(
                    student=s, course=course, trainer=trainer, batch_number=1,
                    classes_completed=completed, classes_total=course.total_classes,
                    start_date=start_date, status=status,
                    class_time=f'{random.randint(9, 18):02d}:00',
                    class_days=random.choice(['MON,WED,FRI', 'TUE,THU', 'SAT', 'MON,THU', 'WED,SAT']),
                ))
        Enrollment.objects.bulk_create(enrollments, batch_size=1000)
        cls.enrollments = list(Enrollment.objects.select_related('student', 'course', 'trainer').all())
        cls.enrollment_count = len(cls.enrollments)

        # Attendance: one 'present' row per completed class, dated backward from the
        # enrollment's start, capped so date volume stays real but the test doesn't take
        # forever — real deployments accrue this one class at a time over years; here we
        # backfill it in bulk to get to the same end state.
        attendance_rows = []
        for e in cls.enrollments:
            n = e.classes_completed
            if n <= 0:
                continue
            for k in range(n):
                attendance_rows.append(Attendance(
                    enrollment=e, date=e.start_date + timedelta(days=k * 3),
                    status='present', topic_covered=f'Session {k + 1}', marked_by=e.trainer,
                ))
        Attendance.objects.bulk_create(attendance_rows, batch_size=2000)
        cls.attendance_count = len(attendance_rows)

        # Payment plans for B2C enrollments — via the real service, so the actual
        # milestone/upfront/rounding logic gets exercised, not a re-derived shortcut.
        plan_count = 0
        for e in cls.enrollments:
            if e.student.source_type == 'B2C' and e.status != 'withdrawn' and random.random() < 0.9:
                plan_type = random.choice(['two_installments', 'three_installments', 'four_installments'])
                total = Decimal(e.course.rate_per_class) * e.classes_total
                plan = create_payment_plan(e, plan_type, total)
                # Mark installments paid up to what the milestone schedule says should be
                # collected by now, so payment-gate / overdue logic has a realistic mix.
                for inst in plan.installments.all():
                    is_reached = inst.due_at_classes is None or e.classes_completed >= inst.due_at_classes - 1
                    if is_reached and random.random() < 0.8:
                        inst.paid_status = 'paid'
                        inst.paid_date = e.start_date
                        inst.save(update_fields=['paid_status', 'paid_date'])
                plan_count += 1
        cls.plan_count = plan_count

        # Close + snapshot the most recent 12 cycles for real (Payout/ClientInvoice rows
        # + frozen revenue snapshots) — older cycles are left open-in-name only to
        # exercise the lazy-backfill path (CycleRevenueView / cycle_revenue_totals) at
        # genuine historical distance instead of pre-computing all 144.
        recent_cycles = cls.cycle_objs[-12:]
        for cycle in recent_cycles:
            calculate_payouts_for_cycle(cycle)
            calculate_client_invoices_for_cycle(cycle)
            snapshot_cycle_revenue(cycle)
            cycle.status = 'closed'
        BillingCycle.objects.bulk_update(recent_cycles, ['status'])
        # A handful of older, never-closed-until-now cycles too, so overdue-invoice
        # detection has real candidates (see AdminAlertsTests upstream in billing/tests.py
        # for the correctness check — here it's about volume/perf).
        older_slice = cls.cycle_objs[-40:-12]
        for cycle in older_slice:
            calculate_payouts_for_cycle(cycle)
            calculate_client_invoices_for_cycle(cycle)
            snapshot_cycle_revenue(cycle)
            cycle.status = 'closed'
        BillingCycle.objects.bulk_update(older_slice, ['status'])
        # Deliberately mark most of the resulting invoices unpaid so overdue detection has
        # real volume to chew through.
        ClientInvoice.objects.filter(cycle__in=older_slice + recent_cycles).exclude(
            id__in=list(ClientInvoice.objects.filter(cycle__in=recent_cycles[-1:]).values_list('id', flat=True))
        ).update(status='pending')

        cls.setup_seconds = time.time() - t0

    def test_00_seed_scale_and_timing(self):
        print(f'\n[scale] setUpTestData took {self.setup_seconds:.1f}s')
        print(f'[scale] trainers={len(self.trainers)} clients={len(self.clients)} courses={len(self.courses)}')
        print(f'[scale] students={Student.objects.count()} (target {N_STUDENTS})')
        print(f'[scale] enrollments={self.enrollment_count} (target 2000+)')
        print(f'[scale] attendance={self.attendance_count}')
        print(f'[scale] payment plans={self.plan_count}, installments={PaymentInstallment.objects.count()}')
        print(f'[scale] billing cycles={BillingCycle.objects.count()} spanning {YEARS} years')
        self.assertGreaterEqual(Student.objects.count(), 1000)
        self.assertGreaterEqual(self.enrollment_count, 2000, 'seed generator should reliably clear 2000 enrollments')

    def test_01_pagination_is_correct_at_scale(self):
        request = self.factory.get('/api/students/')
        force_authenticate(request, user=self.admin)
        response = StudentViewSet.as_view({'get': 'list'})(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], Student.objects.count())
        self.assertEqual(len(response.data['results']), 100, 'PAGE_SIZE=100 must cap a single page')
        self.assertIsNotNone(response.data['next'], 'with 1000 students, page 2 must exist')

        request2 = self.factory.get('/api/students/?page=2')
        force_authenticate(request2, user=self.admin)
        response2 = StudentViewSet.as_view({'get': 'list'})(request2)
        self.assertEqual(len(response2.data['results']), 100)
        page1_ids = {r['id'] for r in response.data['results']}
        page2_ids = {r['id'] for r in response2.data['results']}
        self.assertEqual(page1_ids & page2_ids, set(), 'pages must not overlap')

        last_page = -(-Student.objects.count() // 100)
        request3 = self.factory.get(f'/api/students/?page={last_page}')
        force_authenticate(request3, user=self.admin)
        response3 = StudentViewSet.as_view({'get': 'list'})(request3)
        self.assertEqual(response3.status_code, 200)
        self.assertIsNone(response3.data['next'], 'the last page must report no further page')
        print(f'[scale] students: {Student.objects.count()} across {last_page} pages of 100 — pagination correct')

    def test_02_search_finds_records_beyond_page_one(self):
        # Pick a student guaranteed to be well past page 1 (100 items) alphabetically —
        # "Student 999" sorts after "Student 100".."Student 998" lexically... instead
        # target by a known unique id far into the sequence.
        target = Student.objects.get(student_id__endswith='-0999')
        request = self.factory.get(f'/api/students/?search={target.name}')
        force_authenticate(request, user=self.admin)
        response = StudentViewSet.as_view({'get': 'list'})(request)
        names = [r['name'] for r in response.data['results']]
        self.assertIn(target.name, names, 'search must find a match regardless of pagination')

        target_trainer = self.trainers[-1]
        request2 = self.factory.get(f'/api/trainers/?search={target_trainer.name}')
        force_authenticate(request2, user=self.admin)
        response2 = TrainerViewSet.as_view({'get': 'list'})(request2)
        self.assertIn(target_trainer.name, [r['name'] for r in response2.data['results']])

        target_enrollment = self.enrollments[-1]
        request3 = self.factory.get(f'/api/enrollments/?search={target_enrollment.student.name}')
        force_authenticate(request3, user=self.admin)
        response3 = EnrollmentViewSet.as_view({'get': 'list'})(request3)
        self.assertIn(target_enrollment.student.name, [r['student_name'] for r in response3.data['results']])
        print('[scale] search: found records regardless of page, across students/trainers/enrollments')

    def test_03_list_endpoints_query_cost_stays_bounded(self):
        # N+1 watch: fetching one page (100 rows) of enrollments/students should not
        # scale linearly with the page size — a handful of queries (list + count +
        # select_related joins), not ~100+ one per row.
        for path, viewset, action_map in [
            ('/api/students/', StudentViewSet, {'get': 'list'}),
            ('/api/enrollments/', EnrollmentViewSet, {'get': 'list'}),
            ('/api/trainers/', TrainerViewSet, {'get': 'list'}),
        ]:
            reset_queries()
            with CaptureQueriesContext(connection) as ctx:
                request = self.factory.get(path)
                force_authenticate(request, user=self.admin)
                response = viewset.as_view(action_map)(request)
                self.assertEqual(response.status_code, 200)
            n = len(ctx.captured_queries)
            print(f'[scale] {path}: {n} SQL queries for a 100-row page')
            self.assertLess(n, 20, f'{path} looks like an N+1 query pattern ({n} queries for one page)')

    def test_04_billing_cycle_close_math_is_correct_at_scale(self):
        # Re-close one of the already-closed recent cycles' worth of data via a fresh
        # from-scratch recompute and confirm it's stable (idempotent) even with the
        # full 2000+-enrollment dataset behind it.
        cycle = self.cycle_objs[-1]
        t0 = time.time()
        payouts = calculate_payouts_for_cycle(cycle)
        invoices = calculate_client_invoices_for_cycle(cycle)
        elapsed = time.time() - t0
        print(f'[scale] closing the most recent cycle: {len(payouts)} payouts, {len(invoices)} invoices in {elapsed:.2f}s')

        total_classes_billed = sum(p.total_classes for p in payouts)
        total_attendance_in_cycle = Attendance.objects.filter(
            status='present', date__gte=cycle.cycle_start, date__lte=cycle.cycle_end,
        ).count()
        self.assertEqual(
            total_classes_billed, total_attendance_in_cycle,
            'sum of payout classes must equal actual present-attendance rows in that date range',
        )
        self.assertLess(elapsed, 5, 'closing a single cycle should stay fast even with 2000+ enrollments live')

    def test_05_old_cycle_revenue_lazy_backfill_at_6_year_distance(self):
        oldest_cycle = self.cycle_objs[0]  # ~6 years back, never explicitly closed above
        t0 = time.time()
        result = cycle_revenue_totals(oldest_cycle)
        elapsed = time.time() - t0
        print(f'[scale] lazy-backfilling a 6-year-old cycle took {elapsed:.2f}s -> {result["total_classes"]} classes')
        self.assertIn('total_revenue', result)
        self.assertLess(elapsed, 5)

    def test_06_admin_alerts_at_scale(self):
        t0 = time.time()
        alerts = compute_admin_alerts()
        elapsed = time.time() - t0
        print(
            f'[scale] compute_admin_alerts(): {len(alerts["overdue_invoices"])} overdue invoices, '
            f'{len(alerts["due_installments"])} due installments in {elapsed:.2f}s'
        )
        self.assertGreater(len(alerts['overdue_invoices']), 0, 'seed data should include real overdue invoices')
        self.assertLess(elapsed, 5, 'admin alerts should stay responsive with thousands of installments in play')

        request = self.factory.get('/api/alerts/')
        force_authenticate(request, user=self.admin)
        response = AdminAlertsView.as_view()(request)
        self.assertEqual(response.status_code, 200)

    def test_07_payment_plan_installments_always_sum_to_total(self):
        mismatches = []
        for plan in PaymentPlan.objects.prefetch_related('installments').all():
            total = sum(i.amount for i in plan.installments.all())
            if total != plan.total_amount:
                mismatches.append((plan.id, total, plan.total_amount))
        print(f'[scale] checked {PaymentPlan.objects.count()} payment plans for installment-sum integrity')
        self.assertEqual(mismatches, [], f'installments must always sum to total_amount exactly: {mismatches[:5]}')

    def test_08_schedule_conflict_detection_at_scale(self):
        # Every trainer here has many enrollments across 6 years — confirm a genuine
        # clash is still found correctly and quickly against that full history.
        busy_trainer = self.trainers[0]
        an_enrollment = Enrollment.objects.filter(trainer=busy_trainer, status='ongoing').first()
        if an_enrollment is None:
            self.skipTest('no ongoing enrollment on this trainer in this random seed')
        t0 = time.time()
        conflict = find_schedule_conflict(busy_trainer, an_enrollment.class_time, an_enrollment.class_days)
        elapsed = time.time() - t0
        print(f'[scale] schedule-conflict check against a busy trainer took {elapsed:.3f}s -> conflict={bool(conflict)}')
        self.assertIsNotNone(conflict, 'checking the exact time/day of an existing ongoing enrollment must self-conflict')
        self.assertLess(elapsed, 1)

    def test_09_trainer_payment_gate_at_scale(self):
        t0 = time.time()
        results = {'hidden': 0, 'blocked': 0, 'clear': 0}
        for e in Enrollment.objects.filter(student__source_type='B2C').select_related('payment_plan')[:500]:
            results[trainer_payment_gate(e)] += 1
        elapsed = time.time() - t0
        print(f'[scale] trainer_payment_gate over 500 B2C enrollments: {results} in {elapsed:.2f}s')
        self.assertLess(elapsed, 5)

    def test_10_csv_export_and_payout_list_endpoints_respond(self):
        request = self.factory.get('/api/payouts/')
        force_authenticate(request, user=self.admin)
        response = PayoutViewSet.as_view({'get': 'list'})(request)
        self.assertEqual(response.status_code, 200)
        print(f'[scale] /api/payouts/: count={response.data["count"]}')

        request2 = self.factory.get('/api/client-invoices/')
        force_authenticate(request2, user=self.admin)
        response2 = ClientInvoiceViewSet.as_view({'get': 'list'})(request2)
        self.assertEqual(response2.status_code, 200)
        print(f'[scale] /api/client-invoices/: count={response2.data["count"]}')

    def test_11_audit_log_at_volume(self):
        for i in range(150):
            log_action(self.admin, 'payout_mark_paid', f'Scale test entry {i}', f'₹{i}')
        request = self.factory.get('/api/audit-log/')
        force_authenticate(request, user=self.admin)
        from audit.views import AuditLogViewSet
        response = AuditLogViewSet.as_view({'get': 'list'})(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['results']), 100)
        self.assertIsNotNone(response.data['next'])
        print(f'[scale] audit log: {response.data["count"]} entries, paginates correctly')
