import calendar
from datetime import date
from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.db.models import Count, Sum

from attendance.models import Attendance
from clients.models import Client
from clients.services import client_totals
from courses.models import Course
from enrollments.models import PaymentInstallment
from trainers.models import Trainer, TrainerCourseRate

from .models import (
    B2CRevenueAdjustment,
    BillingCycle,
    ClientInvoice,
    ClientInvoiceAdjustment,
    CycleRevenueSnapshot,
    Payout,
    PayoutAdjustment,
    RateHistory,
)

# Sentinel "since the beginning" effective date for the first-ever logged value of a
# rate — used so a lookup for any real, pre-existing class date resolves to that
# original value rather than finding no history at all. See log_rate_change().
RATE_HISTORY_EPOCH = date(2000, 1, 1)


def log_rate_change(entity, course, old_rate, new_rate, effective_date=None):
    """Record that `entity`'s (Client/Trainer/Course) rate for `course` (None
    for a flat rate) changed from old_rate to new_rate, so historical_rate()
    can look it up later. Called from each rate field's owning model's save()
    whenever the value actually changes — see RateHistory.

    On the very first logged change for a given entity+course, also backfills
    a row for the old value at RATE_HISTORY_EPOCH, so a lookup for any
    pre-existing class date still resolves correctly instead of finding no
    history and silently falling back to today's rate.
    """
    if old_rate == new_rate:
        return
    effective_date = effective_date or date.today()
    content_type = ContentType.objects.get_for_model(entity)
    has_history = RateHistory.objects.filter(
        content_type=content_type, object_id=entity.pk, course=course
    ).exists()
    if not has_history and old_rate is not None:
        RateHistory.objects.create(
            content_type=content_type, object_id=entity.pk, course=course,
            rate_per_class=old_rate, effective_from=RATE_HISTORY_EPOCH,
        )
    if new_rate is not None:
        RateHistory.objects.create(
            content_type=content_type, object_id=entity.pk, course=course,
            rate_per_class=new_rate, effective_from=effective_date,
        )


def historical_rate(entity, course, as_of_date):
    """The rate that was in effect for `entity` (a Client, a Trainer, or a
    Course itself for its own flat B2C price) x `course` (None for a flat
    rate) on as_of_date — mirrors Client.rate_for()/Trainer.rate_for()'s
    override-then-flat precedence, just at a point in the past instead of now.

    Returns None if there's no tracked history predating that date, meaning
    this rate has simply never changed since tracking began — the caller
    should fall back to the live rate_for()/rate_per_class in that case.
    """
    content_type = ContentType.objects.get_for_model(entity)
    qs = RateHistory.objects.filter(
        content_type=content_type, object_id=entity.pk, effective_from__lte=as_of_date
    )
    if course is not None:
        override = qs.filter(course=course).order_by('-effective_from', '-id').first()
        if override:
            return override.rate_per_class
    flat = qs.filter(course__isnull=True).order_by('-effective_from', '-id').first()
    return flat.rate_per_class if flat else None


def cycle_bounds_for_date(d):
    """1st-15th or 16th-month-end, whichever half `d` falls in."""
    if d.day <= 15:
        return d.replace(day=1), d.replace(day=15)
    last_day = calendar.monthrange(d.year, d.month)[1]
    return d.replace(day=16), d.replace(day=last_day)


def get_or_create_cycle(for_date=None):
    for_date = for_date or date.today()
    start, end = cycle_bounds_for_date(for_date)
    return BillingCycle.objects.get_or_create(cycle_start=start, cycle_end=end)


def trainer_totals_for_range(trainer, start, end):
    """Present classes and earnings for one trainer between start/end (inclusive), by course rate.

    Excludes attendance already carried forward via a PayoutAdjustment — its earnings
    are deliberately booked on a different cycle (see PayoutAdjustment), so counting
    it here too would double-pay the class.
    """
    course_counts = (
        Attendance.objects.filter(
            marked_by=trainer,
            status='present',
            date__gte=start,
            date__lte=end,
            payout_adjustment__isnull=True,
        )
        .values('enrollment__course')
        .annotate(count=Count('id'))
    )

    overrides = {
        r.course_id: r.rate_per_class
        for r in TrainerCourseRate.objects.filter(trainer=trainer)
    }
    default_rate = trainer.default_rate_per_class or Decimal('0.00')

    total_classes = 0
    total_amount = Decimal('0.00')
    for row in course_counts:
        course_id = row['enrollment__course']
        count = row['count']
        rate = overrides.get(course_id, default_rate)
        total_classes += count
        total_amount += rate * count

    return total_classes, total_amount


