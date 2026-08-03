from decimal import ROUND_HALF_UP, Decimal

from .models import PLAN_SCHEDULES, Enrollment, PaymentInstallment, PaymentPlan, SubstituteAssignment


def total_amount_for_discount(course, classes_total, discount_percent):
    """A B2C student's total course fee: the course's standard price
    (rate_per_class x classes_total) reduced by `discount_percent` (0-15, see
    MAX_B2C_DISCOUNT in enrollments/serializers.py — enforced there, not
    here). Rounded to the nearest paisa.
    """
    standard_total = (course.rate_per_class or Decimal('0.00')) * classes_total
    discount_percent = discount_percent or Decimal('0.00')
    return (standard_total * (1 - discount_percent / Decimal('100'))).quantize(Decimal('0.01'))


def upfront_payment_for(plan_type, total_amount, classes_total):
    """The amount due before class 1 for a B2C payment plan: the plan's first
    milestone's class count x this plan's own effective per-class rate
    (total_amount / classes_total) — not the course's flat rate_per_class, so
    a per-student discount on the total course fee (see EnrollmentSerializer's
    15%-max discount cap) is reflected proportionally in the upfront amount
    too, rather than always charging the undiscounted rate upfront. Rounded to
    the nearest whole rupee rather than charging fractional paise.
    """
    milestone_classes = PLAN_SCHEDULES[plan_type][1]
    effective_rate = (total_amount / classes_total) if classes_total else Decimal('0.00')
    whole_rupees = (Decimal(milestone_classes) * effective_rate).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    return whole_rupees.quantize(Decimal('0.01'))


def create_payment_plan(enrollment, plan_type, total_amount):
    """Build a PaymentPlan + its PaymentInstallment rows for a B2C enrollment.

    The first installment (due_at_classes=None) is always the plan's upfront
    payment — see upfront_payment_for() — due before the first class. The
    remainder is split evenly across the plan's other milestone installments,
    with the last one absorbing any rounding remainder so the installments
    always sum to exactly `total_amount`.
    """
    milestones = PLAN_SCHEDULES[plan_type]
    first_payment = upfront_payment_for(plan_type, total_amount, enrollment.classes_total)
    plan = PaymentPlan.objects.create(enrollment=enrollment, plan_type=plan_type, total_amount=total_amount)

    remaining = total_amount - first_payment
    remaining_count = len(milestones) - 1
    share = (remaining / remaining_count).quantize(Decimal('0.01')) if remaining_count else Decimal('0.00')

    installments = []
    for i, due_at_classes in enumerate(milestones, start=1):
        if due_at_classes is None:
            amount = first_payment
        elif i == len(milestones):
            # Last installment absorbs the rounding remainder so the total is exact.
            amount = remaining - share * (remaining_count - 1)
        else:
            amount = share
        installments.append(PaymentInstallment(
            plan=plan, sequence=i, due_at_classes=due_at_classes, amount=amount,
        ))

    PaymentInstallment.objects.bulk_create(installments)
    return plan


def trainer_payment_gate(enrollment):
    """Trainer-facing visibility gate for a B2C enrollment's payment plan.

    - 'hidden': the first payment hasn't been recorded yet — the enrollment (and the
      student's name) shouldn't appear to the trainer at all.
    - 'blocked': the first payment was recorded and classes started, but the student
      has reached a later milestone (e.g. the 6th class) without that installment
      being marked paid — the trainer keeps seeing the student's name, but the
      schedule/attendance-marking is paused until admin records the payment.
    - 'clear': no B2C payment plan, or nothing currently blocking.
    """
    plan = getattr(enrollment, 'payment_plan', None)
    if plan is None:
        return 'clear'

    installments = list(plan.installments.all())  # PaymentInstallment.Meta.ordering = ['sequence']
    if not installments:
        return 'clear'

    if installments[0].paid_status != 'paid':
        return 'hidden'

    for inst in installments[1:]:
        if (
            inst.paid_status != 'paid'
            and inst.due_at_classes is not None
            and enrollment.classes_completed >= inst.due_at_classes - 1
        ):
            return 'blocked'

    return 'clear'


def find_schedule_conflict(trainer, class_time, class_days, exclude_enrollment_id=None, date_range=None):
    """The first ongoing enrollment that would clash with `trainer` teaching
    at `class_time` on any of `class_days` — same exact time, at least one
    overlapping day. Checks both the trainer's own permanently-assigned
    enrollments and anything they're currently covering as a substitute.
    Used to hard-block both a permanent Transfer and a new
    SubstituteAssignment from double-booking a trainer. Returns None if
    there's no conflict.

    `date_range` (start, end), when given, additionally scopes the substitute
    side of the check to assignments that overlap that range — irrelevant for
    a permanent Transfer (always "active"), relevant for a new
    SubstituteAssignment (only actually clashes if the date ranges overlap).
    """
    if not class_time or not class_days:
        return None
    days = set(class_days.split(','))

    own = Enrollment.objects.filter(trainer=trainer, status='ongoing', class_time=class_time)
    if exclude_enrollment_id:
        own = own.exclude(id=exclude_enrollment_id)
    for enrollment in own:
        if days & set((enrollment.class_days or '').split(',')):
            return enrollment

    covering = SubstituteAssignment.objects.filter(
        substitute_trainer=trainer, enrollment__class_time=class_time
    ).select_related('enrollment')
    if exclude_enrollment_id:
        covering = covering.exclude(enrollment_id=exclude_enrollment_id)
    if date_range:
        start, end = date_range
        covering = covering.filter(start_date__lte=end, end_date__gte=start)
    for assignment in covering:
        if days & set((assignment.enrollment.class_days or '').split(',')):
            return assignment.enrollment

    return None
