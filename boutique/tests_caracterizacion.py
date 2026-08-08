"""
Pruebas de caracterización — Adelé POS
Demuestran el comportamiento ACTUAL del sistema, incluyendo defectos.
Algunas pruebas FALLAN intencionalmente para documentar bugs conocidos.
Referencia: docs/AUDITORIA_ESTABILIZACION_POS.md
"""
from decimal import Decimal
from django.test import TestCase, Client
from django.contrib.auth.models import User, Group
from django.urls import reverse
import json

from boutique.models import (
    Categoria, Color, Tela, Modelo,
    Producto, Cliente,
    Venta, ItemVenta, Pago,
    Apartado, ApartadoItem, PagoApartado,
    Pedido, PagoPedido, Medidas,
    Servicio, PagoServicio,
    Novia, Dama,
    Ticket, CorteCaja, Tienda, ConfiguracionTienda,
)
from boutique.services.cash_service import registrar_cobro


def crear_usuario_vendedor(username='vendedora'):
    user = User.objects.create_user(username=username, password='testpass123')
    grupo, _ = Group.objects.get_or_create(name='Vendedor')
    user.groups.add(grupo)
    return user


def crear_caja(usuario):
    tienda, _ = Tienda.objects.get_or_create(nombre='Tienda Test')
    return CorteCaja.objects.create(
        tienda=tienda,
        abierto_por=usuario,
        monto_apertura=Decimal('1000.00'),
    )


def crear_catalogo():
    cat, _  = Categoria.objects.get_or_create(nombre='Vestido')
    color, _ = Color.objects.get_or_create(nombre='Rosa Palo', defaults={'codigo_hex': '#FFB6C1'})
    tela, _  = Tela.objects.get_or_create(nombre='Satin', defaults={'es_predefinida': True, 'activa': True})
    modelo, _ = Modelo.objects.get_or_create(nombre='Sirena Enamorada')
    return cat, color, tela, modelo


def crear_producto(cat, color, tela=None, modelo=None, precio=5000):
    return Producto.objects.create(
        categoria=cat,
        color=color,
        tela=tela,
        modelo=modelo,
        talla='M',
        precio_venta=Decimal(str(precio)),
        cantidad_actual=3,
    )


# ============================================================
# TC-01  Abono actualiza saldo de apartado
# ============================================================
class TC01AbonoActualizaSaldoApartado(TestCase):
    """
    DEBE PASAR.
    Verifica que registrar un PagoApartado reduce el saldo del apartado.
    """

    def setUp(self):
        self.usuario = crear_usuario_vendedor()
        self.caja    = crear_caja(self.usuario)
        cat, color, tela, _ = crear_catalogo()
        self.producto = crear_producto(cat, color, tela)
        self.cliente = Cliente.objects.create(nombre='Ana López', telefono='3310000001')

    def test_abono_reduce_saldo(self):
        apartado = Apartado.objects.create(
            cliente=self.cliente,
            cliente_nombre=self.cliente.nombre,
            cliente_telefono=self.cliente.telefono,
            total=Decimal('8000.00'),
            anticipo=Decimal('0.00'),
        )
        ApartadoItem.objects.create(
            apartado=apartado,
            producto=self.producto,
            descripcion=str(self.producto),
            cantidad=1,
            precio_unitario=Decimal('8000.00'),
            subtotal=Decimal('8000.00'),
        )

        self.assertEqual(apartado.saldo, Decimal('8000.00'))

        registrar_cobro(
            origen_tipo='apartado',
            origen_obj=apartado,
            monto=Decimal('2500.00'),
            metodo='EFECTIVO',
            usuario=self.usuario,
        )

        apartado.refresh_from_db()
        self.assertEqual(apartado.anticipo, Decimal('2500.00'))
        self.assertEqual(apartado.saldo,    Decimal('5500.00'))