def current_cycle_summary(trainer):
    """Live totals for a trainer's in-progress cycle, including any PayoutAdjustment
    amounts already assigned to this cycle (added when a late-approved class's own
    cycle had already been paid out).

    These are never "pending" — they're assigned to the current cycle the moment
    they're created, so they show up here immediately rather than waiting for a
    future cycle to close.
    """
    start, end = cycle_bounds_for_date(date.today())
    cycle, _ = get_or_create_cycle()
    total_classes, total_amount = trainer_totals_for_range(trainer, start, end)

    adjustments = PayoutAdjustment.objects.filter(trainer=trainer, applied_cycle=cycle)
    adjustment_total = adjustments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    adjustment_count = adjustments.count()

    return {
        'cycle_start': start,
        'cycle_end': end,
        'total_classes': total_classes + adjustment_count,
        'total_amount': total_amount + adjustment_total,
        'carried_forward_amount': adjustment_total,
        'carried_forward_count': adjustment_count,
    }


def client_current_cycle_totals(client, cycle=None, as_of=None):
    """Totals for a client's billing cycle — "current" by default, but works
    for any cycle you pass, using *that cycle's own* date range. Also folds in
    any ClientInvoiceAdjustment amounts already assigned to it (added when a
    late-approved class's own cycle had already been invoiced to the client).

    Unlike PayoutAdjustment, these are never "pending" — they're assigned to the
    current cycle the moment they're created, so they show up here immediately
    rather than waiting for a future cycle to close.

    Pass an already-resolved `cycle` when calling this for many clients in one
    request (e.g. a list/summary endpoint) to skip the redundant
    get_or_create_cycle() round trip on every call. Pass `as_of` to price at a
    past date's rate — see client_totals().
    """
    if cycle is None:
        cycle, _ = get_or_create_cycle()
    totals = client_totals(client, cycle.cycle_start, cycle.cycle_end, as_of=as_of)

    adjustments = ClientInvoiceAdjustment.objects.filter(client=client, applied_cycle=cycle)
    adjustment_agg = adjustments.aggregate(amount=Sum('amount'), trainer_cost=Sum('trainer_cost'))
    adjustment_total = adjustment_agg['amount'] or Decimal('0.00')
    adjustment_trainer_cost = adjustment_agg['trainer_cost'] or Decimal('0.00')
    adjustment_count = adjustments.count()

    return {
        'cycle_start': cycle.cycle_start,
        'cycle_end': cycle.cycle_end,
        'total_classes': totals['total_classes'] + adjustment_count,
        'total_revenue': totals['total_revenue'] + adjustment_total,
        'trainer_cost': totals['trainer_cost'] + adjustment_trainer_cost,
        'our_earning': totals['our_earning'] + adjustment_total - adjustment_trainer_cost,
        'carried_forward_amount': adjustment_total,
        'carried_forward_count': adjustment_count,
    }


def client_all_time_totals(client):
    """All-time totals for a client. client_totals() alone now excludes attendance
    carried forward via a ClientInvoiceAdjustment (to avoid double-billing it on
    both its original date and its diverted cycle), so add every such adjustment's
    amount back in here — every one of them represents a real class that must be
    counted exactly once somewhere, and this is the "somewhere" for an all-time view.
    """
    totals = client_totals(client)

    adjustments = ClientInvoiceAdjustment.objects.filter(client=client)
    adjustment_agg = adjustments.aggregate(amount=Sum('amount'), trainer_cost=Sum('trainer_cost'))
    adjustment_total = adjustment_agg['amount'] or Decimal('0.00')
    adjustment_trainer_cost = adjustment_agg['trainer_cost'] or Decimal('0.00')
    adjustment_count = adjustments.count()

    return {
        'total_classes': totals['total_classes'] + adjustment_count,
        'total_revenue': totals['total_revenue'] + adjustment_total,
        'trainer_cost': totals['trainer_cost'] + adjustment_trainer_cost,
        'our_earning': totals['our_earning'] + adjustment_total - adjustment_trainer_cost,
    }


