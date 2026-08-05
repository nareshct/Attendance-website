from decimal import Decimal

from django.conf import settings
from django.db import models

from courses.models import Course
from students.models import Student

PAYMENT_TYPE_CHOICES = [
    ('one_time', 'One-time payment'),
    ('two_installments', 'Two installments'),
    ('three_installments', 'Three installments'),
    ('four_installments', 'Four installments'),
]

# Fraction of the batch's total sessions at which each installment becomes due — the
# first is always due immediately at signup (None). Batches don't track per-student
# attendance (see Batch's docstring), so "due" is measured against the batch's own
# session count (see BatchSession) rather than an individual student's classes
# completed. Amounts are split evenly across the plan — unlike the individual B2C
# course plans, a batch has one flat fee rather than a per-class rate to derive an
# uneven upfront amount from. See batches/services.py.
PAYMENT_MILESTONES = {
    'one_time': [None],
    'two_installments': [None, Decimal('0.5')],
    'three_installments': [None, Decimal('0.34'), Decimal('0.67')],
    'four_installments': [None, Decimal('0.25'), Decimal('0.5'), Decimal('0.75')],
}


class Batch(models.Model):
    """A group class run over Google Meet — priced as one flat fee per
    enrolled student (not per attended class like an individual Enrollment),
    with no single mandatory trainer.

    `trainer_names` is an unlimited, free-text list of who's associated with
    running the batch — for split schedules (e.g. one person on Mon/Wed,
    another on Fri) or co-teaching. Deliberately NOT restricted to the
    registered Trainer table: any name works, since "any buddy" can help run
    a batch, same free-text convention as BatchSession.conducted_by_name
    (which logs who actually ran a specific session — independent of this
    list).

    Payouts for running the batch are tracked per person — see BatchPayout
    below — the same "any number, any name" approach as trainer_names, since
    a batch can be co-taught or split across several people who each need
    their own agreed amount recorded.

    Deliberately has nothing to do with BillingCycle/Payout/ClientInvoice —
    this is a separate revenue stream with its own accounting, see
    batches/services.py.
    """

    STATUS_CHOICES = [
        ('ongoing', 'Ongoing'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    name = models.CharField(max_length=255, help_text='e.g. "Scratch Programming — July 2026 batch"')
    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name='batches')
    # Comma-separated free-text names — mirrors the class_days field's convention
    # (a simple delimited list, split/joined by the frontend), not a relation to any
    # other table, since these don't have to be registered trainers.
    trainer_names = models.CharField(max_length=1000, blank=True, default='')
    description = models.TextField(blank=True, default='')
    total_classes = models.IntegerField()
    fee_per_student = models.DecimalField(max_digits=10, decimal_places=2)
    payment_type = models.CharField(max_length=20, choices=PAYMENT_TYPE_CHOICES, default='one_time')
    start_date = models.DateField()
    class_time = models.TimeField(null=True, blank=True)
    class_days = models.CharField(max_length=50, blank=True, default='', help_text='Comma-separated day codes, e.g. MON,WED,FRI')
    meet_link = models.URLField(blank=True, default='')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='ongoing')
    # Independent of `status` — a batch can stay "ongoing" (classes still running) while
    # no longer accepting new sign-ups, e.g. once it's too far in to be worth a late
    # joiner catching up. Blocks new enrollments both via "Add student" and Excel import.
    accepting_enrollments = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-start_date']

    def __str__(self):
        return self.name


class BatchEnrollment(models.Model):
    """One student's membership (and payment plan) in a Batch.

    `student` is optional — a batch can also include someone who's never been
    registered as a Student in the system at all (e.g. a walk-in who signs up
    straight into a batch). When `student` is None, the guest_* fields below
    hold their details instead, doubling as a lightweight lead capture
    (guest_source records how they heard about us) since this is often how a
    center picks up brand-new prospects.
    """

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('withdrawn', 'Withdrawn'),
    ]

    batch = models.ForeignKey(Batch, on_delete=models.CASCADE, related_name='batch_enrollments')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='batch_enrollments', null=True, blank=True)
    guest_name = models.CharField(max_length=255, blank=True, default='')
    guest_phone_number = models.CharField(max_length=20, blank=True, default='')
    guest_email = models.EmailField(blank=True, default='')
    guest_occupation = models.CharField(max_length=255, blank=True, default='')
    guest_source = models.CharField(max_length=255, blank=True, default='', help_text='How they heard about us, e.g. referral, social media, walk-in')
    joined_date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    # Set on withdraw when money already collected needs to be handed back — subtracted
    # from batch_revenue_summary's `collected` figure so a refunded installment doesn't
    # keep counting as real revenue forever. Mirrors PaymentPlan.refund_note/refunded_amount
    # on the individual B2C course flow.
    refunded_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    refund_note = models.TextField(blank=True, default='')

    class Meta:
        unique_together = ('batch', 'student')
        ordering = ['-joined_date']

    @property
    def display_name(self):
        return self.student.name if self.student_id else self.guest_name

    def __str__(self):
        return f'{self.display_name} — {self.batch.name}'


class BatchInstallment(models.Model):
    PAID_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
    ]

    batch_enrollment = models.ForeignKey(BatchEnrollment, on_delete=models.CASCADE, related_name='installments')
    sequence = models.IntegerField()
    # None = due immediately at signup. Otherwise a resolved session-count milestone
    # (see PAYMENT_MILESTONES) — informational only, parents may pay earlier.
    due_at_sessions = models.IntegerField(null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    paid_status = models.CharField(max_length=10, choices=PAID_STATUS_CHOICES, default='pending')
    paid_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['sequence']

    def __str__(self):
        return f'{self.batch_enrollment} — installment {self.sequence} — ₹{self.amount}'


class BatchSession(models.Model):
    """One class actually held for a Batch. No per-student attendance is
    recorded here on purpose — sessions are conducted over Google Meet,
    recorded, and the recording link is shared with the student group
    directly, so this is just a log of when it happened, who ran it, and
    where the recording is.
    """

    batch = models.ForeignKey(Batch, on_delete=models.CASCADE, related_name='sessions')
    date = models.DateField()
    conducted_by_name = models.CharField(max_length=255, help_text='Trainer or anyone else who took this session')
    topic_covered = models.TextField(blank=True, default='')
    recording_link = models.URLField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    # Who actually submitted this log entry via the API — distinct from
    # conducted_by_name, which is free text describing who *ran* the class (may name
    # someone else, e.g. a substitute). Used only to scope edit/delete to the trainer
    # who logged it (see BatchSessionViewSet); null for rows created before this field
    # existed, or if the submitting user is later deleted — those stay editable by any
    # co-trainer on the batch rather than becoming permanently locked.
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f'{self.batch.name} — {self.date}'


class BatchPayout(models.Model):
    """One agreed payment for one person who helped run a Batch — recipient
    name is free text, same "any buddy" convention as trainer_names /
    BatchSession.conducted_by_name, not tied to the registered Trainer table.
    A batch can have any number of these (e.g. one per co-teaching trainer),
    unlike an individual Enrollment's single per-class trainer rate.
    """

    batch = models.ForeignKey(Batch, on_delete=models.CASCADE, related_name='payouts')
    recipient_name = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    paid = models.BooleanField(default=False)
    paid_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f'{self.recipient_name} — {self.batch.name} — ₹{self.amount}'
