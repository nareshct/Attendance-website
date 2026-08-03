from datetime import date

from django.core.management.base import BaseCommand

from billing.services import get_or_create_cycle


class Command(BaseCommand):
    help = 'Ensure a BillingCycle exists for the given date (defaults to today).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--date', type=str, default=None,
            help='YYYY-MM-DD date to generate the cycle for. Defaults to today.',
        )

    def handle(self, *args, **options):
        for_date = date.fromisoformat(options['date']) if options['date'] else date.today()
        cycle, created = get_or_create_cycle(for_date)
        verb = 'Created' if created else 'Already exists'
        self.stdout.write(self.style.SUCCESS(
            f'{verb}: cycle {cycle.cycle_start} to {cycle.cycle_end} (status={cycle.status})'
        ))
