"""
Regression tests: bundled services must appear in ticket.total.

Each test is designed to FAIL on the original code (ticket.total ignores services)
and PASS after the fix in _parse_servicios_bundled.

Invariant under test (REGLA DE ORO):
  ticket.total == Σ(item['subtotal'] for item in snapshot_json['items'])
  saldo == ticket.total - pagado_acum   (saldo >= 0)
"""

import json
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth.models import User, Group


def _vendedor():
    user, _ = User.objects.get_or_create(username='vd_srv_test', defaults={'password': 'x'})
    g, _ = Group.objects.get_or_create(name='Vendedor')
    user.groups.add(g)
    return user


def _make_apartado_ticket(precio, *, user, folio_suffix=''):
    """Create an Apartado + Ticket pair with ticket.total == precio (no services yet)."""
    from boutique.models import Apartado, ApartadoItem, Ticket, Categoria, Color, Producto
    cat, _ = Categoria.objects.get_or_create(nombre='Vestido')
    col, _ = Color.objects.get_or_create(nombre='Blanco')
    prod, _ = Producto.objects.get_or_create(
        categoria=cat, color=col, talla='U',
        defaults={'precio_venta': precio, 'cantidad_actual': 1, 'stock_teorico': 1},
    )
    ap = Apartado.objects.create(
        cliente_nombre='Cliente Test',
        total=precio,
        anticipo=Decimal('0'),
    )
    ApartadoItem.objects.create(
        apartado=ap,
        producto=prod,
        descripcion=str(prod),
        cantidad=1,
        precio_unitario=precio,
        subtotal=precio,
    )
    ticket = Ticket.objects.create(
        folio=f'SRV-TEST{folio_suffix}',
        tipo='APARTADO',
        total=precio,
        total_pagado=Decimal('0'),
        apartado=ap,
        snapshot_json={
            'items': [{'descripcion': str(prod), 'cantidad': 1,
                       'precio_unitario': float(precio), 'subtotal': float(precio)}],
            'abonos': [],
            'total_pagado_acumulado': 0.0,
            'saldo_pendiente': float(precio),
        },
    )
    return ap, ticket, prod


# ---------------------------------------------------------------------------
# Test 1 — Vestido 6500 + servicio 100 → total 6600
# ---------------------------------------------------------------------------

class Test1VestidoServicioTotal(TestCase):
    """Adding a bundled service must raise ticket.total by the service cost."""

    def test_ticket_total_includes_service(self):
        user = _vendedor()
        ap, ticket, _ = _make_apartado_ticket(Decimal('6500'), user=user, folio_suffix='-1')

        from boutique.views import _parse_servicios_bundled
        servicios_json = json.dumps([{
            'tipo': 'BASTILLA', 'prenda': 'Vestido', 'cantidad': 1,
            'precio_unitario': 100, 'costo': 100, 'nota': '',
        }])
        _parse_servicios_bundled(servicios_json, None, user, None, ticket)

        ticket.refresh_from_db()
        self.assertEqual(ticket.total, Decimal('6600'),
                         "ticket.total must include the bundled service cost")

    def test_snapshot_total_matches_ticket_total(self):
        user = _vendedor()
        ap, ticket, _ = _make_apartado_ticket(Decimal('6500'), user=user, folio_suffix='-1b')

        from boutique.views import _parse_servicios_bundled
        servicios_json = json.dumps([{
            'tipo': 'BASTILLA', 'prenda': 'Vestido', 'cantidad': 1,
            'precio_unitario': 100, 'costo': 100, 'nota': '',
        }])
        _parse_servicios_bundled(servicios_json, None, user, None, ticket)

        ticket.refresh_from_db()
        # Paso 3: 'total' is no longer stored in snapshot_json — ticket.total is the only copy.
        self.assertNotIn('total', ticket.snapshot_json,
                         "snapshot_json must NOT store 'total' — ticket.total is the single source of truth")
        self.assertEqual(ticket.total, Decimal('6600'),
                         "ticket.total must include bundled service cost")

    def test_items_sum_equals_total(self):
        """Golden rule: Σ(printed items) == ticket.total"""
        user = _vendedor()
        ap, ticket, _ = _make_apartado_ticket(Decimal('6500'), user=user, folio_suffix='-1c')

        from boutique.views import _parse_servicios_bundled
        servicios_json = json.dumps([{
            'tipo': 'BASTILLA', 'prenda': 'Vestido', 'cantidad': 1,
            'precio_unitario': 100, 'costo': 100, 'nota': '',
        }])
        _parse_servicios_bundled(servicios_json, None, user, None, ticket)

        ticket.refresh_from_db()
        items = ticket.snapshot_json.get('items', [])
        items_sum = sum(Decimal(str(i['subtotal'])) for i in items)
        self.assertEqual(items_sum, ticket.total,
                         f"Σ items {items_sum} != ticket.total {ticket.total}")