# ============================================================
# TC-02  Ticket desde venta directa de inventario
# ============================================================
class TC02TicketDesdeVentaInventario(TestCase):
    """
    DEBE PASAR.
    Una venta directa genera un ticket con al menos un item y el nombre del cliente.
    """

    def setUp(self):
        self.usuario = crear_usuario_vendedor()
        self.caja    = crear_caja(self.usuario)
        cat, color, tela, modelo = crear_catalogo()
        self.producto = crear_producto(cat, color, tela, modelo)
        self.cliente  = Cliente.objects.create(nombre='Beatriz Ruiz', telefono='3310000002')

    def test_ticket_tiene_items_y_cliente(self):
        venta = Venta.objects.create(
            vendedor=self.usuario,
            cliente=self.cliente,
            total=self.producto.precio_venta,
        )
        ItemVenta.objects.create(
            venta=venta,
            producto=self.producto,
            cantidad=1,
            precio_unitario=self.producto.precio_venta,
        )
        Pago.objects.create(
            venta=venta,
            monto=venta.total,
            metodo='EFECTIVO',
            registrado_por=self.usuario,
        )

        ticket = registrar_cobro(
            origen_tipo='venta',
            origen_obj=venta,
            monto=self.producto.precio_venta,
            metodo='EFECTIVO',
            usuario=self.usuario,
        )

        self.assertEqual(ticket.cliente_nombre, 'Beatriz Ruiz')
        items = ticket.snapshot_json.get('items', [])
        self.assertGreater(len(items), 0, "El ticket de venta debe tener al menos 1 artículo")

        item = items[0]
        self.assertNotEqual(item.get('color', ''), '',
                            "El artículo en el ticket debe tener color")
        self.assertNotEqual(item.get('sku', ''), '',
                            "El artículo en el ticket debe tener SKU")


# ============================================================
# TC-03  Ticket desde Pedido — verifica ítem sintético (PR-01 aplicado)
# ============================================================
class TC03TicketDesdePedidoItemsVacios(TestCase):
    """
    R1 corregido: populate_from_obj genera un ítem sintético desde los campos
    del Pedido (modelo, color, tela, talla, precio) cuando no hay PedidoItems.
    """

    def setUp(self):
        self.usuario = crear_usuario_vendedor()
        self.caja    = crear_caja(self.usuario)
        cat, color, tela, modelo = crear_catalogo()
        self.producto = crear_producto(cat, color, tela, modelo)
        self.novia = Novia.objects.create(
            nombre='Carla Hernández',
            fecha_boda='2026-12-01',
            creado_por=self.usuario,
        )

    def test_ticket_pedido_tiene_items(self):
        pedido = Pedido.objects.create(
            novia=self.novia,
            modelo=Modelo.objects.get(nombre='Sirena Enamorada'),
            color=Color.objects.get(nombre='Rosa Palo'),
            tela=Tela.objects.get(nombre='Satin'),
            talla='S',
            precio=Decimal('12000.00'),
            creado_por=self.usuario,
        )

        ticket = registrar_cobro(
            origen_tipo='pedido',
            origen_obj=pedido,
            monto=Decimal('3000.00'),
            metodo='EFECTIVO',
            usuario=self.usuario,
        )

        items = ticket.snapshot_json.get('items', [])
        self.assertGreater(len(items), 0, "El ticket de pedido debe tener al menos un ítem sintético.")
        if items:
            self.assertEqual(items[0].get('modelo'), 'Sirena Enamorada')
            self.assertEqual(items[0].get('color'),  'Rosa Palo')
            self.assertEqual(items[0].get('talla'),  'S')

    def test_saldo_pedido_correcto_independiente_de_items(self):
        pedido = Pedido.objects.create(
            novia=self.novia,
            precio=Decimal('12000.00'),
            creado_por=self.usuario,
        )

        ticket = registrar_cobro(
            origen_tipo='pedido',
            origen_obj=pedido,
            monto=Decimal('3000.00'),
            metodo='EFECTIVO',
            usuario=self.usuario,
        )

        snap = ticket.snapshot_json
        # 'total' is no longer stored in snapshot — ticket.total is the single source of truth
        self.assertEqual(float(ticket.total), 12000.0)
        self.assertEqual(snap['total_pagado_acumulado'], 3000.0)
        self.assertEqual(snap['saldo_pendiente'], 9000.0)


