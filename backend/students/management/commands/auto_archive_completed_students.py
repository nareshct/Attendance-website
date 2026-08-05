from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Max
from django.utils import timezone

from attendance.models import Attendance
from students.models import Student


class Command(BaseCommand):
    help = (
        "Archives active students whose enrollments are all finished (at least one "
        "completed, none still ongoing) once 30+ days have passed since the last class "
        "on any of their completed enrollments. A student with one course still ongoing "
        "is left alone even if another course of theirs already finished. Nothing in "
        "this project runs on a schedule by itself; point your OS scheduler (Windows "
        "Task Scheduler / cron) at this command to run it daily. Safe to run repeatedly "
        "— already-archived students are simply skipped next time."
    )

    GRACE_DAYS = 30

    def handle(self, *args, **options):
        cutoff = timezone.now().date() - timedelta(days=self.GRACE_DAYS)

        candidates = (
            Student.objects.filter(status='active')
            .exclude(enrollments__status='ongoing')
            .filter(enrollments__status='completed')
            .distinct()
        )

        archived = []
        for student in candidates:
            last_class = Attendance.objects.filter(
                enrollment__student=student, enrollment__status='completed', status='present',
            ).aggregate(last=Max('date'))['last']
            if last_class is None or last_class > cutoff:
                continue
            student.status = 'archived'
            student.save(update_fields=['status'])
            archived.append(student)

        if archived:
            self.stdout.write(f'Archived {len(archived)} student(s): ' + ', '.join(s.name for s in archived))
        else:
            self.stdout.write('No students to archive.')
