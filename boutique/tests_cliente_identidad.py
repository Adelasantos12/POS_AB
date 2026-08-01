"""
Tests de identidad de cliente para todas las operaciones que generan ticket.
Regla central: una venta anónima puede existir; una deuda anónima no.
"""
import json
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User, Group
from boutique.models import (
    Categoria, Color, Producto, Apartado, Venta, Ticket, Cliente
)


def _setup_caja(user):
    """Crea una caja abierta para que registrar_cobro no falle."""
    from boutique.models import CorteCaja
    return CorteCaja.objects.create(
        abierto_por=user,
        monto_apertura=1000,
        cerrado=False
    )


def _make_producto(precio=500):
    cat, _ = Categoria.objects.get_or_create(nombre='Vestido')
    col, _ = Color.objects.get_or_create(nombre='Rojo')
    return Producto.objects.create(
        categoria=cat, color=col, talla='M',
        precio_venta=precio, cantidad_actual=1, stock_teorico=1
    )


class ClienteIdentidadBaseTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='cajera', password='pass')
        grupo, _ = Group.objects.get_or_create(name='Vendedor')
        self.user.groups.add(grupo)
        self.client.login(username='cajera', password='pass')
        session = self.client.session
        session['active_profile_id'] = self.user.id
        session.save()
        _setup_caja(self.user)
        self.producto = _make_producto()


