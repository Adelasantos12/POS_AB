"""
Tests para el Módulo de Pedidos Operativo Completo.
Verifica las 6 rutas de creación y las operaciones principales.
"""
import json
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User, Group
from boutique.models import (
    Pedido, PedidoItem, Cliente, Novia, Dama, Secuencia,
    Color, Tela, Modelo, CorteCaja,
)


class PedidoItemModelTest(TestCase):
    """TC-PO-01: PedidoItem genera código automático."""

    def setUp(self):
        from django.contrib.auth.models import User
        self.user = User.objects.create_user(username='u', password='p')
        self.novia = Novia.objects.create(nombre='Novia Test', fecha_boda='2027-06-01')
        self.pedido = Pedido.objects.create(novia=self.novia, precio=1000, creado_por=self.user)

    def test_codigo_autogenerado(self):
        item = PedidoItem.objects.create(
            pedido=self.pedido,
            tipo='VESTIDO',
            precio=1000,
        )
        self.assertTrue(item.codigo.startswith('PI-'))
        self.assertEqual(len(item.codigo.split('-')), 3)

    def test_codigo_unico_por_item(self):
        item1 = PedidoItem.objects.create(pedido=self.pedido, tipo='VESTIDO', precio=500)
        item2 = PedidoItem.objects.create(pedido=self.pedido, tipo='ACCESORIO', precio=200)
        self.assertNotEqual(item1.codigo, item2.codigo)

    def test_to_dict_serializable(self):
        item = PedidoItem.objects.create(pedido=self.pedido, tipo='VESTIDO', precio=999, talla='M')
        d = item.to_dict()
        self.assertEqual(d['tipo'], 'VESTIDO')
        self.assertEqual(d['precio'], 999.0)
        self.assertEqual(d['talla'], 'M')


class PedidoNuevoPageTest(TestCase):
    """TC-PO-02: La página /pedidos/nuevo/ carga con prefilling desde contexto."""

    def setUp(self):
        self.user = User.objects.create_user(username='staff', password='pass')
        grp, _ = Group.objects.get_or_create(name='Vendedor')
        self.user.groups.add(grp)
        self.client.login(username='staff', password='pass')
        session = self.client.session
        session['active_profile_id'] = self.user.id
        session.save()
        self.novia = Novia.objects.create(nombre='Daniela Ríos', fecha_boda='2027-06-01')
        self.dama = Dama.objects.create(nombre='Sofía López', novia=self.novia)
        self.cliente = Cliente.objects.create(nombre='Roberto Gutiérrez', telefono='3310000001')

    def test_page_loads(self):
        res = self.client.get(reverse('pedido_nuevo'))
        self.assertEqual(res.status_code, 200)
        self.assertTemplateUsed(res, 'boutique/pedido_nuevo.html')

    def test_prefill_from_novia(self):
        res = self.client.get(reverse('pedido_nuevo'), {'novia_id': self.novia.pk})
        self.assertContains(res, 'Daniela Ríos')

    def test_prefill_from_dama(self):
        res = self.client.get(reverse('pedido_nuevo'), {'dama_id': self.dama.pk})
        self.assertContains(res, 'Sofía López')

    def test_prefill_from_cliente(self):
        res = self.client.get(reverse('pedido_nuevo'), {'cliente_id': self.cliente.pk})
        self.assertContains(res, 'Roberto Gutiérrez')


class CrearPedidoDesdeAPI(TestCase):
    """Base para los 6 contextos de creación."""

    def setUp(self):
        self.user = User.objects.create_user(username='staff2', password='pass')
        grp, _ = Group.objects.get_or_create(name='Vendedor')
        self.user.groups.add(grp)
        self.client.login(username='staff2', password='pass')
        session = self.client.session
        session['active_profile_id'] = self.user.id
        session.save()
        color, _ = Color.objects.get_or_create(nombre='Rojo')
        self.color = color
        self.novia = Novia.objects.create(nombre='Ana García', fecha_boda='2027-06-01')
        self.dama = Dama.objects.create(nombre='Luisa Pérez', novia=self.novia)
        self.cliente = Cliente.objects.create(nombre='Carlos Mendoza', telefono='3310000002')
        CorteCaja.objects.create(abierto_por=self.user, monto_apertura=1000, cerrado=False)

    def _base_payload(self, **overrides):
        payload = {
            'cliente_nombre': 'Test Cliente',
            'cliente_telefono': '',
            'tipo_pedido': 'PEDIDO_EXTERNO',
            'evento': 'Boda',
            'notas': '',
            'anticipo': 0,
            'metodo_pago': 'EFECTIVO',
            'items': [
                {
                    'tipo': 'VESTIDO',
                    'precio': '2500',
                    'cantidad': '1',
                    'talla': 'M',
                }
            ],
        }
        payload.update(overrides)
        return payload