def b2c_totals_for_range(start, end, as_of=None):
    """Present classes, accrued revenue, trainer cost, and our margin for B2C
    students between start/end (inclusive). Mirrors client_totals()'s shape and
    method exactly, just swapping the client's per-course billing rate for
    Course.rate_per_class (the flat B2C price list) and scoping to B2C students
    instead of one client's students.

    Revenue is priced by classes taught x rate (same accrual model as B2B)
    rather than tracking when a payment-plan installment actually gets paid — a
    B2C parent's payment schedule is milestone-based (see PaymentPlan) and
    rarely lines up with a billing cycle's date range, so it isn't a usable
    basis for "revenue this cycle". This is the figure used for the admin
    dashboard's cycle revenue card.

    Excludes attendance already carried forward via a B2CRevenueAdjustment —
    its revenue is deliberately booked on a different cycle (see
    B2CRevenueAdjustment), so counting it here too would double-count the class.

    Pass `as_of` to price using the rate that was in effect on that date
    instead of today's live rate — see client_totals()'s `as_of`.
    """
    rows = (
        Attendance.objects.filter(
            status='present',
            date__gte=start,
            date__lte=end,
            enrollment__student__source_type='B2C',
            b2c_revenue_adjustment__isnull=True,
        )
        .values('marked_by', 'enrollment__course')
        .annotate(count=Count('id'))
    )

    trainer_ids = {row['marked_by'] for row in rows}
    trainers = {t.id: t for t in Trainer.objects.filter(id__in=trainer_ids)}
    trainer_overrides = {
        (r.trainer_id, r.course_id): r.rate_per_class
        for r in TrainerCourseRate.objects.filter(trainer_id__in=trainer_ids)
    }
    course_rates = {c.id: c.rate_per_class or Decimal('0.00') for c in Course.objects.all()}
    courses_by_id = {}
    if as_of is not None:
        course_ids = {row['enrollment__course'] for row in rows}
        courses_by_id = {c.id: c for c in Course.objects.filter(id__in=course_ids)}

    total_classes = 0
    total_revenue = Decimal('0.00')
    trainer_cost = Decimal('0.00')
    for row in rows:
        trainer_id = row['marked_by']
        course_id = row['enrollment__course']
        count = row['count']
        trainer = trainers[trainer_id]

        if as_of is not None:
            trainer_rate = historical_rate(trainer, course_id, as_of)
            if trainer_rate is None:
                trainer_rate = trainer_overrides.get((trainer_id, course_id), trainer.default_rate_per_class or Decimal('0.00'))
            course_rate = historical_rate(courses_by_id[course_id], None, as_of)
            if course_rate is None:
                course_rate = course_rates.get(course_id, Decimal('0.00'))
        else:
            trainer_rate = trainer_overrides.get((trainer_id, course_id), trainer.default_rate_per_class or Decimal('0.00'))
            course_rate = course_rates.get(course_id, Decimal('0.00'))

        total_classes += count
        total_revenue += course_rate * count
        trainer_cost += trainer_rate * count

    return {
        'total_classes': total_classes,
        'total_revenue': total_revenue,
        'trainer_cost': trainer_cost,
        'our_earning': total_revenue - trainer_cost,
    }


