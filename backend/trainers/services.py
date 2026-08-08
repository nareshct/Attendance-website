def get_archive_blockers(trainer):
    """Everything still tying this trainer to active/unresolved work — shown as a
    checklist (with inline resolve actions) before an archive is allowed to go
    through. See TrainerViewSet.archive/.archive_blockers.

    Imported lazily, not at module level — same reasoning as config.views.SearchView:
    keeps the trainers app from taking a hard import dependency on every domain app
    that happens to reference Trainer.
    """
    from django.utils import timezone

    from attendance.models import AttendanceRequest
    from batches.models import Batch, BatchPayout
    from batches.services import batch_ids_for_trainer
    from billing.models import Payout
    from billing.services import current_cycle_summary
    from enrollments.models import Enrollment, SubstituteAssignment

    ongoing_enrollments = Enrollment.objects.filter(
        trainer=trainer, status='ongoing',
    ).select_related('student', 'course').order_by('student__name')

    batch_ids = batch_ids_for_trainer(trainer.name)
    ongoing_batches = Batch.objects.filter(id__in=batch_ids, status='ongoing').select_related('course').order_by('name')

    pending_requests = AttendanceRequest.objects.filter(
        requested_by=trainer, status='pending',
    ).select_related('enrollment__student', 'enrollment__course').order_by('date')

    pending_payouts = Payout.objects.filter(
        trainer=trainer, paid_status='pending',
    ).select_related('cycle').order_by('cycle__cycle_start')

    # BatchPayout.recipient_name is free text, matched the same case-insensitive way
    # BatchPayoutViewSet.get_queryset() already scopes a trainer to their own payouts.
    pending_batch_payouts = BatchPayout.objects.filter(
        recipient_name__iexact=trainer.name, paid_status='pending',
    ).select_related('batch').order_by('batch__name')

    # "Active" per SubstituteAssignment's own docstring: today falls in [start_date,
    # end_date], or it hasn't started yet — either way this trainer is still on the
    # hook to cover someone else's classes. A window that's already fully in the past
    # needs no action (it already happened).
    today = timezone.now().date()
    active_substitute_assignments = SubstituteAssignment.objects.filter(
        substitute_trainer=trainer, end_date__gte=today,
    ).select_related('enrollment__student', 'enrollment__course').order_by('start_date')

    # The current cycle is still open — nothing here is a Payout row yet (those are
    # only ever created when a cycle formally closes, for every trainer at once), so
    # pending_payouts above can't see this. But it's real, already-earned money —
    # including any carried-forward PayoutAdjustment from a late-approved attendance
    # request (see AttendanceRequestViewSet.approve) — that would otherwise silently
    # sit unpaid until the cycle closes on its own schedule, possibly weeks away.
    # See TrainerViewSet.settle_current_cycle for how this gets resolved.
    #
    # current_cycle_summary() recomputes from Attendance/PayoutAdjustment every
    # time, regardless of whether it's already been settled — so this compares
    # against any existing Payout for this exact cycle by amount, not just
    # existence. A settled Payout whose total no longer matches the live total
    # (e.g. an attendance request got approved for this cycle after settling)
    # must still show up here — see settle_trainer_current_cycle for how a
    # mismatch against an already-paid/cancelled Payout gets refused rather
    # than silently overwritten.
    current_cycle = current_cycle_summary(trainer)
    settled_payout = Payout.objects.filter(
        trainer=trainer, cycle__cycle_start=current_cycle['cycle_start'], cycle__cycle_end=current_cycle['cycle_end'],
    ).first()
    current_cycle_fully_settled = settled_payout is not None and settled_payout.total_amount == current_cycle['total_amount']

    return {
        'ongoing_enrollments': [
            {
                'id': e.id,
                'student_name': e.student.name,
                'course_name': e.course.name,
                'class_time': e.class_time,
                'class_days': e.class_days,
            }
            for e in ongoing_enrollments
        ],
        'ongoing_batches': [
            {
                'id': b.id,
                'name': b.name,
                'course_name': b.course.name,
                'trainer_names': b.trainer_names,
            }
            for b in ongoing_batches
        ],
        'pending_attendance_requests': [
            {
                'id': r.id,
                'date': r.date,
                'student_name': r.enrollment.student.name,
                'course_name': r.enrollment.course.name,
                'topic_covered': r.topic_covered,
            }
            for r in pending_requests
        ],
        'pending_payouts': [
            {
                'id': p.id,
                'cycle_start': p.cycle.cycle_start,
                'cycle_end': p.cycle.cycle_end,
                'total_amount': p.total_amount,
            }
            for p in pending_payouts
        ],
        'pending_batch_payouts': [
            {
                'id': p.id,
                'batch_id': p.batch_id,
                'batch_name': p.batch.name,
                'amount': p.amount,
            }
            for p in pending_batch_payouts
        ],
        'active_substitute_assignments': [
            {
                'id': a.id,
                'student_name': a.enrollment.student.name,
                'course_name': a.enrollment.course.name,
                'start_date': a.start_date,
                'end_date': a.end_date,
            }
            for a in active_substitute_assignments
        ],
        'current_cycle_earnings': (
            [{
                'cycle_start': current_cycle['cycle_start'],
                'cycle_end': current_cycle['cycle_end'],
                'total_classes': current_cycle['total_classes'],
                'total_amount': current_cycle['total_amount'],
                'carried_forward_amount': current_cycle['carried_forward_amount'],
                'carried_forward_count': current_cycle['carried_forward_count'],
            }]
            if current_cycle['total_classes'] > 0 and not current_cycle_fully_settled else []
        ),
    }
