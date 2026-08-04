from datetime import date, timedelta

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from attendance.models import Attendance
from clients.models import Client
from courses.models import Course
from trainers.models import Trainer


class BillingCycle(models.Model):
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('closed', 'Closed'),
        ('paid', 'Paid'),
    ]

    cycle_start = models.DateField()
    cycle_end = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='open')

    class Meta:
        ordering = ['-cycle_start']
        # get_or_create_cycle() relies on this to be race-safe under concurrent
        # requests — without it, two simultaneous calls can both pass the SELECT
        # check and insert duplicate rows for the same period.
        unique_together = ('cycle_start', 'cycle_end')

    def __str__(self):
        return f'{self.cycle_start} → {self.cycle_end} ({self.status})'


class Payout(models.Model):
    PAID_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('paid', 'Paid'),
    ]

    trainer = models.ForeignKey(Trainer, on_delete=models.CASCADE, related_name='payouts')
    cycle = models.ForeignKey(BillingCycle, on_delete=models.CASCADE, related_name='payouts')
    total_classes = models.IntegerField(default=0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    paid_status = models.CharField(max_length=10, choices=PAID_STATUS_CHOICES, default='pending')

    class Meta:
        unique_together = ('trainer', 'cycle')

    def __str__(self):
        return f'{self.trainer.name} — {self.cycle} — ₹{self.total_amount}'


class PayoutAdjustment(models.Model):
    """A class taught after its billing cycle's Payout was already generated for
    the trainer (closing a cycle is what creates that payout).

    Never edited in after the fact — paid or not, a payout for a closed cycle is
    left alone. Instead the amount is assigned straight to the trainer's current,
    still-open cycle at creation time, so it shows up live and gets folded into
    that cycle's own Payout once it closes (see calculate_payouts_for_cycle).
    """

    trainer = models.ForeignKey(Trainer, on_delete=models.CASCADE, related_name='payout_adjustments')
    attendance = models.OneToOneField(Attendance, on_delete=models.CASCADE, related_name='payout_adjustment')
    source_cycle = models.ForeignKey(BillingCycle, on_delete=models.CASCADE, related_name='+')
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    applied_cycle = models.ForeignKey(BillingCycle, on_delete=models.CASCADE, related_name='applied_adjustments')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.trainer.name} — ₹{self.amount} from {self.source_cycle}'


class ClientInvoiceAdjustment(models.Model):
    """A class taught after its billing cycle's invoice was already generated for
    the client (closing a cycle is what creates and sends the ClientInvoice).

    Unlike PayoutAdjustment, this is never left "pending" — a client's invoice
    for a closed cycle has already gone out to them (whether or not they've
    paid it), so editing it after the fact would be confusing. Instead the
    amount is assigned straight to the client's current, still-open cycle at
    creation time, so it shows up live and gets folded into that cycle's own
    ClientInvoice once it closes (see calculate_client_invoices_for_cycle).
    """

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='invoice_adjustments')
    attendance = models.OneToOneField(Attendance, on_delete=models.CASCADE, related_name='invoice_adjustment')
    source_cycle = models.ForeignKey(BillingCycle, on_delete=models.CASCADE, related_name='+')
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    # The trainer's cost for this same class, captured alongside the client's billed
    # amount so margin (our_earning) calculations can subtract it — without this,
    # a diverted class's full client revenue would be counted as pure profit.
    trainer_cost = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    applied_cycle = models.ForeignKey(BillingCycle, on_delete=models.CASCADE, related_name='applied_invoice_adjustments')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.client.company_name} — ₹{self.amount} from {self.source_cycle}'


