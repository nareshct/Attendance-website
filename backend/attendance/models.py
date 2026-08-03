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
        # A class only happens once — the same enrollment can't have two attendance
        # rows for the same date (would double-count classes_completed and pay).
        constraints = [
            models.UniqueConstraint(fields=['enrollment', 'date'], name='unique_attendance_per_enrollment_date')
        ]

    def __str__(self):
        return f'{self.enrollment} — {self.date} ({self.status})'


class AttendanceRequest(models.Model):
    """A trainer's request to mark attendance for a date that falls in a
    closed billing cycle — requires admin approval before it becomes a real
    Attendance record."""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('denied', 'Denied'),
    ]

    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name='attendance_requests')
    date = models.DateField()
    topic_covered = models.TextField(blank=True)
    requested_by = models.ForeignKey(Trainer, on_delete=models.CASCADE, related_name='attendance_requests')
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
