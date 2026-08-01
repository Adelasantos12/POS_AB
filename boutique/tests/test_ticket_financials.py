"""
Tests for ticket financial data consistency.

Invariant under test:
  The financial figures shown in the PDF and ESC/POS printouts
  (total_pagado_acumulado, saldo_pendiente, abonos) must reflect the
  live balance recorded in the database, not the frozen snapshot created
  when the first payment was made.

Failure mode reproduced:
  1. Pedido created with precio = 1000.
  2. First payment of 300 → Ticket emitted with snapshot saldo_pendiente = 700.
  3. Second payment of 300 is recorded.
  4. PDF is requested.
  5. BUG: PDF reads saldo from frozen snapshot (700) instead of live value (400).

Commit: test: reproduce ticket advance payment inconsistencies
"""

from decimal import Decimal
from datetime import date
from django.test import TestCase
from django.contrib.auth.models import User, Group


def _make_vendedor():
    user, _ = User.objects.get_or_create(username='vendedor_test',
                                          defaults={'password': 'x'})
    g, _ = Group.objects.get_or_create(name='Vendedor')
    user.groups.add(g)
    return user


class TicketFinancialConsistencyTest(TestCase):
    """
    Reproduce: stale snapshot causes PDF to show wrong saldo after new abono.
    """

    def setUp(self):
        from boutique.models import (
            Categoria, Color, Novia, Pedido, Ticket,
            ConfiguracionTienda, PagoPedido,
        )
        self.user = _make_vendedor()
        self.config = ConfiguracionTienda.get_solo()

        self.novia = Novia.objects.create(
            nombre='Prueba Financiera',
            fecha_boda=date(2027, 6, 15),
        )

        cat, _ = Categoria.objects.get_or_create(nombre='Vestido')
        self.pedido = Pedido.objects.create(
            novia=self.novia,
            precio=Decimal('1000.00'),
            evento='Boda prueba',
            creado_por=self.user,
        )

        # First payment of 300 — this is the live DB record.
        PagoPedido.objects.create(
            pedido=self.pedido,
            monto=Decimal('300.00'),
            metodo='EFECTIVO',
            registrado_por=self.user,
        )

        # Ticket frozen at the moment of the first payment.
        # Snapshot says: paid_so_far = 300, saldo = 700 — correct at creation time.
        self.ticket = Ticket.objects.create(
            folio='TEST-001',
            tipo='PEDIDO',
            total=Decimal('1000.00'),
            total_pagado=Decimal('300.00'),
            pedido=self.pedido,
            snapshot_json={
                'items': [],
                'total_pagado_acumulado': 300.0,
                'saldo_pendiente': 700.0,
                'abonos': [
                    {'fecha': '2026-01-01', 'monto': 300.0, 'metodo': 'EFECTIVO'},
                ],
            },
        )

    def _make_second_payment(self):
        """Register a second payment of 300 AFTER the ticket was emitted."""
        from boutique.models import PagoPedido
        PagoPedido.objects.create(
            pedido=self.pedido,
            monto=Decimal('300.00'),
            metodo='EFECTIVO',
            registrado_por=self.user,
        )

    # ------------------------------------------------------------------
    # Reproduce the bug using the current (unfixed) code path
    # ------------------------------------------------------------------

    def test_live_saldo_after_second_payment(self):
        """
        After a second payment of 300, the live Pedido.saldo_pendiente
        must be 400 (1000 - 300 - 300).
        This test verifies the model property is correct.
        """
        self._make_second_payment()
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.saldo_pendiente, Decimal('400.00'))

    def test_stale_snapshot_saldo_differs_from_live(self):
        """
        REPRODUCE BUG: The snapshot frozen at ticket creation still shows
        saldo = 700 even after a second payment reduces it to 400.
        This confirms the stale-read problem.
        """
        self._make_second_payment()
        snap = self.ticket.snapshot_json
        saldo_snapshot = Decimal(str(snap['saldo_pendiente']))   # 700 — stale
        saldo_live = self.pedido.saldo_pendiente                  # 400 — correct

        # The snapshot is stale — this inequality is the bug we are fixing.
        self.assertNotEqual(
            saldo_snapshot,
            saldo_live,
            "Snapshot is unexpectedly up-to-date — nothing left to fix.",
        )

    def test_pdf_helper_returns_live_saldo(self):
        """
        FAILS on original code: _get_live_financial_data does not exist yet.
        After the fix, it must return (total_acum=600, saldo=400, abonos=[...]).

        Invariants:
          total_acum + saldo == ticket.total
          total_acum == sum(p.monto for p in pedido.pagos_pedido.all())
        """
        self._make_second_payment()

        # This import FAILS (ImportError) on the original code,
        # making the test an ERROR → test suite fails → fix is required.
        from boutique.services.ticket_service import _get_live_financial_data

        total_acum, saldo, abonos = _get_live_financial_data(self.ticket)

        expected_total_acum = Decimal('600.00')  # 300 + 300
        expected_saldo = Decimal('400.00')        # 1000 - 600

        self.assertEqual(
            Decimal(str(total_acum)),
            expected_total_acum,
            f"total_acum: expected {expected_total_acum}, got {total_acum}",
        )
        self.assertEqual(
            Decimal(str(saldo)),
            expected_saldo,
            f"saldo: expected {expected_saldo}, got {saldo}",
        )
        # Invariant: total_acum + saldo == grand_total
        grand_total = float(self.ticket.total)
        self.assertAlmostEqual(
            total_acum + saldo,
            grand_total,
            places=2,
            msg="total_acum + saldo must equal ticket.total",
        )
        # Abonos must have 2 entries (one per payment)
        self.assertEqual(len(abonos), 2)

    def test_apartado_live_financial_data(self):
        """
        Same invariant for Apartado: after a second PagoApartado,
        _get_live_financial_data must return live saldo, not stale snapshot.
        """
        from boutique.models import Apartado, PagoApartado, Ticket

        apartado = Apartado.objects.create(
            cliente_nombre='Cliente Test',
            total=Decimal('2000.00'),
            anticipo=Decimal('0.00'),
        )
        ticket_ap = Ticket.objects.create(
            folio='TEST-AP-001',
            tipo='APARTADO',
            total=Decimal('2000.00'),
            total_pagado=Decimal('500.00'),
            apartado=apartado,
            snapshot_json={
                'items': [],
                'total_pagado_acumulado': 500.0,
                'saldo_pendiente': 1500.0,
                'abonos': [],
            },
        )
        # First payment (anticipo)
        PagoApartado.objects.create(
            apartado=apartado,
            monto=Decimal('500.00'),
            metodo='EFECTIVO',
            registrado_por=self.user,
        )
        # Second payment — snapshot not updated
        PagoApartado.objects.create(
            apartado=apartado,
            monto=Decimal('500.00'),
            metodo='TRANSFERENCIA',
            registrado_por=self.user,
        )

        from boutique.services.ticket_service import _get_live_financial_data
        apartado.refresh_from_db()

        total_acum, saldo, abonos = _get_live_financial_data(ticket_ap)

        self.assertEqual(Decimal(str(total_acum)), apartado.anticipo,
                         "total_acum must equal live Apartado.anticipo")
        self.assertEqual(Decimal(str(saldo)), apartado.saldo,
                         "saldo must equal live Apartado.saldo")
        self.assertEqual(len(abonos), 2,
                         "Must return both payments, not just first")
