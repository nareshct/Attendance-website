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
    group_fields = ['marked_by', 'enrollment__course', 'enrollment__trainer_rate_per_class', 'enrollment__client_rate_per_class']
    group_fields += [] if as_of is not None else ['date']
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

        # An enrollment-specific rate (set on the enrollment form) always wins over the
        # trainer's/client's own course rate — see Enrollment.trainer_rate_per_class /
        # client_rate_per_class. The trainer side applies to whoever actually taught the
        # class (the enrollment's own trainer or a substitute), since it prices the
        # batch, not the trainer.
        trainer_rate = row['enrollment__trainer_rate_per_class']
        if trainer_rate is None:
            trainer_rate = historical_rate(trainer, course_id, price_date)
            if trainer_rate is None:
                trainer_rate = trainer_overrides.get((trainer_id, course_id), trainer.default_rate_per_class or Decimal('0.00'))
        client_rate = row['enrollment__client_rate_per_class']
        if client_rate is None:
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


def get_archive_blockers(client):
    """Everything still tying this client to active/unresolved billing — hard-
    blocks ClientViewSet.archive() until it's empty. See ArchiveClientModal.

    Imported lazily, not at module level — same reasoning as config.views.SearchView:
    keeps the clients app from taking a hard import dependency on every domain app
    that happens to reference Client.
    """
    from django.db.models import Prefetch

    from billing.models import ClientInvoice
    from billing.services import client_current_cycle_totals
    from enrollments.models import Enrollment
    from students.models import Student

    active_students = Student.objects.filter(client=client, status='active').prefetch_related(
        Prefetch('enrollments', queryset=Enrollment.objects.select_related('course').order_by('course__name')),
    ).order_by('name')
    pending_invoices = ClientInvoice.objects.filter(
        client=client, status='pending', cycle__status='closed',
    ).select_related('cycle').order_by('cycle__cycle_start')
    current = client_current_cycle_totals(client)

    return {
        'active_students': [
            {
                'id': s.id,
                'name': s.name,
                'enrollments': [
                    {
                        'id': e.id,
                        'course_name': e.course.name,
                        'batch_number': e.batch_number,
                        'classes_completed': e.classes_completed,
                        'classes_total': e.classes_total,
                        'status': e.status,
                    }
                    for e in s.enrollments.all()
                ],
            }
            for s in active_students
        ],
        'pending_invoices': [
            {
                'id': inv.id,
                'cycle_start': inv.cycle.cycle_start,
                'cycle_end': inv.cycle.cycle_end,
                'amount': inv.total_amount,
            }
            for inv in pending_invoices
        ],
        'current_cycle_unbilled': current['total_revenue'],
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
        .values('enrollment__course', 'enrollment__course__name', 'enrollment__client_rate_per_class')
        .annotate(count=Count('id'))
        .order_by('enrollment__course__name')
    )

    client_overrides = {r.course_id: r.rate_per_class for r in client.course_rates.all()}
    client_default_rate = client.rate_per_class or Decimal('0.00')

    breakdown = []
    for row in rows:
        # See client_totals() — an enrollment-specific rate always wins.
        rate = row['enrollment__client_rate_per_class']
        if rate is None:
            rate = client_overrides.get(row['enrollment__course'], client_default_rate)
        count = row['count']
        breakdown.append({
            'course_name': row['enrollment__course__name'],
            'classes': count,
            'rate_per_class': rate,
            'amount': rate * count,
        })
    return breakdown