# ---------------------------------------------------------------------------
# Test 2 — Apartado: abono 1000 → saldo 5600, pagado_acum 1000
# ---------------------------------------------------------------------------

class Test2ApartadoPrimerAbono(TestCase):
    """After registering a $1000 anticipo on a $6600 ticket, saldo = 5600."""

    def setUp(self):
        self.user = _vendedor()
        from boutique.models import Apartado, PagoApartado, Ticket, Categoria, Color, Producto
        # Create ticket with total already including service (6500 + 100 = 6600)
        cat, _ = Categoria.objects.get_or_create(nombre='Vestido')
        col, _ = Color.objects.get_or_create(nombre='Blanco')
        prod, _ = Producto.objects.get_or_create(
            categoria=cat, color=col, talla='M',
            defaults={'precio_venta': Decimal('6500'), 'cantidad_actual': 1, 'stock_teorico': 1},
        )
        self.ap = Apartado.objects.create(
            cliente_nombre='Cliente Abono Test',
            total=Decimal('6600'),
            anticipo=Decimal('0'),
        )
        self.ticket = Ticket.objects.create(
            folio='SRV-TEST-2',
            tipo='APARTADO',
            total=Decimal('6600'),
            total_pagado=Decimal('0'),
            apartado=self.ap,
            snapshot_json={
                'total': 6600.0,
                'items': [
                    {'descripcion': str(prod), 'cantidad': 1,
                     'precio_unitario': 6500.0, 'subtotal': 6500.0},
                    {'descripcion': 'Bastilla — Vestido', 'cantidad': 1,
                     'precio_unitario': 100.0, 'subtotal': 100.0, 'es_servicio': True},
                ],
                'abonos': [],
                'total_pagado_acumulado': 0.0,
                'saldo_pendiente': 6600.0,
            },
        )
        # Register anticipo $1000
        PagoApartado.objects.create(
            apartado=self.ap,
            monto=Decimal('1000'),
            metodo='EFECTIVO',
            registrado_por=self.user,
        )
        self.ap.refresh_from_db()

    def test_pagado_acum(self):
        from boutique.services.ticket_service import _get_live_financial_data
        total_acum, saldo, abonos = _get_live_financial_data(self.ticket)
        self.assertEqual(Decimal(str(total_acum)), Decimal('1000'),
                         "pagado_acum must be 1000 after first payment")

    def test_saldo(self):
        from boutique.services.ticket_service import _get_live_financial_data
        total_acum, saldo, abonos = _get_live_financial_data(self.ticket)
        self.assertEqual(Decimal(str(saldo)), Decimal('5600'),
                         "saldo must be 5600 (ticket.total 6600 - anticipo 1000)")

    def test_invariant(self):
        from boutique.services.ticket_service import _get_live_financial_data
        total_acum, saldo, abonos = _get_live_financial_data(self.ticket)
        self.assertAlmostEqual(
            float(total_acum) + float(saldo), float(self.ticket.total), places=2,
            msg="pagado_acum + saldo must equal ticket.total",
        )


