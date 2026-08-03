from django.core.management.base import BaseCommand, CommandError

from billing.models import BillingCycle
from billing.services import calculate_client_invoices_for_cycle, calculate_payouts_for_cycle


class Command(BaseCommand):
    help = 'Calculate payouts and client invoices for a billing cycle and mark it closed.'

    def add_arguments(self, parser):
        parser.add_argument('cycle_id', type=int, nargs='?', default=None,
                             help='BillingCycle id. Defaults to the oldest open cycle.')

    def handle(self, *args, **options):
        cycle_id = options['cycle_id']
        if cycle_id is not None:
            try:
                cycle = BillingCycle.objects.get(id=cycle_id)
            except BillingCycle.DoesNotExist:
                raise CommandError(f'No BillingCycle with id={cycle_id}')
        else:
            cycle = BillingCycle.objects.filter(status='open').order_by('cycle_start').first()
            if cycle is None:
                raise CommandError('No open billing cycles found.')

        if cycle.status != 'open':
            raise CommandError(f'Cycle {cycle.id} is already {cycle.status}.')

        payouts = calculate_payouts_for_cycle(cycle)
        invoices = calculate_client_invoices_for_cycle(cycle)
        cycle.status = 'closed'
        cycle.save(update_fields=['status'])

        self.stdout.write(self.style.SUCCESS(
            f'Closed cycle {cycle.cycle_start} to {cycle.cycle_end}: '
            f'{len(payouts)} payout(s) and {len(invoices)} client invoice(s) generated.'
        ))
        for p in payouts:
            self.stdout.write(f'  {p.trainer.name}: {p.total_classes} classes -> Rs.{p.total_amount}')
        for inv in invoices:
            self.stdout.write(f'  {inv.client.company_name}: {inv.total_classes} classes -> Rs.{inv.total_amount}')