def b2c_current_cycle_totals(cycle, as_of=None):
    """Live B2C totals for a cycle, including any B2CRevenueAdjustment amounts
    already assigned to it (added when a late-approved B2C class's own cycle
    had already been snapshotted/closed). Mirrors client_current_cycle_totals()
    for B2B — see B2CRevenueAdjustment.

    Used both for the still-open cycle (live) and inside snapshot_cycle_revenue
    when a cycle closes, so any adjustment already routed to it (from an even
    earlier closed cycle's late approval) gets folded into its own snapshot.
    Pass `as_of` to price at a past date's rate — see client_totals().
    """
    totals = b2c_totals_for_range(cycle.cycle_start, cycle.cycle_end, as_of=as_of)

    adjustments = B2CRevenueAdjustment.objects.filter(applied_cycle=cycle)
    adjustment_agg = adjustments.aggregate(amount=Sum('amount'), trainer_cost=Sum('trainer_cost'))
    adjustment_amount = adjustment_agg['amount'] or Decimal('0.00')
    adjustment_trainer_cost = adjustment_agg['trainer_cost'] or Decimal('0.00')
    adjustment_count = adjustments.count()

    total_revenue = totals['total_revenue'] + adjustment_amount
    trainer_cost = totals['trainer_cost'] + adjustment_trainer_cost

    return {
        'total_classes': totals['total_classes'] + adjustment_count,
        'total_revenue': total_revenue,
        'trainer_cost': trainer_cost,
        'our_earning': total_revenue - trainer_cost,
    }


def current_payouts_for_cycle(cycle):
    """Live preview of what calculate_payouts_for_cycle() would produce for this
    cycle if it were closed right now — same computation, but read-only and
    nothing is persisted. Powers the admin Payouts page's still-open cycle row,
    so it shows real per-trainer numbers instead of "not closed yet". Since
    it's recomputed from Attendance on every request rather than cached, a
    trainer marking or deleting an attendance record is reflected the next time
    this is fetched, with no extra recalculation step needed.
    """
    trainer_ids = set(
        Attendance.objects.filter(
            status='present',
            date__gte=cycle.cycle_start,
            date__lte=cycle.cycle_end,
        ).values_list('marked_by_id', flat=True)
    )
    trainer_ids |= set(
        PayoutAdjustment.objects.filter(applied_cycle=cycle).values_list('trainer_id', flat=True)
    )

    rows = []
    for trainer in Trainer.objects.filter(id__in=trainer_ids).order_by('name'):
        total_classes, total_amount = trainer_totals_for_range(trainer, cycle.cycle_start, cycle.cycle_end)

        adjustments = PayoutAdjustment.objects.filter(trainer=trainer, applied_cycle=cycle)
        adjustment_total = adjustments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        adjustment_count = adjustments.count()

        rows.append({
            'trainer': trainer.id,
            'trainer_name': trainer.name,
            'total_classes': total_classes + adjustment_count,
            'total_amount': total_amount + adjustment_total,
            'carried_forward_amount': adjustment_total,
            'carried_forward_count': adjustment_count,
        })
    return rows


def calculate_payouts_for_cycle(cycle):
    """
    For each trainer with present attendance in this cycle: group by course,
    multiply count x TrainerCourseRate, sum -> upsert a Payout row. Any
    PayoutAdjustment already assigned to this cycle (see current_cycle_summary)
    is folded in on top — those were carried forward from a late-approved class
    whose own cycle had already been paid out, so they ride along with whatever
    this cycle pays. Trainers with no present attendance and no adjustment are
    left without a Payout row.
    """
    trainer_ids = set(
        Attendance.objects.filter(
            status='present',
            date__gte=cycle.cycle_start,
            date__lte=cycle.cycle_end,
        ).values_list('marked_by_id', flat=True)
    )
    trainer_ids |= set(
        PayoutAdjustment.objects.filter(applied_cycle=cycle).values_list('trainer_id', flat=True)
    )

    payouts = []
    for trainer in Trainer.objects.filter(id__in=trainer_ids):
        total_classes, total_amount = trainer_totals_for_range(trainer, cycle.cycle_start, cycle.cycle_end)

        adjustments = PayoutAdjustment.objects.filter(trainer=trainer, applied_cycle=cycle)
        adjustment_total = adjustments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        total_classes += adjustments.count()
        total_amount += adjustment_total

        payout, _ = Payout.objects.update_or_create(
            trainer=trainer,
            cycle=cycle,
            defaults={'total_classes': total_classes, 'total_amount': total_amount},
        )
        payouts.append(payout)

    return payouts