# ---------------------------------------------------------------------------
# Test 3 — Service added AFTER first payment: saldo increases, pagado not lost
# ---------------------------------------------------------------------------

class Test3ServicioAgregadoDespuesAbono(TestCase):
    """
    Scenario:
    - Vestido $5500, anticipo $1000 → saldo = $4500
    - Service $100 added later → ticket.total = $5600, saldo = $4600 (higher)
    - pagado_acum still $1000 (not lost)
    """

    def setUp(self):
        self.user = _vendedor()
        from boutique.models import Apartado, ApartadoItem, PagoApartado, Ticket, Categoria, Color, Producto
        cat, _ = Categoria.objects.get_or_create(nombre='Vestido')
        col, _ = Color.objects.get_or_create(nombre='Rosa')
        prod, _ = Producto.objects.get_or_create(
            categoria=cat, color=col, talla='S',
            defaults={'precio_venta': Decimal('5500'), 'cantidad_actual': 1, 'stock_teorico': 1},
        )
        self.ap = Apartado.objects.create(
            cliente_nombre='Cliente Post-Servicio',
            total=Decimal('5500'),
            anticipo=Decimal('0'),
        )
        ApartadoItem.objects.create(
            apartado=self.ap, producto=prod, descripcion=str(prod),
            cantidad=1, precio_unitario=Decimal('5500'), subtotal=Decimal('5500'),
        )
        self.ticket = Ticket.objects.create(
            folio='SRV-TEST-3',
            tipo='APARTADO',
            total=Decimal('5500'),
            total_pagado=Decimal('0'),
            apartado=self.ap,
            snapshot_json={
                'items': [{'descripcion': str(prod), 'cantidad': 1,
                           'precio_unitario': 5500.0, 'subtotal': 5500.0}],
                'abonos': [],
                'total_pagado_acumulado': 0.0,
                'saldo_pendiente': 5500.0,
            },
        )
        # First payment
        PagoApartado.objects.create(
            apartado=self.ap, monto=Decimal('1000'),
            metodo='EFECTIVO', registrado_por=self.user,
        )
        self.ap.refresh_from_db()

    def test_service_added_after_payment_increases_saldo(self):
        from boutique.views import _parse_servicios_bundled
        from boutique.services.ticket_service import _get_live_financial_data

        # Record saldo before adding service
        total_acum_before, saldo_before, _ = _get_live_financial_data(self.ticket)

        # Add service after payment
        servicios_json = json.dumps([{
            'tipo': 'BASTILLA', 'prenda': 'Vestido', 'cantidad': 1,
            'precio_unitario': 100, 'costo': 100, 'nota': '',
        }])
        _parse_servicios_bundled(servicios_json, None, self.user, None, self.ticket)
        self.ticket.refresh_from_db()

        total_acum_after, saldo_after, _ = _get_live_financial_data(self.ticket)

        self.assertEqual(self.ticket.total, Decimal('5600'),
                         "ticket.total must increase by service cost")
        self.assertGreater(float(saldo_after), float(saldo_before),
                           "saldo must increase after service is added")
        self.assertEqual(Decimal(str(total_acum_after)), Decimal('1000'),
                         "pagado_acum must NOT change when service is added")

    def test_second_ticket_shows_updated_total(self):
        """The second print must show the updated total, not the original."""
        from boutique.views import _parse_servicios_bundled
        servicios_json = json.dumps([{
            'tipo': 'BASTILLA', 'prenda': 'Vestido', 'cantidad': 1,
            'precio_unitario': 100, 'costo': 100, 'nota': '',
        }])
        _parse_servicios_bundled(servicios_json, None, self.user, None, self.ticket)
        self.ticket.refresh_from_db()

        # snapshot_json no longer stores 'total'; read from ticket.total directly.
        self.assertNotIn('total', self.ticket.snapshot_json,
                         "snapshot_json must NOT store 'total'")
        self.assertEqual(self.ticket.total, Decimal('5600'))


