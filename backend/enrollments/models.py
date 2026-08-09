from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from courses.models import Course
from students.models import Student
from trainers.models import Trainer

DAYS_OF_WEEK = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN']


class Enrollment(models.Model):
    STATUS_CHOICES = [
        ('ongoing', 'Ongoing'),
        ('completed', 'Completed'),
        ('withdrawn', 'Withdrawn'),
    ]

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='enrollments')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='enrollments')
    trainer = models.ForeignKey(Trainer, on_delete=models.CASCADE, related_name='enrollments')
    batch_number = models.IntegerField(default=1)
    classes_completed = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    classes_total = models.IntegerField(default=24, validators=[MinValueValidator(1)])
    start_date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='ongoing')
    class_time = models.TimeField(null=True, blank=True)
    class_days = models.CharField(max_length=50, blank=True, default='', help_text='Comma-separated day codes, e.g. MON,WED,FRI')
    # Snapshots of the trainer's/client's per-class rate at enrollment time, for display
    # on the enrollment record only. Payout and billing math never reads these — they
    # always use billing.RateHistory (effective-dated) or the trainer's/client's live
    # rate — since a single enrollment can span rate changes over its lifetime. See
    # attendance/views.py, clients/services.py and billing/services.py.
    trainer_rate_per_class = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)],
    )
    client_rate_per_class = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)],
    )

    class Meta:
        # find_schedule_conflict() filters on exactly this combination (trainer,
        # status='ongoing', class_time) on every transfer/substitute-assignment
        # request — see the performance audit.
        indexes = [models.Index(fields=['trainer', 'status', 'class_time'])]

    def __str__(self):
        return f'{self.student.name} — {self.course.name} (batch {self.batch_number})'

    def sync_completion_status(self):
        """Flip status between 'ongoing' and 'completed' to match classes_completed vs
        classes_total. Never touches a withdrawn enrollment — withdrawal is terminal.

        Shared by both sides of that comparison changing: classes_completed (see
        attendance/views.py's perform_create/perform_destroy and
        AttendanceRequestViewSet.approve) and classes_total (see
        enrollments/services.py's sync_enrollment_status_after_classes_total_change —
        e.g. extending an already-completed enrollment's batch count reopens it so the
        trainer can mark the newly added classes).

        Returns the enrollment's previous status if it changed, else None.
        """
        if self.status == 'withdrawn':
            return None
        if self.classes_completed >= self.classes_total and self.status != 'completed':
            old_status = self.status
            self.status = 'completed'
            self.save(update_fields=['status'])
            return old_status
        if self.classes_completed < self.classes_total and self.status == 'completed':
            old_status = self.status
            self.status = 'ongoing'
            self.save(update_fields=['status'])
            return old_status
        return None


class SubstituteAssignment(models.Model):
    """Temporary coverage: a different trainer teaches this enrollment's
    classes for a specific date range, then it automatically reverts — unlike
    `EnrollmentViewSet.transfer` (a permanent reassignment), this never
    touches Enrollment.trainer at all. Attendance marked during the window is
    just recorded with marked_by=substitute_trainer as normal (see
    AttendanceSerializer.validate()), so trainer pay follows naturally —
    payout totals are already grouped by who actually marked a class, not by
    who the enrollment is assigned to.

    "Active" is derived from today's date falling in [start_date, end_date] —
    there's nothing to do to end coverage on schedule; deleting the row ends
    it early if the original trainer comes back sooner than planned.
    """

    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name='substitute_assignments')
    substitute_trainer = models.ForeignKey(Trainer, on_delete=models.CASCADE, related_name='substitute_assignments')
    start_date = models.DateField()
    end_date = models.DateField()
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-start_date']
        # MyStudentsView and find_schedule_conflict() both check "is there an
        # active/overlapping substitute assignment for this trainer" — see the
        # performance audit.
        indexes = [models.Index(fields=['substitute_trainer', 'start_date', 'end_date'])]

    def __str__(self):
        return f'{self.substitute_trainer.name} covering {self.enrollment} ({self.start_date}..{self.end_date})'


# due_at_classes milestones for each plan's installments after the first payment (which
# is always due immediately, before class 1 — represented by `None`).
PLAN_SCHEDULES = {
    'two_installments': [None, 10],
    'three_installments': [None, 6, 18],
    'four_installments': [None, 6, 11, 18],
}


class PaymentPlan(models.Model):
    """A B2C student's course-fee payment plan for one enrollment. Chosen at enrollment
    time — see PLAN_SCHEDULES for each plan's installment milestones. Not used for B2B
    students, who are billed per class through the Client/ClientInvoice system instead.
    """

    PLAN_CHOICES = [
        ('two_installments', 'Two installments (10th class)'),
        ('three_installments', 'Three installments (6th, 18th class)'),
        ('four_installments', 'Four installments (6th, 11th, 18th class)'),
    ]

    enrollment = models.OneToOneField(Enrollment, on_delete=models.CASCADE, related_name='payment_plan')
    plan_type = models.CharField(max_length=20, choices=PLAN_CHOICES)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    # The discount percent (0-15, see EnrollmentSerializer.discount_percent) applied when
    # total_amount was last computed — persisted so a later classes_total edit can reprice
    # with total_amount_for_discount() using the exact same discount, rather than guessing
    # it back from the stored total_amount. See services.recalculate_payment_plan().
    discount_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('0.00'), validators=[MinValueValidator(0)],
    )
    # Set when the enrollment is withdrawn with a refund — see EnrollmentViewSet.withdraw().
    refunded_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    refund_note = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.enrollment} — {self.get_plan_type_display()} — ₹{self.total_amount}'


class PaymentInstallment(models.Model):
    PAID_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        # Set when the enrollment is withdrawn — see EnrollmentViewSet.withdraw().
        # A cancelled installment was never paid and never will be; it's kept
        # (not deleted) so the payment plan's history stays intact.
        ('cancelled', 'Cancelled'),
    ]

    plan = models.ForeignKey(PaymentPlan, on_delete=models.CASCADE, related_name='installments')
    sequence = models.IntegerField()
    # None = due before class 1 (the first payment). Otherwise the class number this
    # installment is due before — informational only; parents may pay earlier.
    due_at_classes = models.IntegerField(null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    paid_status = models.CharField(max_length=10, choices=PAID_STATUS_CHOICES, default='pending')
    paid_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['sequence']
        # compute_admin_alerts() filters PaymentInstallment.objects.filter(paid_status=
        # 'pending') with no other predicate — an unscoped whole-table filter otherwise.
        indexes = [models.Index(fields=['paid_status'])]

    def __str__(self):
        return f'{self.plan.enrollment} — installment {self.sequence} — ₹{self.amount}'
