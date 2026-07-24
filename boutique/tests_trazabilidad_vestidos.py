"""
Tests de trazabilidad de vestidos de damas y expediente editable de medidas.
13 casos obligatorios según la especificación.
"""
import json
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User, Group
from django.utils import timezone
from boutique.models import (
    Novia, Dama, Color, Tela, Modelo, CorteCaja,
    MedidasDama, VestidoDama, MovimientoVestido,
    Pedido, Cliente,
)


def _make_usuario():
    u = User.objects.create_user(username='tester_traza', password='pass')
    Group.objects.get_or_create(name='Vendedor')[0].user_set.add(u)
    return u


def _setup_caja(user):
    return CorteCaja.objects.create(abierto_por=user, monto_apertura=1000, cerrado=False)


def _make_novia(nombre='Novia Test'):
    return Novia.objects.create(nombre=nombre, fecha_boda='2027-01-01')


def _make_dama(novia, nombre='Dama Test'):
    return Dama.objects.create(novia=novia, nombre=nombre)


def _make_vestido(dama, **kwargs):
    defaults = dict(tipo='ESPECIAL', talla='M', precio=3000)
    defaults.update(kwargs)
    return VestidoDama.objects.create(
        dama=dama,
        creado_por=dama.novia.creado_por if hasattr(dama.novia, 'creado_por') else User.objects.first(),
        **defaults
    )


class BaseTraza(TestCase):
    def setUp(self):
        self.user = _make_usuario()
        _setup_caja(self.user)
        self.novia = _make_novia()
        self.dama = _make_dama(self.novia)
        self.client.login(username='tester_traza', password='pass')
        session = self.client.session
        session['active_profile_id'] = self.user.id
        session.save()


# ──────────────────────────────────────────────────────────────────────────────
# TC-T-01  Registrar medidas por primera vez
# ──────────────────────────────────────────────────────────────────────────────
class TC_T_01_RegistrarMedidasPorPrimeraVez(BaseTraza):

    def test_primera_vez_crea_registro_vigente(self):
        """Registrar medidas donde no hay ninguna → crea MedidasDama vigente."""
        self.assertEqual(self.dama.medidas_registradas.count(), 0)
        payload = {'busto': 90.0, 'cintura': 68.0, 'cadera': 96.0, 'notas': 'Primera toma'}
        r = self.client.post(
            reverse('api_medidas_dama', kwargs={'pk': self.dama.pk}),
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(r.status_code, 200, r.content)
        data = r.json()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['accion'], 'creada')

        m = MedidasDama.objects.get(dama=self.dama, vigente=True)
        self.assertEqual(float(m.busto), 90.0)
        self.assertEqual(float(m.cintura), 68.0)
        self.assertTrue(m.vigente)


# ──────────────────────────────────────────────────────────────────────────────
# TC-T-02  Editar medidas — datos precargados y actualización in-place
# ──────────────────────────────────────────────────────────────────────────────
class TC_T_02_EditarMedidasConPrecarga(BaseTraza):

    def setUp(self):
        super().setUp()
        self.medidas = MedidasDama.objects.create(
            dama=self.dama, vigente=True,
            busto=88.0, cintura=65.0, cadera=94.0,
            registrado_por=self.user
        )

    def test_get_devuelve_medidas_vigentes(self):
        """GET /api/dama/<pk>/medidas/ devuelve la versión vigente con datos."""
        r = self.client.get(reverse('api_medidas_dama', kwargs={'pk': self.dama.pk}))
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIsNotNone(data['medidas'])
        self.assertEqual(float(data['medidas']['busto']), 88.0)
        self.assertTrue(data['medidas']['vigente'])

    def test_post_actualiza_in_place_sin_nueva_version(self):
        """POST sin nueva_version=True actualiza la versión vigente existente."""
        payload = {'busto': 91.0, 'cintura': 67.0, 'nueva_version': False}
        r = self.client.post(
            reverse('api_medidas_dama', kwargs={'pk': self.dama.pk}),
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['accion'], 'actualizada')

        # Sigue siendo una sola versión vigente
        self.assertEqual(MedidasDama.objects.filter(dama=self.dama, vigente=True).count(), 1)
        self.medidas.refresh_from_db()
        self.assertEqual(float(self.medidas.busto), 91.0)