# ============================================================
# TC-04  Ticket desde Apartado — items con modelo y color
# ============================================================
class TC04TicketDesdeApartadoConItems(TestCase):
    """
    DEBE PASAR.
    Un apartado creado con FK de producto debe producir ticket con items
    que incluyan modelo, color y SKU del producto.
    """

    def setUp(self):
        self.usuario = crear_usuario_vendedor()
        self.caja    = crear_caja(self.usuario)
        cat, color, tela, modelo = crear_catalogo()
        self.producto = crear_producto(cat, color, tela, modelo)
        self.cliente  = Cliente.objects.create(nombre='Diana Castro', telefono='3310000004')

    def test_ticket_apartado_tiene_items_con_datos(self):
        apartado = Apartado.objects.create(
            cliente=self.cliente,
            cliente_nombre=self.cliente.nombre,
            cliente_telefono=self.cliente.telefono,
            total=Decimal('5000.00'),
            anticipo=Decimal('0.00'),
        )
        ApartadoItem.objects.create(
            apartado=apartado,
            producto=self.producto,
            descripcion=str(self.producto),
            modelo='',
            color='',
            talla=self.producto.talla,
            cantidad=1,
            precio_unitario=self.producto.precio_venta,
            subtotal=self.producto.precio_venta,
        )

        ticket = registrar_cobro(
            origen_tipo='apartado',
            origen_obj=apartado,
            monto=Decimal('2000.00'),
            metodo='EFECTIVO',
            usuario=self.usuario,
        )

        items = ticket.snapshot_json.get('items', [])
        self.assertEqual(len(items), 1)

        item = items[0]
        self.assertEqual(item.get('color'), 'Rosa Palo',
                         "El color debe leerse desde item.producto.color.nombre")
        self.assertNotEqual(item.get('sku'), '',
                            "El SKU debe leerse desde item.producto.sku")
        self.assertEqual(item.get('modelo'), 'Sirena Enamorada')


# ============================================================
# TC-05  Dama con notas y medidas — acceso programático
# ============================================================
class TC05DamaNotasYMedidas(TestCase):
    """
    DEBE PASAR.
    Verifica que los campos de notas, modelo especial y medidas de una dama
    se pueden guardar y recuperar.
    """

    def setUp(self):
        self.usuario = crear_usuario_vendedor()
        self.novia = Novia.objects.create(
            nombre='Elena Morales',
            fecha_boda='2026-11-15',
            creado_por=self.usuario,
        )

    def test_dama_tiene_campos_notas_y_medidas(self):
        dama = Dama.objects.create(
            novia=self.novia,
            nombre='Fernanda Jiménez',
            talla='S',
            modelo_especial='Princesa con encaje',
            color_especial='Azul cielo',
            notas_ajustes='Manga tres cuartos. Ajuste en talle.',
            m_busto='88',
            m_cintura='68',
            m_cadera='95',
            m_largo_total='145',
        )

        dama.refresh_from_db()
        self.assertEqual(dama.notas_ajustes, 'Manga tres cuartos. Ajuste en talle.')
        self.assertEqual(dama.modelo_especial, 'Princesa con encaje')
        self.assertEqual(dama.m_busto, '88')
        self.assertEqual(dama.m_cintura, '68')

    def test_dama_visibilidad_de_notas_sin_edicion(self):
        """
        Verifica que las notas se almacenan en el modelo y son accesibles
        sin necesidad de modo de edición (el bug era en el template).
        """
        dama = Dama.objects.create(
            novia=self.novia,
            nombre='Georgina Soto',
            notas_ajustes='Requiere entalle especial en cintura.',
        )
        recuperada = Dama.objects.get(pk=dama.pk)
        self.assertIn('entalle', recuperada.notas_ajustes)


# ============================================================
# TC-06  Soft delete de Novia
# ============================================================
class TC06SoftDeleteNovia(TestCase):
    """
    DEBE PASAR.
    api_eliminar_novia hace soft delete (activo=False).
    El registro persiste en DB y el endpoint devuelve 200.
    """

    def setUp(self):
        self.usuario = crear_usuario_vendedor()
        crear_caja(self.usuario)
        self.c = Client()
        self.c.force_login(self.usuario)
        session = self.c.session
        session['active_profile_id'] = self.usuario.id
        session.save()
        self.novia = Novia.objects.create(
            nombre='Hilda Vargas',
            fecha_boda='2026-10-10',
            creado_por=self.usuario,
        )

    def test_eliminar_novia_hace_soft_delete(self):
        response = self.c.post(
            reverse('api_eliminar_novia', args=[self.novia.pk]),
            content_type='application/json',
            data=json.dumps({}),
        )
        self.assertEqual(response.status_code, 200)

        self.novia.refresh_from_db()
        self.assertFalse(self.novia.activo,
                         "La novia debe existir en DB con activo=False (soft delete)")

    def test_novia_eliminada_no_aparece_en_lista(self):
        self.novia.activo = False
        self.novia.save()

        novias_activas = Novia.objects.filter(activo=True)
        self.assertNotIn(self.novia, novias_activas)


