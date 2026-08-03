import uuid

from django.db import IntegrityError, models, transaction
from django.utils import timezone

from clients.models import Client


class Student(models.Model):
    SOURCE_CHOICES = [
        ('B2B', 'B2B'),
        ('B2C', 'B2C'),
    ]
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('archived', 'Archived'),
    ]

    student_id = models.CharField(max_length=20, unique=True, blank=True)
    name = models.CharField(max_length=255)
    grade = models.CharField(max_length=20)
    parent_name = models.CharField(max_length=255, blank=True, default='')
    place = models.CharField(max_length=255, blank=True, default='')
    parent_phone_number = models.CharField(max_length=20, blank=True, default='')
    source_type = models.CharField(max_length=3, choices=SOURCE_CHOICES)
    client = models.ForeignKey(Client, on_delete=models.SET_NULL, null=True, blank=True, related_name='students')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.student_id:
            super().save(*args, **kwargs)
            return

        # Retry on a unique-constraint collision — two near-simultaneous creates can
        # both compute the same next_seq from the same "last" row before either commits.
        year = timezone.now().year
        prefix = f'STU-{year}-'
        for attempt in range(5):
            last = (
                Student.objects.filter(student_id__startswith=prefix)
                .order_by('-student_id')
                .first()
            )
            next_seq = int(last.student_id.rsplit('-', 1)[1]) + 1 if last else 1
            self.student_id = f'{prefix}{next_seq:03d}'
            try:
                with transaction.atomic():
                    super().save(*args, **kwargs)
                return
            except IntegrityError:
                if attempt == 4:
                    raise

    def __str__(self):
        return f'{self.student_id} — {self.name}'


class ParentShareLink(models.Model):
    """A private, unauthenticated read-only link an admin can send a parent —
    the token itself is the only access control, no login involved. One per
    student; `regenerate` on the view swaps the token (invalidating any link
    already sent out), and `revoked` turns it off without losing the row.
    """

    student = models.OneToOneField(Student, on_delete=models.CASCADE, related_name='parent_share_link')
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    revoked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Parent link for {self.student.name}'
