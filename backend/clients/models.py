from django.core.validators import MinValueValidator
from django.db import models

from courses.models import Course


class Client(models.Model):
    """A B2B company that refers students to us."""

    STATUS_CHOICES = [
        ('active', 'Active'),
        ('archived', 'Archived'),
    ]

    company_name = models.CharField(max_length=255)
    contact_phone = models.CharField(max_length=20)
    contact_email = models.EmailField(blank=True)
    rate_per_class = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)],
        help_text='Amount this client pays us per class attended by their students.',
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')

    def save(self, *args, **kwargs):
        if self.pk:
            from billing.services import log_rate_change
            old_rate = Client.objects.filter(pk=self.pk).values_list('rate_per_class', flat=True).first()
            log_rate_change(self, None, old_rate, self.rate_per_class)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.company_name

    def rate_for(self, course):
        """The effective rate for a course: an explicit override if one exists, else the flat rate."""
        override = self.course_rates.filter(course=course).first()
        if override:
            return override.rate_per_class
        return self.rate_per_class


class ClientContact(models.Model):
    """An additional contact person at a B2B client, beyond the client's primary phone/email."""

    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='contacts')
    name = models.CharField(max_length=255)
    role = models.CharField(max_length=100, blank=True, help_text='e.g. Billing, Operations, Principal.')
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)

    def __str__(self):
        return f'{self.name} ({self.client.company_name})'


class ClientCourseRate(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='course_rates')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='client_rates')
    rate_per_class = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(0)])

    class Meta:
        unique_together = ('client', 'course')

    def save(self, *args, **kwargs):
        if self.pk:
            from billing.services import log_rate_change
            old_rate = ClientCourseRate.objects.filter(pk=self.pk).values_list('rate_per_class', flat=True).first()
            log_rate_change(self.client, self.course, old_rate, self.rate_per_class)
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.client.company_name} / {self.course.name} — ₹{self.rate_per_class}'
