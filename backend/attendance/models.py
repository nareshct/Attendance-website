from django.db import models

from enrollments.models import Enrollment
from trainers.models import Trainer


class Attendance(models.Model):
    STATUS_CHOICES = [
        ('present', 'Present'),
        ('absent', 'Absent'),
    ]

    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name='attendance_records')
    date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    topic_covered = models.TextField(blank=True)
    marked_by = models.ForeignKey(Trainer, on_delete=models.PROTECT, related_name='marked_attendance')

    class Meta:
        ordering = ['-date']
        # A class only happens once per enrollment+date *by default* — but a trainer can
        # genuinely teach a student twice in one day, so this is capped at 2 (not 1) and
        # enforced in application code (AttendanceViewSet.create()/AttendanceRequestViewSet.
        # approve()) rather than a DB constraint, since the 2nd row always requires admin
        # approval first. See AttendanceRequest.request_type == 'duplicate_day'.
        # status='present' + a date range is the dominant filter shape across the
        # billing services (trainer_totals_for_range, b2c_totals_for_range,
        # calculate_payouts_for_cycle, calculate_client_invoices_for_cycle,
        # client_totals) and the CSV report views — see the performance audit.
        indexes = [models.Index(fields=['status', 'date']), models.Index(fields=['enrollment', 'date'])]

    def __str__(self):
        return f'{self.enrollment} — {self.date} ({self.status})'


class AttendanceRequest(models.Model):
    """A trainer's request to mark attendance for a date that either falls in
    a closed billing cycle, or already has one class recorded for the same
    student that day — either way it requires admin approval before it
    becomes a real Attendance record."""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('denied', 'Denied'),
    ]
    REQUEST_TYPE_CHOICES = [
        ('late_entry', 'Late entry (closed billing cycle)'),
        ('duplicate_day', 'Second class same day'),
    ]

    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name='attendance_requests')
    date = models.DateField()
    topic_covered = models.TextField(blank=True)
    requested_by = models.ForeignKey(Trainer, on_delete=models.CASCADE, related_name='attendance_requests')
    request_type = models.CharField(max_length=20, choices=REQUEST_TYPE_CHOICES, default='late_entry')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    attendance = models.OneToOneField(
        Attendance, on_delete=models.SET_NULL, null=True, blank=True, related_name='approval_request'
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.enrollment} — {self.date} ({self.status})'
