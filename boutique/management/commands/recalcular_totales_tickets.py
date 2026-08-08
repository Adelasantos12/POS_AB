"""
Management command: recalcular_totales_tickets

TAREA 3 — Migración de totales de tickets existentes.

Finds tickets where ticket.total disagrees with snapshot_json['total']
(caused by bundled services being appended to the snapshot but not to the
ticket.total DB field before the fix in _parse_servicios_bundled).

Usage:
  python manage.py recalcular_totales_tickets          # dry run — report only
  python manage.py recalcular_totales_tickets --fix    # apply corrections
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from decimal import Decimal


class Command(BaseCommand):
    help = "Report (and optionally fix) tickets where ticket.total != snapshot_json['total']"

    def add_arguments(self, parser):
        parser.add_argument(
            '--fix',
            action='store_true',
            default=False,
            help='Apply the corrected totals. Without this flag the command only reports.',
        )
        parser.add_argument(
            '--min-diff',
            type=float,
            default=0.01,
            help='Minimum discrepancy in MXN to include in the report (default: 0.01).',
        )

    def handle(self, *args, **options):
        from boutique.models import Ticket

        fix_mode = options['fix']
        min_diff = Decimal(str(options['min_diff']))

        qs = Ticket.objects.exclude(snapshot_json=None)

        discrepancies = []

        for ticket in qs.iterator(chunk_size=500):
            snap_total = ticket.snapshot_json.get('total')
            if snap_total is None:
                continue
            snap_total_dec = Decimal(str(snap_total))
            db_total = ticket.total
            diff = snap_total_dec - db_total
            if abs(diff) >= min_diff:
                discrepancies.append((ticket, db_total, snap_total_dec, diff))

        if not discrepancies:
            self.stdout.write(self.style.SUCCESS("No discrepancies found."))
            return

        self.stdout.write(
            f"\n{'Folio':<20} {'DB total':>12} {'Snap total':>12} {'Diff':>10}"
        )
        self.stdout.write("-" * 58)
        for ticket, db_total, snap_total_dec, diff in discrepancies:
            sign = '+' if diff > 0 else ''
            self.stdout.write(
                f"{ticket.folio:<20} {float(db_total):>12.2f} {float(snap_total_dec):>12.2f} "
                f"{sign}{float(diff):>9.2f}"
            )

        self.stdout.write("-" * 58)
        self.stdout.write(
            f"Total: {len(discrepancies)} ticket(s) with discrepancy >= {min_diff} MXN."
        )

        if not fix_mode:
            self.stdout.write(
                self.style.WARNING(
                    "\nDRY RUN — no changes written. Re-run with --fix to apply corrections."
                )
            )
            return

        updated = 0
        with transaction.atomic():
            for ticket, _db_total, snap_total_dec, _diff in discrepancies:
                ticket.total = snap_total_dec
                ticket.save(update_fields=['total'])
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(f"\nFixed {updated} ticket(s). ticket.total now matches snapshot_json['total'].")
        )
