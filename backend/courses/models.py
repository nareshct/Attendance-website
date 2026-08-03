from django.core.validators import FileExtensionValidator, MinValueValidator
from django.db import models


class Course(models.Model):
    name = models.CharField(max_length=255)
    total_classes = models.IntegerField(default=24, validators=[MinValueValidator(1)])
    rate_per_class = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)],
        help_text='Standard per-class price for B2C students. Used to default the total course fee on a B2C enrollment.',
    )

    def save(self, *args, **kwargs):
        if self.pk:
            from billing.services import log_rate_change
            old_rate = Course.objects.filter(pk=self.pk).values_list('rate_per_class', flat=True).first()
            log_rate_change(self, None, old_rate, self.rate_per_class)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class CourseMaterial(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='materials')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    file = models.FileField(
        upload_to='course_materials/%Y/%m/',
        validators=[FileExtensionValidator(allowed_extensions=['pdf'])],
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f'{self.course.name} — {self.title}'