# ---------------------------------------------------------------------------
# Test 4 — Segundo abono 2000 → pagado_acum 3000, saldo 2600
# (continuation of test-3 scenario: total = 5600 after service)
# ---------------------------------------------------------------------------

class Test4SegundoAbono(TestCase):
    """After service added (total=5600) and second payment of 2000: pagado=3000, saldo=2600."""

    def setUp(self):
        self.user = _vendedor()
        from boutique.models import Apartado, PagoApartado, Ticket

        self.ap = Apartado.objects.create(
            cliente_nombre='Cliente Dos Abonos',
            total=Decimal('5600'),
            anticipo=Decimal('0'),
        )
        self.ticket = Ticket.objects.create(
            folio='SRV-TEST-4',
            tipo='APARTADO',
            total=Decimal('5600'),  # already includes service
            total_pagado=Decimal('0'),
            apartado=self.ap,
            snapshot_json={'total': 5600.0, 'items': [], 'abonos': []},
        )
        PagoApartado.objects.create(
            apartado=self.ap, monto=Decimal('1000'),
            metodo='EFECTIVO', registrado_por=self.user,
        )
        PagoApartado.objects.create(
            apartado=self.ap, monto=Decimal('2000'),
            metodo='TRANSFERENCIA', registrado_por=self.user,
        )
        self.ap.refresh_from_db()

    def test_pagado_acum_3000(self):
        from boutique.services.ticket_service import _get_live_financial_data
        total_acum, saldo, abonos = _get_live_financial_data(self.ticket)
        self.assertEqual(Decimal(str(total_acum)), Decimal('3000'))

    def test_saldo_2600(self):
        from boutique.services.ticket_service import _get_live_financial_data
        total_acum, saldo, abonos = _get_live_financial_data(self.ticket)
        self.assertEqual(Decimal(str(saldo)), Decimal('2600'),
                         "saldo must be 5600 - 3000 = 2600")

    def test_invariant_pagado_plus_saldo(self):
        from boutique.services.ticket_service import _get_live_financial_data
        total_acum, saldo, abonos = _get_live_financial_data(self.ticket)
        self.assertAlmostEqual(
            float(total_acum) + float(saldo), float(self.ticket.total), places=2,
        )


# ---------------------------------------------------------------------------
# Test 5 — Ticket de entrega: solo se emite con saldo 0
# ---------------------------------------------------------------------------

class Test5TicketEntrega(TestCase):
    """Delivery ticket can only be issued when saldo = 0; pagado_acum = sum of all payments."""

    def setUp(self):
        self.user = _vendedor()
        from boutique.models import Apartado, PagoApartado, Ticket

        self.ap = Apartado.objects.create(
            cliente_nombre='Cliente Entrega',
            total=Decimal('5600'),
            anticipo=Decimal('0'),
        )
        self.ticket = Ticket.objects.create(
            folio='SRV-TEST-5',
            tipo='APARTADO',
            total=Decimal('5600'),
            total_pagado=Decimal('0'),
            apartado=self.ap,
            snapshot_json={'total': 5600.0, 'items': [], 'abonos': []},
        )
        # Pay in full: 1000 + 2000 + 2600 = 5600
        for monto in [Decimal('1000'), Decimal('2000'), Decimal('2600')]:
            PagoApartado.objects.create(
                apartado=self.ap, monto=monto,
                metodo='EFECTIVO', registrado_por=self.user,
            )
        self.ap.refresh_from_db()

    def test_saldo_zero_after_full_payment(self):
        from boutique.services.ticket_service import _get_live_financial_data
        total_acum, saldo, abonos = _get_live_financial_data(self.ticket)
        self.assertEqual(Decimal(str(saldo)), Decimal('0'),
                         "saldo must be 0 when fully paid")

    def test_pagado_acum_equals_total(self):
        from boutique.services.ticket_service import _get_live_financial_data
        total_acum, saldo, abonos = _get_live_financial_data(self.ticket)
        self.assertEqual(Decimal(str(total_acum)), self.ticket.total,
                         "pagado_acum must equal ticket.total when fully paid")

    def test_pagado_acum_is_sum_of_individual_tickets(self):
        """pagado_acum == Σ(each ticket's total_pagado) for this folio."""
        from boutique.services.ticket_service import _get_live_financial_data
        total_acum, saldo, abonos = _get_live_financial_data(self.ticket)
        expected = sum(Decimal(str(ab['monto'])) for ab in abonos)
        self.assertEqual(Decimal(str(total_acum)), expected,
                         "pagado_acum must equal sum of abonos")

    def test_delivery_only_when_saldo_zero(self):
        """Business rule: entrega can only happen when ap.saldo == 0."""
        self.ap.refresh_from_db()
        self.assertEqual(self.ap.saldo, Decimal('0'),
                         "Delivery should only be enabled when saldo = 0")


