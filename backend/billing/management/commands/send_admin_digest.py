from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.core.management.base import BaseCommand

from billing.services import compute_admin_alerts


class Command(BaseCommand):
    help = (
        'Email admins a summary of overdue B2B invoices and due-but-unpaid B2C '
        'installments — the same data the dashboard "Needs attention" cards show. '
        'Nothing in this project runs on a schedule by itself; point your OS scheduler '
        '(Windows Task Scheduler / cron) at this command to run it daily. Sends nothing '
        'when there is nothing overdue or due, so it is safe to schedule every day.'
    )

    def handle(self, *args, **options):
        alerts = compute_admin_alerts()
        overdue_invoices = alerts['overdue_invoices']
        due_installments = alerts['due_installments']

        if not overdue_invoices and not due_installments:
            self.stdout.write('Nothing overdue or due - no digest sent.')
            return

        User = get_user_model()
        recipients = list(
            User.objects.filter(is_staff=True).exclude(email='').values_list('email', flat=True)
        )
        if not recipients:
            self.stderr.write(
                'No admin account has an email address on file, so this digest has nowhere '
                'to go. Set one via Change Password / account settings. Skipping send.'
            )
            return

        lines = []
        if overdue_invoices:
            lines.append(f'Overdue client invoices ({len(overdue_invoices)}):')
            for inv in overdue_invoices:
                day_word = 'day' if inv['days_overdue'] == 1 else 'days'
                lines.append(
                    f"  - {inv['client_name']}: Rs.{inv['amount']}, {inv['days_overdue']} {day_word} overdue "
                    f"(cycle {inv['cycle_start']} to {inv['cycle_end']})"
                )
            lines.append('')

        if due_installments:
            lines.append(f'Due B2C installments ({len(due_installments)}):')
            for inst in due_installments:
                due_label = 'before class 1' if inst['due_at_classes'] is None else f"before class {inst['due_at_classes']}"
                lines.append(
                    f"  - {inst['student_name']} - {inst['course_name']}, installment #{inst['sequence']} "
                    f"({due_label}): Rs.{inst['amount']} - {inst['classes_completed']} classes done so far"
                )
            lines.append('')

        lines.append(f'Open the admin dashboard at {settings.FRONTEND_URL} to review and record payments.')
        message = '\n'.join(lines)

        send_mail(
            subject=f'Apex Binary: {len(overdue_invoices)} overdue, {len(due_installments)} due for payment',
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
        )
        self.stdout.write(self.style.SUCCESS(
            f'Sent digest to {len(recipients)} admin(s): {len(overdue_invoices)} overdue invoice(s), '
            f'{len(due_installments)} due installment(s).'
        ))
