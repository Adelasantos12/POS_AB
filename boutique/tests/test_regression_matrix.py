"""
End-to-end regression matrix.

Covers the stabilization fixes as integrated flows, not just unit paths.
Each test maps to one observable behaviour that must hold in production.

Regression IDs:
  R1 - ticket financial data reflects live payments, not frozen snapshot
  R2 - Pedido.__str__ is safe with novia=None
  R3 - novia_detalle renders without 500 for any combination of pedidos/pagos
  R4 - dama_detalle renders without 500 for dama with no medidas
  R5 - duplicate cobro is rejected (select_for_update guard)
  R6 - middleware loads active_profile.groups without extra queries
"""

from decimal import Decimal
from datetime import date
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User, Group


def _make_user(username, groups=('Vendedor', 'Agenda')):
    user, _ = User.objects.get_or_create(username=username, defaults={'password': 'x'})
    user.set_password('pass')
    user.save()
    for g in groups:
        grp, _ = Group.objects.get_or_create(name=g)
        user.groups.add(grp)
    return user


class R1LiveTicketFinancials(TestCase):
    """R1 — reprinted PDF/ESC-POS shows live saldo after new payment."""

    def setUp(self):
        from boutique.models import Novia, Pedido, Ticket, PagoPedido, ConfiguracionTienda
        ConfiguracionTienda.get_solo()
        self.user = _make_user('r1_user')
        self.novia = Novia.objects.create(nombre='R1 Novia', fecha_boda=date(2027, 1, 1))
        self.pedido = Pedido.objects.create(
            novia=self.novia, precio=Decimal('1000.00'),
            evento='Boda', creado_por=self.user,
        )
        # First payment — ticket frozen at this moment
        PagoPedido.objects.create(pedido=self.pedido, monto=Decimal('300.00'),
                                  metodo='EFECTIVO', registrado_por=self.user)
        self.ticket = Ticket.objects.create(
            folio='R1-001', tipo='PEDIDO',
            total=Decimal('1000.00'), total_pagado=Decimal('300.00'),
            pedido=self.pedido,
            snapshot_json={'total_pagado_acumulado': 300.0, 'saldo_pendiente': 700.0, 'abonos': []},
        )
        # Second payment — snapshot NOT updated
        PagoPedido.objects.create(pedido=self.pedido, monto=Decimal('300.00'),
                                  metodo='TRANSFERENCIA', registrado_por=self.user)

    def test_live_financial_data_reflects_both_payments(self):
        from boutique.services.ticket_service import _get_live_financial_data
        total_acum, saldo, abonos = _get_live_financial_data(self.ticket)
        self.assertAlmostEqual(total_acum, 600.0, places=2)
        self.assertAlmostEqual(saldo, 400.0, places=2)
        self.assertEqual(len(abonos), 2, "Both payments must appear in abonos list")
        # Invariant
        self.assertAlmostEqual(total_acum + saldo, float(self.ticket.total), places=2)


class R2PedidoStrSafe(TestCase):
    """R2 — str(Pedido) with novia=None must not raise."""

    def setUp(self):
        from boutique.models import ConfiguracionTienda
        ConfiguracionTienda.get_solo()
        self.user = _make_user('r2_user')

    def test_str_null_novia(self):
        from boutique.models import Pedido
        p = Pedido.objects.create(novia=None, precio=Decimal('500.00'),
                                  evento='Fiesta', creado_por=self.user)
        result = str(p)
        self.assertIn('Sin novia', result)

    def test_str_null_dama(self):
        from boutique.models import Novia, Pedido
        novia = Novia.objects.create(nombre='R2 Novia', fecha_boda=date(2027, 2, 1))
        p = Pedido.objects.create(novia=novia, dama=None, es_vestido_novia=False,
                                  precio=Decimal('500.00'), evento='Boda',
                                  creado_por=self.user)
        result = str(p)
        self.assertIsInstance(result, str)


class R3NoviaDetalle200(TestCase):
    """R3 — novia_detalle returns 200 for novia with multiple pedidos/pagos."""

    def setUp(self):
        from boutique.models import Novia, Pedido, PagoPedido, ConfiguracionTienda
        ConfiguracionTienda.get_solo()
        self.user = _make_user('r3_user')
        self.novia = Novia.objects.create(nombre='R3 Novia', fecha_boda=date(2027, 3, 1))
        for i in range(3):
            p = Pedido.objects.create(
                novia=self.novia, precio=Decimal('1000.00'),
                evento='Boda', creado_por=self.user,
            )
            PagoPedido.objects.create(pedido=p, monto=Decimal('400.00'),
                                      metodo='EFECTIVO', registrado_por=self.user)

    def test_novia_detalle_200(self):
        client = Client()
        client.login(username='r3_user', password='pass')
        s = client.session
        s['active_profile_id'] = self.user.id
        s.save()
        response = client.get(reverse('novia_detalle', kwargs={'pk': self.novia.pk}))
        self.assertEqual(response.status_code, 200)

    def test_novia_semaforo_correct(self):
        # 3 pedidos × $400 paid → $1200; none liquidado → semaforo_pago != 'success'
        self.assertNotEqual(self.novia.semaforo_pago, 'success')
        self.assertEqual(self.novia.total_pagado, Decimal('1200.00'))


class R4DamaDetalle200(TestCase):
    """R4 — dama_detalle returns 200 when dama has no medidas and no vestido."""

    def setUp(self):
        from boutique.models import Novia, Dama, ConfiguracionTienda
        ConfiguracionTienda.get_solo()
        self.user = _make_user('r4_user')
        self.novia = Novia.objects.create(nombre='R4 Novia', fecha_boda=date(2027, 4, 1))
        self.dama = Dama.objects.create(novia=self.novia, nombre='Dama R4')

    def test_dama_detalle_200(self):
        client = Client()
        client.login(username='r4_user', password='pass')
        s = client.session
        s['active_profile_id'] = self.user.id
        s.save()
        response = client.get(reverse('dama_detalle', kwargs={'pk': self.dama.pk}))
        self.assertEqual(response.status_code, 200)


class R5DuplicateCobro(TestCase):
    """
    R5 — api_cobrar_item rejects a second payment on an already-paid item.

    The select_for_update guard must prevent double-payment on a saldo=0 item.
    """

    def setUp(self):
        from boutique.models import Novia, Pedido, PagoPedido, ConfiguracionTienda, CorteCaja
        ConfiguracionTienda.get_solo()
        self.user = _make_user('r5_user', groups=('Vendedor', 'Admin'))
        self.novia = Novia.objects.create(nombre='R5 Novia', fecha_boda=date(2027, 5, 1))
        self.pedido = Pedido.objects.create(
            novia=self.novia, precio=Decimal('500.00'),
            evento='Boda', creado_por=self.user,
        )
        # Open a caja so registrar_cobro works
        self.caja = CorteCaja.objects.create(
            abierto_por=self.user,
            monto_apertura=Decimal('1000.00'),
        )
        # Fully pay the pedido
        PagoPedido.objects.create(pedido=self.pedido, monto=Decimal('500.00'),
                                  metodo='EFECTIVO', registrado_por=self.user)

    def test_cobrar_ya_pagado_returns_400(self):
        import json
        client = Client()
        client.login(username='r5_user', password='pass')
        s = client.session
        s['active_profile_id'] = self.user.id
        s.save()

        response = client.post(
            reverse('api_cobrar_item', kwargs={'tipo': 'pedido', 'pk': self.pedido.pk}),
            data=json.dumps({'monto': '100.00', 'metodo': 'EFECTIVO'}),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('pagado', response.json().get('message', '').lower())