# ──────────────────────────────────────────────────────────────────────────────
# TC-T-03  Consultar medidas sin editar — siempre versión vigente
# ──────────────────────────────────────────────────────────────────────────────
class TC_T_03_ConsultarMedidasSinEditar(BaseTraza):

    def setUp(self):
        super().setUp()
        MedidasDama.objects.create(dama=self.dama, vigente=False, busto=80.0)  # histórica
        MedidasDama.objects.create(dama=self.dama, vigente=True, busto=90.0)   # vigente

    def test_get_devuelve_solo_vigente(self):
        r = self.client.get(reverse('api_medidas_dama', kwargs={'pk': self.dama.pk}))
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(float(data['medidas']['busto']), 90.0)  # la vigente, no la histórica
        self.assertTrue(data['medidas']['vigente'])


# ──────────────────────────────────────────────────────────────────────────────
# TC-T-04  Conservar historial de medidas
# ──────────────────────────────────────────────────────────────────────────────
class TC_T_04_HistorialMedidas(BaseTraza):

    def setUp(self):
        super().setUp()
        MedidasDama.objects.create(dama=self.dama, vigente=False, busto=80.0, notas='Versión 1')
        MedidasDama.objects.create(dama=self.dama, vigente=True, busto=88.0, notas='Versión 2')

    def test_historial_contiene_todas_las_versiones(self):
        r = self.client.get(reverse('api_medidas_dama_historial', kwargs={'pk': self.dama.pk}))
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data['total'], 2)

    def test_nueva_version_archiva_anterior(self):
        """POST con nueva_version=True archiva la anterior y crea nueva vigente."""
        payload = {'busto': 95.0, 'nueva_version': True, 'notas': 'Prueba de vestido'}
        r = self.client.post(
            reverse('api_medidas_dama', kwargs={'pk': self.dama.pk}),
            data=json.dumps(payload), content_type='application/json'
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['accion'], 'creada')

        # Ahora hay 3 versiones; solo 1 vigente
        self.assertEqual(MedidasDama.objects.filter(dama=self.dama).count(), 3)
        self.assertEqual(MedidasDama.objects.filter(dama=self.dama, vigente=True).count(), 1)
        vigente = MedidasDama.objects.get(dama=self.dama, vigente=True)
        self.assertEqual(float(vigente.busto), 95.0)


# ──────────────────────────────────────────────────────────────────────────────
# TC-T-05  Crear modelo especial (VestidoDama)
# ──────────────────────────────────────────────────────────────────────────────
class TC_T_05_CrearModeloEspecial(BaseTraza):

    def test_crear_vestido_dama_via_api(self):
        color, _ = Color.objects.get_or_create(nombre='Ivory')
        tela, _ = Tela.objects.get_or_create(nombre='Satén', codigo_proveedor='SA')
        payload = {
            'tipo': 'ESPECIAL',
            'color_nombre': 'Ivory',
            'tela_nombre': 'Satén',
            'talla': 'M',
            'precio': 4500,
            'numero_modelo': 'M-2026-05',
            'descripcion_especial': 'Vestido de satén con encaje en espalda',
        }
        r = self.client.post(
            reverse('api_crear_vestido_dama', kwargs={'pk': self.dama.pk}),
            data=json.dumps(payload), content_type='application/json'
        )
        self.assertEqual(r.status_code, 200, r.content)
        data = r.json()
        self.assertEqual(data['status'], 'ok')
        vestido = VestidoDama.objects.get(pk=data['vestido']['id'])
        self.assertEqual(vestido.tipo, 'ESPECIAL')
        self.assertEqual(vestido.numero_modelo, 'M-2026-05')
        self.assertEqual(vestido.dama, self.dama)


# ──────────────────────────────────────────────────────────────────────────────
# TC-T-06  Código único generado al crear
# ──────────────────────────────────────────────────────────────────────────────
class TC_T_06_CodigoUnico(BaseTraza):

    def test_vestido_tiene_codigo_al_crear(self):
        vestido = VestidoDama.objects.create(
            dama=self.dama, tipo='HECHURA', precio=2000,
            creado_por=self.user
        )
        self.assertTrue(vestido.codigo.startswith('VD-'))
        self.assertGreater(len(vestido.codigo), 5)

    def test_dos_vestidos_tienen_codigos_diferentes(self):
        dama2 = _make_dama(self.novia, 'Dama B')
        v1 = VestidoDama.objects.create(dama=self.dama, tipo='ESPECIAL', precio=1000, creado_por=self.user)
        v2 = VestidoDama.objects.create(dama=dama2, tipo='CATALOGO', precio=2000, creado_por=self.user)
        self.assertNotEqual(v1.codigo, v2.codigo)