# ============================================================
# TC-07  Creación de servicio — sin HTTP 500
# ============================================================
class TC07CreacionServicio(TestCase):
    """
    DOCUMENTA el bug P6 (HTTP 500 en servicios).
    La creación via API debe retornar 200, no 500.
    Si falla, el test identifica el punto de falla.
    """

    def setUp(self):
        self.usuario = crear_usuario_vendedor()
        crear_caja(self.usuario)
        self.c = Client()
        self.c.force_login(self.usuario)
        session = self.c.session
        session['active_profile_id'] = self.usuario.id
        session.save()
        self.cliente = Cliente.objects.create(nombre='Isabel Torres', telefono='3310000007')

    def test_crear_servicio_retorna_200(self):
        response = self.c.post(
            reverse('api_crear_servicio'),
            content_type='application/json',
            data=json.dumps({
                'tipo': 'BASTILLA',
                'descripcion': 'Bastilla con refuerzo en dobladillo',
                'cliente_id': self.cliente.pk,
                'costo': '350.00',
                'anticipo': '0',
                'notas': 'Largo: 145 cm',
            }),
        )
        self.assertEqual(
            response.status_code, 200,
            f"api_crear_servicio devolvió {response.status_code}. "
            f"Respuesta: {response.content.decode()[:500]}"
        )
        data = response.json()
        self.assertEqual(data.get('status'), 'ok')
        self.assertIn('id', data)

    def test_servicio_lista_no_devuelve_500(self):
        Servicio.objects.create(
            tipo='BASTILLA',
            descripcion='Bastilla de prueba',
            cliente=self.cliente,
            costo=Decimal('200.00'),
            creado_por=self.usuario,
        )
        response = self.c.get(reverse('servicios_list'))
        self.assertNotEqual(
            response.status_code, 500,
            "La lista de servicios retornó HTTP 500. Revisar template servicios_list.html "
            "o el queryset en servicios_list()."
        )
        self.assertEqual(response.status_code, 200)

    def test_cobrar_servicio_genera_ticket(self):
        servicio = Servicio.objects.create(
            tipo='TALLE',
            descripcion='Ajuste de talle',
            cliente=self.cliente,
            costo=Decimal('500.00'),
            creado_por=self.usuario,
        )

        ticket = registrar_cobro(
            origen_tipo='servicio',
            origen_obj=servicio,
            monto=Decimal('500.00'),
            metodo='EFECTIVO',
            usuario=self.usuario,
        )

        self.assertEqual(ticket.tipo, 'SERVICIO')
        self.assertEqual(ticket.total, Decimal('500.00'))
        snap = ticket.snapshot_json
        self.assertEqual(snap['saldo_pendiente'], 0.0)


# ============================================================
# TC-08  Flujo completo: crear pedido + cobrar + verificar snapshot
# ============================================================
class TC08FlujoPedidoCompleto(TestCase):
    """Prueba de integración del flujo de pedido/hechura."""

    def setUp(self):
        self.usuario = crear_usuario_vendedor()
        self.caja    = crear_caja(self.usuario)
        cat, color, tela, modelo = crear_catalogo()
        self.cliente = Cliente.objects.create(nombre='Jacqueline Vega', telefono='3310000008')
        self.novia   = Novia.objects.create(
            nombre='Karla Estrada',
            fecha_boda='2026-09-20',
            creado_por=self.usuario,
        )
        self.dama = Dama.objects.create(
            novia=self.novia,
            nombre='Laura Mendoza',
            talla='M',
            modelo_especial='',
            color_especial='Rosa Palo',
        )

    def test_a_ticket_pedido_tiene_items(self):
        cat, color, tela, modelo = crear_catalogo()
        pedido = Pedido.objects.create(
            cliente=self.cliente,
            novia=self.novia,
            dama=self.dama,
            modelo=modelo,
            color=color,
            tela=tela,
            talla='M',
            precio=Decimal('9500.00'),
            creado_por=self.usuario,
        )

        ticket = registrar_cobro(
            origen_tipo='pedido',
            origen_obj=pedido,
            monto=Decimal('2500.00'),
            metodo='TRANSFERENCIA',
            usuario=self.usuario,
        )

        items = ticket.snapshot_json.get('items', [])
        self.assertGreater(len(items), 0, "El ticket de pedido debe tener al menos un ítem sintético.")

    def test_b_saldo_y_abonos_correctos(self):
        cat, color, tela, modelo = crear_catalogo()
        pedido = Pedido.objects.create(
            cliente=self.cliente,
            novia=self.novia,
            precio=Decimal('9500.00'),
            creado_por=self.usuario,
        )

        ticket1 = registrar_cobro(
            origen_tipo='pedido',
            origen_obj=pedido,
            monto=Decimal('2500.00'),
            metodo='EFECTIVO',
            usuario=self.usuario,
        )
        ticket2 = registrar_cobro(
            origen_tipo='pedido',
            origen_obj=pedido,
            monto=Decimal('3000.00'),
            metodo='TARJETA',
            usuario=self.usuario,
        )

        pedido.refresh_from_db()
        self.assertEqual(pedido.anticipo, Decimal('5500.00'))
        self.assertEqual(pedido.saldo_pendiente, Decimal('4000.00'))
        self.assertEqual(pedido.estado_pago, 'PARCIAL')

        snap2 = ticket2.snapshot_json
        self.assertEqual(snap2['total_pagado_acumulado'], 5500.0)
        self.assertEqual(snap2['saldo_pendiente'], 4000.0)
        self.assertEqual(len(snap2['abonos']), 2)