class TC_PO_03_CrearDesdeCaja(CrearPedidoDesdeAPI):
    """TC-PO-03: Creación desde Caja (sin novia ni dama)."""

    def test_crear_pedido_standalone(self):
        payload = self._base_payload(
            cliente_nombre='Cliente Caja',
            cliente_telefono='3310000099',
        )
        res = self.client.post(
            reverse('api_pedido_nuevo'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(res.status_code, 200)
        d = res.json()
        self.assertEqual(d['status'], 'ok')
        pedido = Pedido.objects.get(pk=d['pedido_id'])
        self.assertEqual(pedido.items.count(), 1)
        self.assertEqual(pedido.items.first().tipo, 'VESTIDO')
        # Cliente creado por teléfono
        self.assertTrue(Cliente.objects.filter(telefono='3310000099').exists())

    def test_sin_nombre_falla(self):
        payload = self._base_payload(cliente_nombre='')
        res = self.client.post(
            reverse('api_pedido_nuevo'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn('obligatorio', res.json()['message'])

    def test_sin_items_falla(self):
        payload = self._base_payload(items=[])
        res = self.client.post(
            reverse('api_pedido_nuevo'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(res.status_code, 400)


class TC_PO_04_CrearDesdeNovia(CrearPedidoDesdeAPI):
    """TC-PO-04: Creación con novia_id — el pedido queda vinculado."""

    def test_pedido_vinculado_a_novia(self):
        payload = self._base_payload(
            cliente_nombre=self.novia.nombre,
            novia_id=self.novia.pk,
        )
        res = self.client.post(
            reverse('api_pedido_nuevo'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(res.status_code, 200)
        pedido = Pedido.objects.get(pk=res.json()['pedido_id'])
        self.assertEqual(pedido.novia, self.novia)


class TC_PO_05_CrearDesdeDama(CrearPedidoDesdeAPI):
    """TC-PO-05: Creación con dama_id — el ítem queda vinculado a la dama."""

    def test_item_vinculado_a_dama(self):
        payload = self._base_payload(
            cliente_nombre=self.dama.nombre,
            dama_id=self.dama.pk,
            novia_id=self.novia.pk,
        )
        res = self.client.post(
            reverse('api_pedido_nuevo'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(res.status_code, 200)
        pedido = Pedido.objects.get(pk=res.json()['pedido_id'])
        self.assertEqual(pedido.dama, self.dama)
        self.assertEqual(pedido.items.first().dama, self.dama)


class TC_PO_06_CrearDesdeCliente(CrearPedidoDesdeAPI):
    """TC-PO-06: Creación desde página de cliente existente."""

    def test_cliente_reutilizado(self):
        payload = self._base_payload(
            cliente_nombre=self.cliente.nombre,
            cliente_telefono=self.cliente.telefono,
        )
        count_before = Cliente.objects.count()
        res = self.client.post(
            reverse('api_pedido_nuevo'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(res.status_code, 200)
        # No se creó un segundo cliente con el mismo teléfono
        self.assertEqual(Cliente.objects.count(), count_before)
        pedido = Pedido.objects.get(pk=res.json()['pedido_id'])
        self.assertEqual(pedido.cliente, self.cliente)


class TC_PO_07_MultiItem(CrearPedidoDesdeAPI):
    """TC-PO-07: Pedido con múltiples ítems — precio total es la suma."""

    def test_multi_item_total(self):
        payload = self._base_payload(
            cliente_nombre='Multi-item Cliente',
            items=[
                {'tipo': 'VESTIDO', 'precio': '1500', 'cantidad': '1', 'talla': 'M'},
                {'tipo': 'ACCESORIO', 'precio': '300', 'cantidad': '2', 'talla': ''},
            ],
        )
        res = self.client.post(
            reverse('api_pedido_nuevo'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(res.status_code, 200)
        pedido = Pedido.objects.get(pk=res.json()['pedido_id'])
        self.assertEqual(pedido.items.count(), 2)
        self.assertEqual(float(pedido.precio), 2100.0)


class TC_PO_08_PedidoDetalleView(CrearPedidoDesdeAPI):
    """TC-PO-08: /pedidos/<pk>/ carga el detalle operativo."""

    def test_detalle_carga(self):
        payload = self._base_payload(
            cliente_nombre='Detalle Test',
            cliente_telefono='3310099001',
        )
        res = self.client.post(
            reverse('api_pedido_nuevo'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(res.status_code, 200)
        pedido_id = res.json()['pedido_id']
        res2 = self.client.get(reverse('pedido_detalle', args=[pedido_id]))
        self.assertEqual(res2.status_code, 200)
        self.assertTemplateUsed(res2, 'boutique/pedido_detalle.html')
        self.assertContains(res2, 'Detalle Test')

    def test_detalle_404_para_id_inexistente(self):
        res = self.client.get(reverse('pedido_detalle', args=[99999]))
        self.assertEqual(res.status_code, 404)


class TC_PO_09_CambiarEstadoItem(CrearPedidoDesdeAPI):
    """TC-PO-09: api_pedido_item_estado cambia el estado del ítem."""

    def test_cambiar_estado(self):
        pedido = Pedido.objects.create(precio=1000, creado_por=self.user)
        item = PedidoItem.objects.create(pedido=pedido, tipo='VESTIDO', precio=1000)
        self.assertEqual(item.estado, 'PENDIENTE')

        res = self.client.post(
            reverse('api_pedido_item_estado', args=[item.pk]),
            data=json.dumps({'estado': 'LLEGO'}),
            content_type='application/json',
        )
        self.assertEqual(res.status_code, 200)
        item.refresh_from_db()
        self.assertEqual(item.estado, 'LLEGO')
        self.assertIsNotNone(item.llego_en)

    def test_estado_invalido_rechazado(self):
        pedido = Pedido.objects.create(precio=1000, creado_por=self.user)
        item = PedidoItem.objects.create(pedido=pedido, tipo='VESTIDO', precio=1000)
        res = self.client.post(
            reverse('api_pedido_item_estado', args=[item.pk]),
            data=json.dumps({'estado': 'INVENTADO'}),
            content_type='application/json',
        )
        self.assertEqual(res.status_code, 400)


class TC_PO_10_EditarPedido(CrearPedidoDesdeAPI):
    """TC-PO-10: api_pedido_editar actualiza campos del pedido."""

    def test_editar_campos(self):
        pedido = Pedido.objects.create(precio=1000, creado_por=self.user, notas='original')
        res = self.client.post(
            reverse('api_pedido_editar', args=[pedido.pk]),
            data=json.dumps({'notas': 'actualizado', 'precio': '1500'}),
            content_type='application/json',
        )
        self.assertEqual(res.status_code, 200)
        pedido.refresh_from_db()
        self.assertEqual(pedido.notas, 'actualizado')
        self.assertEqual(float(pedido.precio), 1500.0)


class TC_PO_11_PedidoListaTodosLosTipos(CrearPedidoDesdeAPI):
    """TC-PO-11: La lista de pedidos muestra todos los tipos."""

    def test_todos_tipos_visibles(self):
        tipos = ['HECHURA', 'PEDIDO_EXTERNO', 'ESTANDAR_GRUPO', 'SOBRE_PEDIDO']
        for tipo in tipos:
            Pedido.objects.create(
                precio=100, tipo_pedido=tipo, creado_por=self.user,
                estado='NUEVO',
            )
        res = self.client.get(reverse('pedidos_en_puerta'))
        self.assertEqual(res.status_code, 200)
        # Todos los tipos deben aparecer en el contexto
        for tipo in tipos:
            self.assertIn(tipo, res.context['pedidos_por_tipo'])


class TC_PO_12_AnticipoCreaTicket(CrearPedidoDesdeAPI):
    """TC-PO-12: Al crear pedido con anticipo, se genera ticket."""

    def test_ticket_generado(self):
        payload = self._base_payload(
            cliente_nombre='Con Anticipo',
            anticipo=500,
            metodo_pago='EFECTIVO',
        )
        res = self.client.post(
            reverse('api_pedido_nuevo'),
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(res.status_code, 200)
        pedido = Pedido.objects.get(pk=res.json()['pedido_id'])
        self.assertIsNotNone(pedido.ticket)
        self.assertEqual(pedido.ticket.cliente_nombre, 'Con Anticipo')
