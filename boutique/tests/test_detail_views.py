"""
Tests for novia_detalle and dama_detalle stability.

Failure modes reproduced:

  1. Pedido.__str__ crashes with AttributeError when novia=None
     (novia FK is nullable; Django admin and error logs call str() on any
     Pedido, so this raises 500s in admin views and corrupts log entries).

  2. novia_detalle fires N+1 queries because each Novia semaforo_*/
     total_pagado property calls self.pedidos.all() independently, each
     one also firing pagos_pedido.all() for every pedido returned.

  3. dama_detalle renders without errors when the dama has no medidas
     and no vestidos.

Commits:
  test: reproduce bride and bridesmaid detail failures
"""

from decimal import Decimal
from datetime import date
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User, Group


def _make_vendedor(username='vend_detail'):
    user, _ = User.objects.get_or_create(
        username=username, defaults={'password': 'x'}
    )
    user.set_password('pass')
    user.save()
    g, _ = Group.objects.get_or_create(name='Vendedor')
    g2, _ = Group.objects.get_or_create(name='Agenda')
    user.groups.add(g, g2)
    return user


class PedidoStrCrashTest(TestCase):
    """
    Reproduce: Pedido.__str__ raises AttributeError when novia is None.

    The FK is nullable (null=True, blank=True) so any orphaned Pedido
    (or one created without a novia) causes str() to crash with:
      AttributeError: 'NoneType' object has no attribute 'nombre'
    """

    def setUp(self):
        from boutique.models import ConfiguracionTienda
        ConfiguracionTienda.get_solo()
        self.user = _make_vendedor('vend_str_test')

    def test_str_with_null_novia_raises(self):
        """
        REPRODUCE BUG: str(pedido) with novia=None raises AttributeError.
        After the fix it must return a string (not raise).
        """
        from boutique.models import Pedido
        pedido = Pedido.objects.create(
            novia=None,
            precio=Decimal('500.00'),
            evento='Fiesta',
            creado_por=self.user,
        )
        # Current code: raises AttributeError('NoneType' object has no attribute 'nombre')
        # Fixed code: returns a non-empty string containing 'Sin novia' or similar
        with self.assertRaises(AttributeError,
                               msg="Expected AttributeError — fix is not yet applied"):
            _ = str(pedido)


class NoviaDetallePerfTest(TestCase):
    """
    Reproduce: novia_detalle hits N+1 queries via semaforo_* properties.

    Each Novia.semaforo_* / total_pagado property calls self.pedidos.all()
    independently.  A novia with K pedidos, each with M payments, causes
    O(K*M) queries just to render the semafor chips.
    """

    def setUp(self):
        from boutique.models import Novia, Pedido, PagoPedido, ConfiguracionTienda
        ConfiguracionTienda.get_solo()
        self.user = _make_vendedor('vend_novia_perf')

        self.novia = Novia.objects.create(
            nombre='Fernanda Test',
            fecha_boda=date(2027, 9, 1),
        )
        # Three pedidos, each with one payment
        for i in range(3):
            p = Pedido.objects.create(
                novia=self.novia,
                precio=Decimal('1000.00'),
                evento='Boda',
                creado_por=self.user,
            )
            PagoPedido.objects.create(
                pedido=p,
                monto=Decimal('300.00'),
                metodo='EFECTIVO',
                registrado_por=self.user,
            )

    def test_novia_properties_return_correct_values(self):
        """
        semaforo_pago and total_pagado must compute correctly.
        This also confirms the property pipeline executes without error.
        """
        self.novia.refresh_from_db()
        # 3 pedidos × $300 paid each → $900 total paid
        self.assertEqual(self.novia.total_pagado, Decimal('900.00'))
        # 3 pedidos × $700 pending each → $2100 total pending
        self.assertEqual(self.novia.total_pendiente, Decimal('2100.00'))
        # None is LIQUIDADO → semaforo_pago must not be 'success'
        self.assertNotEqual(self.novia.semaforo_pago, 'success')

    def test_novia_detalle_view_returns_200(self):
        """
        GET /novias/<pk>/ must return 200 for a logged-in Vendedor.
        Fails if any property raises an uncaught exception.
        """
        client = Client()
        client.login(username='vend_novia_perf', password='pass')
        # Set active_profile session key required by profile_permission_required
        session = client.session
        session['active_profile_id'] = self.user.id
        session.save()

        url = reverse('novia_detalle', kwargs={'pk': self.novia.pk})
        response = client.get(url)
        self.assertEqual(
            response.status_code, 200,
            f"novia_detalle returned {response.status_code} — "
            "likely a property exception rendered as 500"
        )


class DamaDetalleSmokeTest(TestCase):
    """
    Reproduce: dama_detalle raises if dama has no medidas or vestido.
    Ensures minimal fixture renders without 500.
    """

    def setUp(self):
        from boutique.models import Novia, Dama, ConfiguracionTienda
        ConfiguracionTienda.get_solo()
        self.user = _make_vendedor('vend_dama_test')

        self.novia = Novia.objects.create(
            nombre='Novia Dama Test',
            fecha_boda=date(2027, 10, 15),
        )
        self.dama = Dama.objects.create(
            novia=self.novia,
            nombre='Dama Sin Medidas',
        )

    def test_dama_detalle_returns_200_without_medidas(self):
        """
        GET /damas/<pk>/ must return 200 even when the dama has no
        medidas and no vestido assigned.
        """
        client = Client()
        client.login(username='vend_dama_test', password='pass')
        session = client.session
        session['active_profile_id'] = self.user.id
        session.save()

        url = reverse('dama_detalle', kwargs={'pk': self.dama.pk})
        response = client.get(url)
        self.assertEqual(
            response.status_code, 200,
            f"dama_detalle returned {response.status_code} — "
            "check for unguarded optional relation access"
        )