# ──────────────────────────────────────────────────────────────────────────────
# TC-ID-01: Venta inmediata — cliente registrado por nombre y teléfono
# ──────────────────────────────────────────────────────────────────────────────
class TC_ID_01_VentaClienteRegistrado(ClienteIdentidadBaseTest):

    def test_venta_con_nombre_y_telefono_crea_cliente(self):
        """Venta inmediata con nombre+teléfono: se crea Cliente y el ticket lleva el nombre."""
        payload = {
            'items': [{'id': self.producto.id, 'cantidad': 1}],
            'total': 500,
            'pago_inicial': 500,
            'metodo': 'EFECTIVO',
            'es_apartado': False,
            'cliente_nombre': 'Ana López',
            'cliente_telefono': '5551234567',
        }
        r = self.client.post(
            reverse('api_registrar_venta'),
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(r.status_code, 200, r.content)
        data = r.json()
        self.assertEqual(data['status'], 'ok')

        ticket = Ticket.objects.get(folio=data['folio'])
        self.assertEqual(ticket.cliente_nombre, 'Ana López')
        self.assertEqual(ticket.cliente_telefono, '5551234567')

        cliente = Cliente.objects.filter(telefono='5551234567').first()
        self.assertIsNotNone(cliente)
        self.assertEqual(cliente.nombre, 'Ana López')

    def test_venta_nombre_sin_telefono_parchea_ticket(self):
        """Venta sin teléfono: no se crea Cliente pero el ticket lleva el nombre."""
        payload = {
            'items': [{'id': self.producto.id, 'cantidad': 1}],
            'total': 500,
            'pago_inicial': 500,
            'metodo': 'EFECTIVO',
            'es_apartado': False,
            'cliente_nombre': 'María García',
            'cliente_telefono': '',
        }
        r = self.client.post(
            reverse('api_registrar_venta'),
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(r.status_code, 200, r.content)
        folio = r.json()['folio']
        ticket = Ticket.objects.get(folio=folio)
        self.assertEqual(ticket.cliente_nombre, 'María García')


# ──────────────────────────────────────────────────────────────────────────────
# TC-ID-02: Venta inmediata — venta anónima ("Sin registro")
# ──────────────────────────────────────────────────────────────────────────────
class TC_ID_02_VentaAnonima(ClienteIdentidadBaseTest):

    def test_venta_con_sin_registro_true_acepta(self):
        """Venta inmediata con sin_registro=True: se acepta y el ticket dice 'Sin registro'."""
        payload = {
            'items': [{'id': self.producto.id, 'cantidad': 1}],
            'total': 500,
            'pago_inicial': 500,
            'metodo': 'EFECTIVO',
            'es_apartado': False,
            'sin_registro': True,
        }
        r = self.client.post(
            reverse('api_registrar_venta'),
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(r.status_code, 200, r.content)
        folio = r.json()['folio']
        ticket = Ticket.objects.get(folio=folio)
        self.assertEqual(ticket.cliente_nombre, 'Sin registro')
        self.assertEqual(ticket.cliente_telefono, '')

    def test_venta_sin_nombre_y_sin_sin_registro_rechaza(self):
        """Venta sin nombre y sin sin_registro=True: debe ser rechazada."""
        payload = {
            'items': [{'id': self.producto.id, 'cantidad': 1}],
            'total': 500,
            'pago_inicial': 500,
            'metodo': 'EFECTIVO',
            'es_apartado': False,
            'cliente_nombre': '',
        }
        r = self.client.post(
            reverse('api_registrar_venta'),
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn('nombre', r.json()['message'].lower())

    def test_venta_nombre_default_rechaza(self):
        """Nombres trampa no deben colarse: string vacío."""
        payload = {
            'items': [{'id': self.producto.id, 'cantidad': 1}],
            'total': 500,
            'pago_inicial': 500,
            'metodo': 'EFECTIVO',
            'es_apartado': False,
            'cliente_nombre': '   ',
        }
        r = self.client.post(
            reverse('api_registrar_venta'),
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(r.status_code, 400)


# ──────────────────────────────────────────────────────────────────────────────
# TC-ID-03: Apartado — deuda anónima rechazada
# ──────────────────────────────────────────────────────────────────────────────
class TC_ID_03_ApartadoIdentidadObligatoria(ClienteIdentidadBaseTest):

    def test_apartado_sin_nombre_rechaza(self):
        """Apartado sin nombre del cliente debe ser rechazado."""
        payload = {
            'items': [{'id': self.producto.id, 'cantidad': 1}],
            'total': 500,
            'pago_inicial': 100,
            'metodo': 'EFECTIVO',
            'es_apartado': True,
            'cliente_nombre': '',
        }
        r = self.client.post(
            reverse('api_registrar_venta'),
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn('nombre', r.json()['message'].lower())

    def test_apartado_sin_registro_rechaza(self):
        """Apartado con sin_registro=True debe ser rechazado."""
        payload = {
            'items': [{'id': self.producto.id, 'cantidad': 1}],
            'total': 500,
            'pago_inicial': 100,
            'metodo': 'EFECTIVO',
            'es_apartado': True,
            'sin_registro': True,
            'cliente_nombre': '',
        }
        r = self.client.post(
            reverse('api_registrar_venta'),
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(r.status_code, 400)

    def test_apartado_sin_registro_como_nombre_rechaza(self):
        """Apartado con 'Sin registro' como nombre literal debe ser rechazado."""
        payload = {
            'items': [{'id': self.producto.id, 'cantidad': 1}],
            'total': 500,
            'pago_inicial': 100,
            'metodo': 'EFECTIVO',
            'es_apartado': True,
            'cliente_nombre': 'Sin registro',
        }
        r = self.client.post(
            reverse('api_registrar_venta'),
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(r.status_code, 400)

    def test_apartado_con_nombre_acepta(self):
        """Apartado con nombre real debe ser aceptado."""
        payload = {
            'items': [{'id': self.producto.id, 'cantidad': 1}],
            'total': 500,
            'pago_inicial': 100,
            'metodo': 'EFECTIVO',
            'es_apartado': True,
            'cliente_nombre': 'Laura Martínez',
            'cliente_telefono': '5559876543',
        }
        r = self.client.post(
            reverse('api_registrar_venta'),
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(r.status_code, 200, r.content)
        data = r.json()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['tipo'], 'apartado')

        ticket = Ticket.objects.get(folio=data['ticket'])
        self.assertEqual(ticket.cliente_nombre, 'Laura Martínez')


# ──────────────────────────────────────────────────────────────────────────────
# TC-ID-04: api_crear_apartado — validación independiente
# ──────────────────────────────────────────────────────────────────────────────
class TC_ID_04_ApiCrearApartado(ClienteIdentidadBaseTest):

    def test_crear_apartado_sin_nombre_rechaza(self):
        payload = {
            'items': [{'id': self.producto.id, 'cantidad': 1}],
            'total': 500,
            'anticipo': 100,
            'metodo': 'EFECTIVO',
            'cliente_nombre': '',
        }
        r = self.client.post(
            reverse('api_crear_apartado'),
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn('nombre', r.json()['message'].lower())

    def test_crear_apartado_con_nombre_acepta(self):
        payload = {
            'items': [{'id': self.producto.id, 'cantidad': 1}],
            'total': 500,
            'anticipo': 100,
            'metodo': 'EFECTIVO',
            'cliente_nombre': 'Sofía Ramírez',
            'cliente_telefono': '5550001111',
        }
        r = self.client.post(
            reverse('api_crear_apartado'),
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()['status'], 'ok')
        ap = Apartado.objects.get(id=r.json()['id'])
        self.assertEqual(ap.cliente_nombre, 'Sofía Ramírez')


# ──────────────────────────────────────────────────────────────────────────────
# TC-ID-05: Servicio — nombre obligatorio
# ──────────────────────────────────────────────────────────────────────────────
class TC_ID_05_ServicioClienteObligatorio(ClienteIdentidadBaseTest):

    def test_servicio_sin_nombre_y_sin_id_rechaza(self):
        payload = {
            'tipo': 'BASTILLA',
            'descripcion': 'Bastilla pantalón',
            'costo': 150,
            'anticipo': 0,
        }
        r = self.client.post(
            reverse('api_crear_servicio'),
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn('nombre', r.json()['message'].lower())

    def test_servicio_con_nombre_acepta(self):
        payload = {
            'tipo': 'BASTILLA',
            'descripcion': 'Bastilla pantalón',
            'costo': 150,
            'anticipo': 0,
            'cliente_nombre': 'Carmen Vega',
            'cliente_telefono': '5553334444',
        }
        r = self.client.post(
            reverse('api_crear_servicio'),
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()['status'], 'ok')

    def test_servicio_con_cliente_id_existente_acepta(self):
        cliente = Cliente.objects.create(nombre='Rosa Flores', telefono='5557778888')
        payload = {
            'tipo': 'AJUSTE',
            'descripcion': 'Ajuste de talle',
            'costo': 200,
            'anticipo': 0,
            'cliente_id': cliente.id,
        }
        r = self.client.post(
            reverse('api_crear_servicio'),
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()['status'], 'ok')