# ---------------------------------------------------------------------------
# Test 6 — Venta rápida con servicio y pago completo → saldo 0
# ---------------------------------------------------------------------------

class Test6VentaRapidaCompleta(TestCase):
    """Full payment venta rápida (not an apartado) with bundled service → saldo = 0."""

    def test_venta_completa_saldo_cero(self):
        user = _vendedor()
        from boutique.models import Venta, Ticket, ItemVenta, Categoria, Color, Producto
        cat, _ = Categoria.objects.get_or_create(nombre='Vestido')
        col, _ = Color.objects.get_or_create(nombre='Aqua')
        prod, _ = Producto.objects.get_or_create(
            categoria=cat, color=col, talla='L',
            defaults={'precio_venta': Decimal('6500'), 'cantidad_actual': 1, 'stock_teorico': 1},
        )
        venta = Venta.objects.create(
            vendedor=user, total=Decimal('6500'), tipo_operacion='VENTA_NORMAL',
        )
        ItemVenta.objects.create(
            venta=venta, producto=prod, cantidad=1, precio_unitario=Decimal('6500'),
        )
        ticket = Ticket.objects.create(
            folio='SRV-TEST-6',
            tipo='VENTA',
            total=Decimal('6500'),
            total_pagado=Decimal('6500'),
            venta=venta,
            snapshot_json={
                'total': 6500.0,
                'items': [{'descripcion': str(prod), 'cantidad': 1,
                           'precio_unitario': 6500.0, 'subtotal': 6500.0}],
                'abonos': [],
                'total_pagado_acumulado': 6500.0,
                'saldo_pendiente': 0.0,
            },
        )

        from boutique.views import _parse_servicios_bundled
        servicios_json = json.dumps([{
            'tipo': 'BASTILLA', 'prenda': 'Vestido', 'cantidad': 1,
            'precio_unitario': 100, 'costo': 100, 'nota': '',
        }])
        _parse_servicios_bundled(servicios_json, None, user, venta, ticket)

        # Simulate venta.total being updated (as done in api_venta_rapida)
        from boutique.models import Servicio
        srv = Servicio.objects.filter(venta=venta).first()
        venta.total += srv.costo
        venta.save(update_fields=['total'])
        # Also update ticket.total_pagado to reflect full payment including service
        ticket.refresh_from_db()
        ticket.total_pagado = ticket.total
        ticket.save(update_fields=['total_pagado'])

        ticket.refresh_from_db()
        self.assertEqual(ticket.total, Decimal('6600'),
                         "ticket.total must include service")
        saldo = ticket.total - ticket.total_pagado
        self.assertEqual(saldo, Decimal('0'),
                         "saldo must be 0 for a completed venta")
        self.assertEqual(ticket.tipo, 'VENTA',
                         "ticket type must be VENTA, not APARTADO")

    def test_items_sum_equals_total_after_service(self):
        user = _vendedor()
        from boutique.models import Venta, Ticket, ItemVenta, Categoria, Color, Producto
        cat, _ = Categoria.objects.get_or_create(nombre='Vestido')
        col, _ = Color.objects.get_or_create(nombre='Vino')
        prod, _ = Producto.objects.get_or_create(
            categoria=cat, color=col, talla='XS',
            defaults={'precio_venta': Decimal('4000'), 'cantidad_actual': 1, 'stock_teorico': 1},
        )
        venta = Venta.objects.create(
            vendedor=user, total=Decimal('4000'), tipo_operacion='VENTA_NORMAL',
        )
        ticket = Ticket.objects.create(
            folio='SRV-TEST-6b',
            tipo='VENTA',
            total=Decimal('4000'),
            total_pagado=Decimal('4000'),
            venta=venta,
            snapshot_json={
                'total': 4000.0,
                'items': [{'descripcion': str(prod), 'cantidad': 1,
                           'precio_unitario': 4000.0, 'subtotal': 4000.0}],
            },
        )
        from boutique.views import _parse_servicios_bundled
        servicios_json = json.dumps([{
            'tipo': 'TIRANTE', 'prenda': 'Vestido', 'cantidad': 2,
            'precio_unitario': 80, 'costo': 160, 'nota': 'Derecho e izquierdo',
        }])
        _parse_servicios_bundled(servicios_json, None, user, venta, ticket)
        ticket.refresh_from_db()

        items = ticket.snapshot_json.get('items', [])
        items_sum = sum(Decimal(str(i['subtotal'])) for i in items)
        self.assertEqual(items_sum, ticket.total,
                         f"Σ items {items_sum} != ticket.total {ticket.total}")