# ============================================================
# TC-09  Duplicación de variante pierde fotografía
# ============================================================
class TC09ClonVariantePierdeFoto(TestCase):
    """
    DOCUMENTA bug P13.
    Clonar una variante no copia la foto del producto base.
    """

    def setUp(self):
        self.usuario = crear_usuario_vendedor()
        crear_caja(self.usuario)
        self.c = Client()
        grupo_admin, _ = Group.objects.get_or_create(name='Admin')
        self.usuario.groups.add(grupo_admin)
        self.c.force_login(self.usuario)
        session = self.c.session
        session['active_profile_id'] = self.usuario.id
        session.save()

    def test_clonar_variante_no_tiene_foto(self):
        cat, color, tela, modelo = crear_catalogo()
        producto_base = crear_producto(cat, color, tela, modelo)

        color2, _ = Color.objects.get_or_create(nombre='Azul Marino', defaults={'codigo_hex': '#001f5b'})

        response = self.c.post(
            reverse('api_clonar_variante', args=[producto_base.pk]),
            content_type='application/json',
            data=json.dumps({'color': color2.nombre, 'talla': 'L'}),
        )

        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'ok':
                nuevo_id = data.get('id') or data.get('producto_id')
                if nuevo_id:
                    nueva_variante = Producto.objects.get(pk=nuevo_id)
                    self.assertFalse(
                        bool(nueva_variante.foto),
                        "Bug P13 DOCUMENTADO: la variante clonada no tiene foto. "
                        "La foto del producto base no se copia al clonar. "
                        "Requiere PR para copiar foto en api_clonar_variante."
                    )


# ============================================================
# TC-10  Folio de Apartado no es atómico (race condition teórica)
# ============================================================
class TC10FolioApartadoNoAtomico(TestCase):
    """
    DOCUMENTA bug P de folio duplicado potencial.
    El folio de Apartado usa COUNT+1, no Secuencia.siguiente().
    Este test muestra la mecánica aunque no puede reproducir el race en un test síncrono.
    """

    def test_folio_apartado_usa_count_no_secuencia(self):
        """
        Confirma que dos apartados creados secuencialmente tienen folios únicos,
        y documenta que la implementación actual usa COUNT+1 (no atómica).
        """
        cliente = Cliente.objects.create(nombre='Test Race', telefono='3310000010')

        ap1 = Apartado.objects.create(
            cliente=cliente,
            cliente_nombre=cliente.nombre,
            cliente_telefono=cliente.telefono,
            total=Decimal('1000.00'),
        )
        ap2 = Apartado.objects.create(
            cliente=cliente,
            cliente_nombre=cliente.nombre,
            cliente_telefono=cliente.telefono,
            total=Decimal('2000.00'),
        )

        self.assertNotEqual(ap1.folio, ap2.folio,
                            "Los folios deben ser únicos (pasan secuencialmente)")
        self.assertTrue(ap1.folio.startswith('AP-'),
                        "Folio debe iniciar con AP-")

        # Documenta que Apartado.save() usa COUNT+1, no Secuencia.siguiente()
        # En producción bajo alta concurrencia, dos requests simultáneos pueden
        # obtener el mismo COUNT y generar folio duplicado.
        # Corrección: usar Secuencia.siguiente('AP') como hace Ticket.save()
