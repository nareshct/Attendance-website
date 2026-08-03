from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import IntegrityError, models, transaction
from django.utils import timezone

from courses.models import Course


class Trainer(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('archived', 'Archived'),
    ]

    trainer_id = models.CharField(max_length=20, unique=True, blank=True)
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='trainer')
    name = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=20)
    place = models.CharField(max_length=255)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    default_rate_per_class = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)],
        help_text='Applies to every course unless overridden by a TrainerCourseRate for that course.',
    )

    def save(self, *args, **kwargs):
        if self.pk:
            from billing.services import log_rate_change
            old_rate = Trainer.objects.filter(pk=self.pk).values_list('default_rate_per_class', flat=True).first()
            log_rate_change(self, None, old_rate, self.default_rate_per_class)

        if self.trainer_id:
            super().save(*args, **kwargs)
            return

        # Retry on a unique-constraint collision — two near-simultaneous creates can
        # both compute the same next_seq from the same "last" row before either commits.
        year = timezone.now().year
        prefix = f'TRN-{year}-'
        for attempt in range(5):
            last = (
                Trainer.objects.filter(trainer_id__startswith=prefix)
                .order_by('-trainer_id')
                .first()
            )
            next_seq = int(last.trainer_id.rsplit('-', 1)[1]) + 1 if last else 1
            self.trainer_id = f'{prefix}{next_seq:03d}'
            try:
                with transaction.atomic():
                    super().save(*args, **kwargs)
                return
            except IntegrityError:
                if attempt == 4:
                    raise

    def __str__(self):
        return f'{self.trainer_id} — {self.name}'

    def rate_for(self, course):
        """The effective rate for a course: an explicit override if one exists, else the default."""
        override = self.course_rates.filter(course=course).first()
        if override:
            return override.rate_per_class
        return self.default_rate_per_class

    def has_rate_for(self, course):
        return self.rate_for(course) is not None


class TrainerCourseRate(models.Model):
    trainer = models.ForeignKey(Trainer, on_delete=models.CASCADE, related_name='course_rates')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='trainer_rates')
    rate_per_class = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(0)])

    class Meta:
        unique_together = ('trainer', 'course')

    def save(self, *args, **kwargs):
        if self.pk:
            from billing.services import log_rate_change
            old_rate = TrainerCourseRate.objects.filter(pk=self.pk).values_list('rate_per_class', flat=True).first()
            log_rate_change(self.trainer, self.course, old_rate, self.rate_per_class)
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.trainer.name} / {self.course.name} — ₹{self.rate_per_class}'