def calculate_client_invoices_for_cycle(cycle):
    """
    For each B2B client with present attendance in this cycle: group by course,
    bill at the client's rate, sum -> upsert a ClientInvoice row. Any
    ClientInvoiceAdjustment already assigned to this cycle (see
    client_current_cycle_totals) is folded in on top — those were carried
    forward from a late-approved class whose own cycle had already been
    invoiced, so they ride along with whatever this cycle bills.
    Clients with no present attendance and no adjustment are left without an invoice row.
    """
    client_ids = set(
        Attendance.objects.filter(
            status='present',
            date__gte=cycle.cycle_start,
            date__lte=cycle.cycle_end,
            enrollment__student__client__isnull=False,
        ).values_list('enrollment__student__client_id', flat=True)
    )
    client_ids |= set(
        ClientInvoiceAdjustment.objects.filter(applied_cycle=cycle).values_list('client_id', flat=True)
    )

    invoices = []
    for client in Client.objects.filter(id__in=client_ids):
        totals = client_totals(client, cycle.cycle_start, cycle.cycle_end)

        adjustments = ClientInvoiceAdjustment.objects.filter(client=client, applied_cycle=cycle)
        adjustment_total = adjustments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
        total_classes = totals['total_classes'] + adjustments.count()
        total_amount = totals['total_revenue'] + adjustment_total

        invoice, _ = ClientInvoice.objects.update_or_create(
            client=client,
            cycle=cycle,
            defaults={'total_classes': total_classes, 'total_amount': total_amount},
        )
        invoices.append(invoice)

    return invoices


def snapshot_cycle_revenue(cycle):
    """Freeze this cycle's B2B/B2C classes/revenue/trainer-cost split into a
    CycleRevenueSnapshot. Called once, from BillingCycleViewSet.close(), right
    alongside calculate_payouts_for_cycle/calculate_client_invoices_for_cycle —
    the same moment those other frozen records get created.

    Uses client_current_cycle_totals()/b2c_current_cycle_totals() rather than
    the raw client_totals()/b2c_totals_for_range(), so that any
    ClientInvoiceAdjustment/B2CRevenueAdjustment already routed to this cycle
    (from an even earlier closed cycle's late-approved class) is folded in —
    same as calculate_payouts_for_cycle/calculate_client_invoices_for_cycle
    already do for Payout/ClientInvoice.

    Prices everything as of this cycle's own cycle_end — not today — so that a
    rate change made after this cycle closed can't silently reprice it. This
    matters most for the lazy-backfill path: CycleRevenueView calls this for
    any closed cycle that doesn't have a snapshot yet, which can happen long
    after that cycle actually closed (e.g. an old cycle from before this
    snapshot mechanism existed, viewed for the first time today).

    An update_or_create upsert, so it's safe to call again for a cycle that
    already has a snapshot — it will simply recompute and overwrite it.
    """
    as_of = cycle.cycle_end

    b2b_classes = 0
    b2b_revenue = Decimal('0.00')
    b2b_trainer_cost = Decimal('0.00')
    for client in Client.objects.all():
        totals = client_current_cycle_totals(client, cycle=cycle, as_of=as_of)
        b2b_classes += totals['total_classes']
        b2b_revenue += totals['total_revenue']
        b2b_trainer_cost += totals['trainer_cost']

    b2c = b2c_current_cycle_totals(cycle, as_of=as_of)

    snapshot, _ = CycleRevenueSnapshot.objects.update_or_create(
        cycle=cycle,
        defaults={
            'b2b_classes': b2b_classes,
            'b2b_revenue': b2b_revenue,
            'b2b_trainer_cost': b2b_trainer_cost,
            'b2c_classes': b2c['total_classes'],
            'b2c_revenue': b2c['total_revenue'],
            'b2c_trainer_cost': b2c['trainer_cost'],
        },
    )
    return snapshot