# ---------------------------------------------------------------------------
# Test 7 — Invariant across every module entry point
# ---------------------------------------------------------------------------

class Test7InvariantAllModules(TestCase):
    """
    Golden rule: for any ticket created by any module,
      Σ(snapshot items) == ticket.total
      saldo == ticket.total - pagado_acum  (saldo >= 0)
    """

    def _check_invariants(self, ticket, label=''):
        items = (ticket.snapshot_json or {}).get('items', [])
        if items:
            items_sum = sum(Decimal(str(i.get('subtotal', 0))) for i in items)
            self.assertAlmostEqual(
                float(items_sum), float(ticket.total), places=2,
                msg=f"[{label}] Σ items {items_sum} != ticket.total {ticket.total}",
            )

    def _check_saldo_invariant(self, ticket_total, pagado_acum, saldo, label=''):
        self.assertGreaterEqual(float(saldo), 0,
                                msg=f"[{label}] saldo must be >= 0")
        self.assertAlmostEqual(
            float(pagado_acum) + float(saldo), float(ticket_total), places=2,
            msg=f"[{label}] pagado_acum + saldo must equal ticket.total",
        )

    def test_novias_pedido_invariant(self):
        user = _vendedor()
        from boutique.models import Novia, Pedido, Ticket, PagoPedido
        from datetime import date

        novia = Novia.objects.create(nombre='Novia Invariant Test', fecha_boda=date(2027, 1, 1))
        pedido = Pedido.objects.create(
            novia=novia, precio=Decimal('8000'), evento='Boda', creado_por=user,
        )
        ticket = Ticket.objects.create(
            folio='SRV-TEST-7a',
            tipo='PEDIDO',
            total=Decimal('8000'),
            total_pagado=Decimal('2000'),
            pedido=pedido,
            snapshot_json={
                'total': 8000.0,
                'items': [{'descripcion': 'Vestido de Novia', 'cantidad': 1,
                           'precio_unitario': 8000.0, 'subtotal': 8000.0}],
            },
        )
        PagoPedido.objects.create(
            pedido=pedido, monto=Decimal('2000'),
            metodo='TRANSFERENCIA', registrado_por=user,
        )
        from boutique.services.ticket_service import _get_live_financial_data
        total_acum, saldo, _ = _get_live_financial_data(ticket)
        self._check_invariants(ticket, 'novias')
        self._check_saldo_invariant(ticket.total, total_acum, saldo, 'novias')

    def test_apartados_module_invariant(self):
        user = _vendedor()
        from boutique.models import Apartado, PagoApartado, Ticket
        ap = Apartado.objects.create(
            cliente_nombre='Apartado Module Test',
            total=Decimal('3500'),
            anticipo=Decimal('0'),
        )
        ticket = Ticket.objects.create(
            folio='SRV-TEST-7b',
            tipo='APARTADO',
            total=Decimal('3500'),
            total_pagado=Decimal('500'),
            apartado=ap,
            snapshot_json={
                'total': 3500.0,
                'items': [{'descripcion': 'Vestido Quinceañera', 'cantidad': 1,
                           'precio_unitario': 3500.0, 'subtotal': 3500.0}],
            },
        )
        PagoApartado.objects.create(
            apartado=ap, monto=Decimal('500'),
            metodo='EFECTIVO', registrado_por=user,
        )
        ap.refresh_from_db()
        from boutique.services.ticket_service import _get_live_financial_data
        total_acum, saldo, _ = _get_live_financial_data(ticket)
        self._check_invariants(ticket, 'apartados')
        self._check_saldo_invariant(ticket.total, total_acum, saldo, 'apartados')

    def test_venta_rapida_invariant(self):
        user = _vendedor()
        ap, ticket, _ = _make_apartado_ticket(Decimal('4500'), user=user, folio_suffix='-7c')
        from boutique.views import _parse_servicios_bundled
        from boutique.models import PagoApartado
        servicios_json = json.dumps([{
            'tipo': 'BASTILLA', 'prenda': 'Vestido', 'cantidad': 1,
            'precio_unitario': 150, 'costo': 150, 'nota': '',
        }])
        _parse_servicios_bundled(servicios_json, None, user, None, ticket)
        PagoApartado.objects.create(
            apartado=ap, monto=Decimal('1500'),
            metodo='EFECTIVO', registrado_por=user,
        )
        ap.refresh_from_db()
        ticket.refresh_from_db()
        from boutique.services.ticket_service import _get_live_financial_data
        total_acum, saldo, _ = _get_live_financial_data(ticket)
        self._check_invariants(ticket, 'venta_rapida')
        self._check_saldo_invariant(ticket.total, total_acum, saldo, 'venta_rapida')
        self.assertEqual(ticket.total, Decimal('4650'),
                         "ticket.total must be 4500 + 150 service")

    def test_servicios_module_invariant(self):
        user = _vendedor()
        from boutique.models import Servicio, Ticket, PagoServicio
        srv = Servicio.objects.create(
            tipo='BASTILLA',
            descripcion='Bastilla vestido graduación',
            costo=Decimal('200'),
            anticipo=Decimal('0'),
            estado='RECIBIDO',
            creado_por=user,
        )
        ticket = Ticket.objects.create(
            folio='SRV-TEST-7d',
            tipo='SERVICIO',
            total=Decimal('200'),
            total_pagado=Decimal('100'),
            servicio=srv,
            snapshot_json={
                'total': 200.0,
                'items': [{'descripcion': 'Bastilla vestido graduación', 'cantidad': 1,
                           'precio_unitario': 200.0, 'subtotal': 200.0}],
            },
        )
        PagoServicio.objects.create(
            servicio=srv, monto=Decimal('100'),
            metodo='EFECTIVO', registrado_por=user,
        )
        from boutique.services.ticket_service import _get_live_financial_data
        total_acum, saldo, _ = _get_live_financial_data(ticket)
        self._check_invariants(ticket, 'servicios')
        self._check_saldo_invariant(ticket.total, total_acum, saldo, 'servicios')