class B2CRevenueAdjustment(models.Model):
    """A B2C class taught after its billing cycle's revenue was already frozen
    into a CycleRevenueSnapshot (closing a cycle is what creates that
    snapshot). Mirrors ClientInvoiceAdjustment, just without a client — B2C
    revenue isn't billed per-client, so there's nothing to attach this to but
    the class itself.

    Same as ClientInvoiceAdjustment, this is never left "pending" — the
    snapshot for a closed cycle has already been frozen (paid out or not), so
    editing it after the fact would be confusing. Instead the amount is
    assigned straight to the current, still-open cycle at creation time, so it
    shows up live and gets folded into that cycle's own snapshot once it
    closes (see snapshot_cycle_revenue / b2c_current_cycle_totals).
    """

    attendance = models.OneToOneField(Attendance, on_delete=models.CASCADE, related_name='b2c_revenue_adjustment')
    source_cycle = models.ForeignKey(BillingCycle, on_delete=models.CASCADE, related_name='+')
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    # See ClientInvoiceAdjustment.trainer_cost — same reasoning, for the B2C profit split.
    trainer_cost = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    applied_cycle = models.ForeignKey(BillingCycle, on_delete=models.CASCADE, related_name='applied_b2c_adjustments')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'B2C class #{self.attendance_id} — ₹{self.amount} from {self.source_cycle}'


class ClientInvoice(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('received', 'Received'),
    ]

    # Grace period after a cycle closes before an unpaid invoice counts as overdue.
    OVERDUE_GRACE_DAYS = 3

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='invoices')
    cycle = models.ForeignKey(BillingCycle, on_delete=models.CASCADE, related_name='client_invoices')
    total_classes = models.IntegerField(default=0)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')

    class Meta:
        unique_together = ('client', 'cycle')
        # compute_admin_alerts() and ClientViewSet.summary/earnings all filter on
        # status='pending' paired with the cycle's own status — see the performance audit.
        indexes = [models.Index(fields=['status', 'cycle'])]

    def __str__(self):
        return f'{self.client.company_name} — {self.cycle} — ₹{self.total_amount}'

    @property
    def due_date(self):
        return self.cycle.cycle_end + timedelta(days=self.OVERDUE_GRACE_DAYS)

    @property
    def is_overdue(self):
        return self.status == 'pending' and date.today() > self.due_date

    @property
    def days_overdue(self):
        return (date.today() - self.due_date).days if self.is_overdue else 0


class RateHistory(models.Model):
    """Effective-dated history of a rate_per_class value, for a Client (flat
    rate + per-course override), a Trainer (flat default + per-course
    override), or a Course itself (its flat B2C price).

    Editing a rate normally just overwrites the live field on its own model —
    there's no other trace of what it used to be. This table exists solely so
    a late attendance approval (see AttendanceRequestViewSet.approve() /
    billing.services.historical_rate()) can bill at the rate that was actually
    in effect on the class's real date, instead of whatever the rate happens to
    be today. Logged automatically whenever a rate field changes — see
    billing.services.log_rate_change(), called from each owning model's save().
    """

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    entity = GenericForeignKey('content_type', 'object_id')
    # Set for a per-course override (ClientCourseRate/TrainerCourseRate row);
    # null for a flat rate (Client.rate_per_class, Trainer.default_rate_per_class,
    # or a Course's own rate_per_class).
    course = models.ForeignKey(Course, on_delete=models.CASCADE, null=True, blank=True, related_name='+')
    rate_per_class = models.DecimalField(max_digits=8, decimal_places=2)
    effective_from = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-effective_from', '-created_at']
        indexes = [models.Index(fields=['content_type', 'object_id', 'course', 'effective_from'])]

    def __str__(self):
        return f'{self.entity} / {self.course or "flat"} — ₹{self.rate_per_class} from {self.effective_from}'


class CycleRevenueSnapshot(models.Model):
    """B2B/B2C revenue-and-trainer-cost split for a BillingCycle, frozen the
    moment the cycle closes (see services.snapshot_cycle_revenue(), called from
    BillingCycleViewSet.close()).

    Payout and ClientInvoice are already frozen at close time for the same
    reason: without this, a trainer/course rate change made after a cycle has
    already been invoiced and paid out would silently rewrite that cycle's
    historical profit figures on the dashboard's revenue card. Profit isn't
    stored directly — it's always revenue minus trainer_cost, computed on read.
    """

    cycle = models.OneToOneField(BillingCycle, on_delete=models.CASCADE, related_name='revenue_snapshot')
    b2b_classes = models.IntegerField(default=0)
    b2b_revenue = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    b2b_trainer_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    b2c_classes = models.IntegerField(default=0)
    b2c_revenue = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    b2c_trainer_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.cycle} revenue snapshot'