# ──────────────────────────────────────────────────────────────────────────────
# TC-T-07  Marcar llegada a tienda — solo una entrada permitida
# ──────────────────────────────────────────────────────────────────────────────
class TC_T_07_LlegadaTiendaUnaEntrada(BaseTraza):

    def setUp(self):
        super().setUp()
        self.vestido = VestidoDama.objects.create(
            dama=self.dama, tipo='ESPECIAL', precio=3000, creado_por=self.user
        )

    def test_primera_llegada_crea_entrada_y_reserva(self):
        r = self.client.post(
            reverse('api_vestido_llegada', kwargs={'pk': self.vestido.pk}),
            data=json.dumps({}), content_type='application/json'
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.vestido.refresh_from_db()
        self.assertEqual(self.vestido.estado, 'RESERVADO')
        self.assertEqual(self.vestido.movimientos_vestido.filter(tipo='ENTRADA').count(), 1)
        self.assertEqual(self.vestido.movimientos_vestido.filter(tipo='RESERVA').count(), 1)

    def test_segunda_llegada_rechazada(self):
        # Primera llegada
        MovimientoVestido.objects.create(vestido=self.vestido, tipo='ENTRADA', cantidad=1, usuario=self.user)
        self.vestido.estado = 'RESERVADO'
        self.vestido.save(update_fields=['estado'])

        # Segunda llegada debe fallar
        r = self.client.post(
            reverse('api_vestido_llegada', kwargs={'pk': self.vestido.pk}),
            data=json.dumps({}), content_type='application/json'
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn('doble entrada', r.json()['message'].lower())


# ──────────────────────────────────────────────────────────────────────────────
# TC-T-08  Reservar el vestido para la dama
# ──────────────────────────────────────────────────────────────────────────────
class TC_T_08_ReservaVestido(BaseTraza):

    def test_llegada_crea_reserva_automatica(self):
        """Al marcar llegada, el sistema crea ENTRADA + RESERVA vinculados a la dama."""
        vestido = VestidoDama.objects.create(
            dama=self.dama, tipo='CATALOGO', precio=2500, creado_por=self.user
        )
        self.client.post(
            reverse('api_vestido_llegada', kwargs={'pk': vestido.pk}),
            data=json.dumps({}), content_type='application/json'
        )
        reserva = vestido.movimientos_vestido.filter(tipo='RESERVA').first()
        self.assertIsNotNone(reserva)
        self.assertIn(self.dama.nombre, reserva.notas)


# ──────────────────────────────────────────────────────────────────────────────
# TC-T-09  Entregar vestido — genera salida; impide doble salida
# ──────────────────────────────────────────────────────────────────────────────
class TC_T_09_EntregarVestido(BaseTraza):

    def setUp(self):
        super().setUp()
        self.vestido = VestidoDama.objects.create(
            dama=self.dama, tipo='ESPECIAL', precio=3000,
            estado='RESERVADO', creado_por=self.user
        )
        MovimientoVestido.objects.create(vestido=self.vestido, tipo='ENTRADA', cantidad=1, usuario=self.user)
        MovimientoVestido.objects.create(vestido=self.vestido, tipo='RESERVA', cantidad=1, usuario=self.user)

    def test_entrega_crea_salida_y_cambia_estado(self):
        r = self.client.post(
            reverse('api_vestido_entregar', kwargs={'pk': self.vestido.pk}),
            data=json.dumps({}), content_type='application/json'
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.vestido.refresh_from_db()
        self.assertEqual(self.vestido.estado, 'ENTREGADO')
        self.assertEqual(self.vestido.movimientos_vestido.filter(tipo='SALIDA').count(), 1)

    def test_doble_entrega_rechazada(self):
        # Primera entrega
        MovimientoVestido.objects.create(vestido=self.vestido, tipo='SALIDA', cantidad=1, usuario=self.user)
        self.vestido.estado = 'ENTREGADO'
        self.vestido.save(update_fields=['estado'])

        r = self.client.post(
            reverse('api_vestido_entregar', kwargs={'pk': self.vestido.pk}),
            data=json.dumps({}), content_type='application/json'
        )
        self.assertEqual(r.status_code, 400)


# ──────────────────────────────────────────────────────────────────────────────
# TC-T-10  Ticket de pedido muestra modelo/color/talla/tela
# ──────────────────────────────────────────────────────────────────────────────
class TC_T_10_TicketMuestraDatosVestido(BaseTraza):

    def test_populate_from_obj_con_vestido_dama(self):
        """Ticket.populate_from_obj genera items con datos del VestidoDama."""
        from boutique.models import Ticket, Pedido as PedidoModel
        color, _ = Color.objects.get_or_create(nombre='Rosa')
        tela, _ = Tela.objects.get_or_create(nombre='Chiffon', codigo_proveedor='CH')
        modelo, _ = Modelo.objects.get_or_create(nombre='Valencia')
        cliente = Cliente.objects.create(nombre='Ana Test', telefono='5550001234')

        pedido = PedidoModel.objects.create(
            novia=self.novia,
            dama=self.dama,
            cliente=cliente,
            modelo=modelo, color=color, tela=tela, talla='S',
            precio=4000, anticipo=0,
            tipo_pedido='ESTANDAR_GRUPO', estado='NUEVO',
            creado_por=self.user
        )
        VestidoDama.objects.create(
            dama=self.dama, pedido=pedido, tipo='CATALOGO',
            modelo=modelo, color=color, tela=tela, talla='S', precio=4000,
            numero_modelo='VAL-001', creado_por=self.user
        )

        ticket = Ticket.objects.create(
            tipo='PEDIDO', pedido=pedido, novia=self.novia,
            cliente_nombre=cliente.nombre,
            total=4000, total_pagado=0,
            cajero_nombre=self.user.username,
            caja=CorteCaja.objects.filter(cerrado=False).first()
        )
        ticket.populate_from_obj(pedido)
        ticket.refresh_from_db()

        snap = ticket.snapshot_json
        self.assertGreater(len(snap.get('items', [])), 0)
        item = snap['items'][0]
        self.assertEqual(item['modelo'], 'Valencia')
        self.assertEqual(item['color'], 'Rosa')
        self.assertEqual(item['talla'], 'S')
        self.assertEqual(item['tela'], 'Chiffon')
        self.assertEqual(item['sku'], ticket.snapshot_json['vestido']['codigo'])

    def test_pedido_sin_vestido_dama_genera_item_sintetico(self):
        """Pedido sin VestidoDama asignado genera un ítem sintético desde sus campos."""
        from boutique.models import Ticket, Pedido as PedidoModel
        color, _ = Color.objects.get_or_create(nombre='Azul')
        modelo, _ = Modelo.objects.get_or_create(nombre='Atenas')
        cliente = Cliente.objects.create(nombre='Beta Test', telefono='5550005678')

        pedido = PedidoModel.objects.create(
            novia=self.novia, dama=self.dama, cliente=cliente,
            modelo=modelo, color=color, talla='L', precio=3500, anticipo=0,
            tipo_pedido='ESTANDAR_GRUPO', estado='NUEVO', creado_por=self.user
        )
        ticket = Ticket.objects.create(
            tipo='PEDIDO', pedido=pedido, novia=self.novia,
            cliente_nombre=cliente.nombre,
            total=3500, total_pagado=0,
            cajero_nombre=self.user.username,
            caja=CorteCaja.objects.filter(cerrado=False).first()
        )
        ticket.populate_from_obj(pedido)
        ticket.refresh_from_db()

        snap = ticket.snapshot_json
        self.assertGreater(len(snap.get('items', [])), 0)
        item = snap['items'][0]
        self.assertEqual(item['color'], 'Azul')


# ──────────────────────────────────────────────────────────────────────────────
# TC-T-11  Etiqueta: código incluido en el snapshot del vestido
# ──────────────────────────────────────────────────────────────────────────────
class TC_T_11_EtiquetaConCodigo(BaseTraza):

    def test_vestido_codigo_persiste_y_es_estable(self):
        """El código del vestido no cambia entre la creación, llegada y entrega."""
        vestido = VestidoDama.objects.create(
            dama=self.dama, tipo='ESPECIAL', precio=2800, creado_por=self.user
        )
        codigo_original = vestido.codigo
        self.assertTrue(codigo_original.startswith('VD-'))

        # Marcar llegada
        MovimientoVestido.objects.create(vestido=vestido, tipo='ENTRADA', cantidad=1, usuario=self.user)
        vestido.estado = 'RESERVADO'
        vestido.save(update_fields=['estado'])
        vestido.refresh_from_db()
        self.assertEqual(vestido.codigo, codigo_original)  # código no cambia

        # Marcar entrega
        MovimientoVestido.objects.create(vestido=vestido, tipo='SALIDA', cantidad=1, usuario=self.user)
        vestido.estado = 'ENTREGADO'
        vestido.save(update_fields=['estado'])
        vestido.refresh_from_db()
        self.assertEqual(vestido.codigo, codigo_original)  # código sigue igual


# ──────────────────────────────────────────────────────────────────────────────
# TC-T-12  Mismo código en todo el recorrido (pedido → ficha → ticket)
# ──────────────────────────────────────────────────────────────────────────────
class TC_T_12_MismoCodigoEnRecorrido(BaseTraza):

    def test_codigo_presente_en_ticket_snapshot(self):
        from boutique.models import Ticket, Pedido as PedidoModel
        color, _ = Color.objects.get_or_create(nombre='Champagne')
        cliente = Cliente.objects.create(nombre='Gamma Test', telefono='5550009999')

        pedido = PedidoModel.objects.create(
            novia=self.novia, dama=self.dama, cliente=cliente,
            color=color, talla='XS', precio=5000, anticipo=0,
            tipo_pedido='ESTANDAR_GRUPO', estado='NUEVO', creado_por=self.user
        )
        vestido = VestidoDama.objects.create(
            dama=self.dama, pedido=pedido, tipo='ESPECIAL',
            color=color, talla='XS', precio=5000, creado_por=self.user
        )
        codigo = vestido.codigo

        ticket = Ticket.objects.create(
            tipo='PEDIDO', pedido=pedido, novia=self.novia,
            cliente_nombre=cliente.nombre,
            total=5000, total_pagado=0,
            cajero_nombre=self.user.username,
            caja=CorteCaja.objects.filter(cerrado=False).first()
        )
        ticket.populate_from_obj(pedido)
        ticket.refresh_from_db()

        snap = ticket.snapshot_json
        # El código del vestido debe aparecer en el snapshot del vestido y en items
        self.assertEqual(snap.get('vestido', {}).get('codigo'), codigo)
        if snap.get('items'):
            self.assertEqual(snap['items'][0].get('sku'), codigo)


# ──────────────────────────────────────────────────────────────────────────────
# TC-T-13  Existencia calculada por movimientos (no por campo directo)
# ──────────────────────────────────────────────────────────────────────────────
class TC_T_13_ExistenciaPorMovimientos(BaseTraza):

    def setUp(self):
        super().setUp()
        self.vestido = VestidoDama.objects.create(
            dama=self.dama, tipo='ESPECIAL', precio=3000, creado_por=self.user
        )

    def test_sin_movimientos_existencia_es_cero(self):
        self.assertEqual(self.vestido.existencia_fisica, 0)
        self.assertEqual(self.vestido.disponible, 0)

    def test_entrada_aumenta_existencia(self):
        MovimientoVestido.objects.create(vestido=self.vestido, tipo='ENTRADA', cantidad=1, usuario=self.user)
        self.assertEqual(self.vestido.existencia_fisica, 1)

    def test_reserva_reduce_disponible_sin_afectar_existencia_fisica(self):
        MovimientoVestido.objects.create(vestido=self.vestido, tipo='ENTRADA', cantidad=1, usuario=self.user)
        MovimientoVestido.objects.create(vestido=self.vestido, tipo='RESERVA', cantidad=1, usuario=self.user)
        self.assertEqual(self.vestido.existencia_fisica, 1)
        self.assertEqual(self.vestido.disponible, 0)  # reservado = no disponible

    def test_salida_reduce_existencia_fisica(self):
        MovimientoVestido.objects.create(vestido=self.vestido, tipo='ENTRADA', cantidad=1, usuario=self.user)
        MovimientoVestido.objects.create(vestido=self.vestido, tipo='SALIDA', cantidad=1, usuario=self.user)
        self.assertEqual(self.vestido.existencia_fisica, 0)

    def test_devolucion_aumenta_existencia(self):
        MovimientoVestido.objects.create(vestido=self.vestido, tipo='ENTRADA', cantidad=1, usuario=self.user)
        MovimientoVestido.objects.create(vestido=self.vestido, tipo='SALIDA', cantidad=1, usuario=self.user)
        MovimientoVestido.objects.create(vestido=self.vestido, tipo='DEVOLUCION', cantidad=1, usuario=self.user)
        self.assertEqual(self.vestido.existencia_fisica, 1)