def cycle_revenue_totals(cycle):
    """B2B/B2C classes, revenue, trainer cost, and profit for one BillingCycle —
    the shared computation behind both CycleRevenueView (single cycle) and
    CycleRevenueHistoryView (many cycles), so the two never drift apart.

    The still-open cycle is computed live (rates can and should move it, same
    as every other "current cycle" figure elsewhere in the app). A closed cycle
    instead reads its CycleRevenueSnapshot, frozen the moment it closed, so a
    trainer/course rate change made afterward can't rewrite the profit of a
    cycle that's already been invoiced and paid out — backfilled lazily here if
    it closed before that snapshot existed.
    """
    if cycle.status == 'open':
        b2b_classes = 0
        b2b_revenue = Decimal('0.00')
        b2b_trainer_cost = Decimal('0.00')
        for client in Client.objects.filter(status='active'):
            totals = client_current_cycle_totals(client, cycle=cycle)
            b2b_classes += totals['total_classes']
            b2b_revenue += totals['total_revenue']
            b2b_trainer_cost += totals['trainer_cost']

        b2c = b2c_current_cycle_totals(cycle)
        b2c_classes = b2c['total_classes']
        b2c_revenue = b2c['total_revenue']
        b2c_trainer_cost = b2c['trainer_cost']
    else:
        snapshot = getattr(cycle, 'revenue_snapshot', None) or snapshot_cycle_revenue(cycle)
        b2b_classes = snapshot.b2b_classes
        b2b_revenue = snapshot.b2b_revenue
        b2b_trainer_cost = snapshot.b2b_trainer_cost
        b2c_classes = snapshot.b2c_classes
        b2c_revenue = snapshot.b2c_revenue
        b2c_trainer_cost = snapshot.b2c_trainer_cost

    b2b_profit = b2b_revenue - b2b_trainer_cost
    b2c_profit = b2c_revenue - b2c_trainer_cost

    return {
        'cycle_id': cycle.id,
        'cycle_start': cycle.cycle_start,
        'cycle_end': cycle.cycle_end,
        'status': cycle.status,
        'b2b_classes': b2b_classes,
        'b2b_revenue': b2b_revenue,
        'b2b_trainer_cost': b2b_trainer_cost,
        'b2b_profit': b2b_profit,
        'b2c_classes': b2c_classes,
        'b2c_revenue': b2c_revenue,
        'b2c_trainer_cost': b2c_trainer_cost,
        'b2c_profit': b2c_profit,
        'total_classes': b2b_classes + b2c_classes,
        'total_revenue': b2b_revenue + b2c_revenue,
        'total_trainer_cost': b2b_trainer_cost + b2c_trainer_cost,
        'total_profit': b2b_profit + b2c_profit,
    }


def compute_admin_alerts():
    """Things needing admin attention right now: overdue B2B invoices and B2C
    installments that have reached their due milestone but are still unpaid.
    Computed live rather than stored — same as every other "current state"
    figure in this app. Shared by AdminAlertsView (the dashboard's live view)
    and the send_admin_digest management command (an emailed summary, for
    admins who don't have the dashboard open) so the two can't drift apart.
    """
    overdue_invoices = []
    for inv in ClientInvoice.objects.select_related('client', 'cycle').filter(
        status='pending', cycle__status='closed'
    ):
        if inv.is_overdue:
            overdue_invoices.append({
                'id': inv.id,
                'client_id': inv.client_id,
                'client_name': inv.client.company_name,
                'cycle_start': inv.cycle.cycle_start,
                'cycle_end': inv.cycle.cycle_end,
                'amount': inv.total_amount,
                'days_overdue': inv.days_overdue,
            })
    overdue_invoices.sort(key=lambda row: -row['days_overdue'])

    due_installments = []
    installments = PaymentInstallment.objects.select_related(
        'plan__enrollment__student', 'plan__enrollment__course'
    ).filter(paid_status='pending')
    for inst in installments:
        enrollment = inst.plan.enrollment
        is_due = inst.due_at_classes is None or enrollment.classes_completed >= inst.due_at_classes - 1
        if is_due:
            due_installments.append({
                'id': inst.id,
                'student_id': enrollment.student_id,
                'student_name': enrollment.student.name,
                'course_name': enrollment.course.name,
                'sequence': inst.sequence,
                'amount': inst.amount,
                'due_at_classes': inst.due_at_classes,
                'classes_completed': enrollment.classes_completed,
            })

    return {
        'overdue_invoices': overdue_invoices,
        'due_installments': due_installments,
    }
