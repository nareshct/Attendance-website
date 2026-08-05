from decimal import Decimal

from django.db.models import Count

from attendance.models import Attendance
from trainers.models import Trainer, TrainerCourseRate


def client_totals(client, start=None, end=None, as_of=None):
    """Classes taken, revenue billed to the client, trainer cost, and our margin.

    Scoped to [start, end] (inclusive) when given, else all-time. Both the trainer's
    cost and the client's billing rate use a course-specific override when one
    exists, else fall back to each side's flat default rate.

    Pass `as_of` to price every class at the single rate that was in effect on that
    one date — used when freezing a closed billing cycle's snapshot (see
    billing.services.snapshot_cycle_revenue), where "the whole cycle priced as of
    its own close" is the correct model (a cycle is a couple of weeks; a rate
    changing mid-cycle is an accepted edge case there).

    Without `as_of` (the all-time / multi-cycle case), each class is instead priced
    individually at whatever rate was actually in effect on *that class's own date*
    — a single as_of date would be wrong here, since the span can cross a rate
    change and a class from before it must still be priced at the old rate rather
    than today's live one.
    """
    from billing.services import historical_rate  # deferred: avoids a cross-app import cycle

    # Exclude attendance already carried forward via a ClientInvoiceAdjustment — its
    # revenue is deliberately billed on a different cycle (see ClientInvoiceAdjustment),
    # so counting it here too would double-bill the class.
    qs = Attendance.objects.filter(
        status='present', enrollment__student__client=client, invoice_adjustment__isnull=True,
    )
    if start is not None:
        qs = qs.filter(date__gte=start)
    if end is not None:
        qs = qs.filter(date__lte=end)

    # Grouped by date too (not just trainer+course) when as_of isn't fixing the whole
    # query to one date — classes on different dates can fall either side of a rate
    # change, so each date's group needs its own rate lookup.
    group_fields = ['marked_by', 'enrollment__course'] if as_of is not None else ['marked_by', 'enrollment__course', 'date']
    rows = qs.values(*group_fields).annotate(count=Count('id'))

    trainer_ids = {row['marked_by'] for row in rows}
    trainers = {t.id: t for t in Trainer.objects.filter(id__in=trainer_ids)}
    trainer_overrides = {
        (r.trainer_id, r.course_id): r.rate_per_class
        for r in TrainerCourseRate.objects.filter(trainer_id__in=trainer_ids)
    }
    client_overrides = {
        r.course_id: r.rate_per_class
        for r in client.course_rates.all()
    }
    client_default_rate = client.rate_per_class or Decimal('0.00')

    total_classes = 0
    total_revenue = Decimal('0.00')
    trainer_cost = Decimal('0.00')
    for row in rows:
        trainer_id = row['marked_by']
        course_id = row['enrollment__course']
        count = row['count']
        trainer = trainers[trainer_id]
        price_date = as_of if as_of is not None else row['date']

        trainer_rate = historical_rate(trainer, course_id, price_date)
        if trainer_rate is None:
            trainer_rate = trainer_overrides.get((trainer_id, course_id), trainer.default_rate_per_class or Decimal('0.00'))
        client_rate = historical_rate(client, course_id, price_date)
        if client_rate is None:
            client_rate = client_overrides.get(course_id, client_default_rate)

        total_classes += count
        trainer_cost += trainer_rate * count
        total_revenue += client_rate * count

    our_earning = total_revenue - trainer_cost

    return {
        'total_classes': total_classes,
        'total_revenue': total_revenue,
        'trainer_cost': trainer_cost,
        'our_earning': our_earning,
    }


def client_course_breakdown(client, start, end):
    """Per-course classes/rate/amount for a client within [start, end] (inclusive),
    for itemized invoice line items. Same present-attendance scope as client_totals
    (excludes anything already carried forward via a ClientInvoiceAdjustment), so
    these rows sum to the same total_revenue client_totals would report.
    """
    rows = (
        Attendance.objects.filter(
            status='present', enrollment__student__client=client, invoice_adjustment__isnull=True,
            date__gte=start, date__lte=end,
        )
        .values('enrollment__course', 'enrollment__course__name')
        .annotate(count=Count('id'))
        .order_by('enrollment__course__name')
    )

    client_overrides = {r.course_id: r.rate_per_class for r in client.course_rates.all()}
    client_default_rate = client.rate_per_class or Decimal('0.00')

    breakdown = []
    for row in rows:
        rate = client_overrides.get(row['enrollment__course'], client_default_rate)
        count = row['count']
        breakdown.append({
            'course_name': row['enrollment__course__name'],
            'classes': count,
            'rate_per_class': rate,
            'amount': rate * count,
        })
    return breakdown
