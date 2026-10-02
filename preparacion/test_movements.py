import json
import uuid
from django.test import TestCase
from django.contrib.auth.models import User, Group
from django.urls import reverse
from django.utils import timezone
from boutique.models import Categoria, Color, Talla, Producto, Venta, ItemVenta
from .models import VariantePreparada, PiezaEtiqueta, MovimientoPieza, OperacionPrendas


class CustodyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('owner', 'owner@example.com', 'pass')
        self.login(self.user)
        category = Categoria.objects.create(nombre='Ropa prueba')
        color = Color.objects.create(nombre='Azul prueba')
        Talla.objects.get_or_create(nombre='M')
        response = self.client.post(reverse('preparacion:guardar_variante'), {
            'modelo_nuevo': 'Modelo custodia', 'categoria_id': category.pk,
            'color_id': color.pk, 'talla': 'M', 'precio': '1000'})
        self.assertEqual(response.status_code, 302)
        self.variant = VariantePreparada.objects.get()
        self.client.post(reverse('preparacion:emitir_etiquetas', args=[self.variant.pk]), {'cantidad': 2})
        self.pieces = list(PiezaEtiqueta.objects.order_by('pk'))
        self.client.post(reverse('preparacion:iniciar_conteo'))
        for piece in self.pieces:
            self.client.post(reverse('preparacion:escanear'), {'codigo': piece.codigo})
        self.client.post(reverse('preparacion:cerrar_conteo'), {'confirmar': 'SI'})

    def login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session['active_profile_id'] = user.pk
        session.save()

    def payload(self, pieces=None, **kwargs):
        data = dict(clave=str(uuid.uuid4()), accion='MOVER', destino='BODEGA',
                    estado='DISPONIBLE', encargado='', regreso='', notas='',
                    piezas=[{'codigo': p.codigo, 'revision': p.revision} for p in (pieces or self.pieces)])
        data.update(kwargs)
        return data

    def post(self, data):
        return self.client.post(reverse('preparacion:confirmar_movimiento'), json.dumps(data), content_type='application/json')

    def test_mixed_destinations_no_stock_change_and_retry_safe(self):
        data = self.payload()
        data['piezas'][1]['individual'] = {'destino': 'TALLER', 'estado': 'ARREGLO', 'encargado': 'Ana', 'regreso': '2026-11-10'}
        self.assertEqual(self.post(data).status_code, 200)
        self.assertEqual(self.post(data).status_code, 200)
        self.assertEqual(MovimientoPieza.objects.count(), 2)
        self.assertEqual(OperacionPrendas.objects.count(), 1)
        first, second = [PiezaEtiqueta.objects.get(pk=p.pk) for p in self.pieces]
        self.assertEqual((first.ubicacion, second.ubicacion), ('BODEGA', 'TALLER'))
        self.assertEqual(Producto.objects.get().cantidad_actual, 2)
        self.assertFalse(self.client.get('/api/search-global/', {'q': second.codigo}).json()['results'])
        sold = self.client.post('/api/registrar-venta/', json.dumps({'items':[{'id': self.variant.producto_id,
            'cantidad':1,'unit_codes':[second.codigo]}]}), content_type='application/json')
        self.assertEqual(sold.status_code, 409)
        returned = self.payload([second], accion='REGRESO', destino='BOUTIQUE')
        self.assertEqual(self.post(returned).status_code, 200)
        self.assertTrue(self.client.get('/api/search-global/', {'q': second.codigo}).json()['results'])
        self.assertEqual(Producto.objects.get().cantidad_actual, 2)

    def test_stale_piece_rolls_back_whole_batch(self):
        PiezaEtiqueta.objects.filter(pk=self.pieces[1].pk).update(revision=1)
        self.assertEqual(self.post(self.payload()).status_code, 409)
        self.assertFalse(MovimientoPieza.objects.exists())
        self.assertFalse(OperacionPrendas.objects.exists())
        self.assertEqual(PiezaEtiqueta.objects.filter(ubicacion='BOUTIQUE').count(), 2)

    def test_return_is_linked_to_sale_once_and_requires_admin(self):
        sale = Venta.objects.create(vendedor=self.user, total=1000)
        ItemVenta.objects.create(venta=sale, producto=self.variant.producto, cantidad=1, precio_unitario=1000)
        piece = self.pieces[0]
        piece.refresh_from_db()
        piece.vendida = timezone.now()
        piece.ultima_venta = sale
        piece.estado = 'VENDIDA'
        piece.save()
        Producto.objects.filter(pk=self.variant.producto_id).update(cantidad_actual=1, stock_teorico=1)
        data = self.payload([piece], accion='DEVOLUCION', destino='BOUTIQUE', estado='REVISION', notas='Revisar cierre')
        vendor = User.objects.create_user('seller', password='pass')
        vendor.groups.add(Group.objects.get(name='Vendedor'))
        self.login(vendor)
        self.assertEqual(self.post(data).status_code, 403)
        self.login(self.user)
        self.assertEqual(self.post(data).status_code, 200)
        self.assertEqual(self.post(data).status_code, 200)
        piece.refresh_from_db()
        self.assertIsNone(piece.vendida)
        self.assertEqual(Producto.objects.get().cantidad_actual, 2)
        self.assertEqual(MovimientoPieza.objects.get().venta_id, sale.pk)
        self.assertFalse(self.client.get('/api/search-global/', {'q': piece.codigo}).json()['results'])
        self.assertEqual(self.post(self.payload([piece], accion='DEVOLUCION', destino='BOUTIQUE', notas='Otra vez')).status_code, 409)

    def test_pages_and_individual_receiving(self):
        self.assertContains(self.client.get(reverse('preparacion:movimientos')), '¿Dónde están mis prendas?')
        self.assertContains(self.client.get(reverse('inventario_view')), 'Entradas')
        self.client.post(reverse('preparacion:emitir_etiquetas', args=[self.variant.pk]), {'cantidad': 2})
        for place, state, person, piece in zip(['BODEGA','TALLER'], ['DISPONIBLE','MUESTRA'], ['', 'Taller Ana'], PiezaEtiqueta.objects.filter(contada__isnull=True)):
            res = self.client.post(reverse('preparacion:recibir'), {'codigo':piece.codigo,'ubicacion':place,'estado':state,'encargado':person})
            self.assertEqual(res.status_code, 200)
            piece.refresh_from_db()
            self.assertEqual(piece.ubicacion, place)
        self.assertEqual(Producto.objects.get().cantidad_actual, 4)

    def test_entries_mix_new_and_returned_garments_without_double_stock(self):
        existing = self.pieces[0]
        PiezaEtiqueta.objects.filter(pk=existing.pk).update(ubicacion='TALLER', estado='ARREGLO', encargado='Ana')
        self.client.post(reverse('preparacion:emitir_etiquetas', args=[self.variant.pk]), {'cantidad':1})
        new = PiezaEtiqueta.objects.filter(contada__isnull=True).get()
        lookup = self.client.get(reverse('preparacion:consultar_pieza'), {'codigo':new.codigo,'modo':'ENTRADA'})
        self.assertEqual(lookup.status_code, 200)
        self.assertFalse(lookup.json()['registrada'])
        data = self.payload([existing,new], accion='ENTRADA', destino='BOUTIQUE')
        result = self.post(data)
        self.assertEqual(result.status_code, 200, result.content)
        self.assertTrue(result.json()['folio'].startswith('MOV-'))
        self.assertEqual(Producto.objects.get().cantidad_actual, 3)
        self.assertEqual(self.post(data).status_code, 200)
        self.assertEqual(Producto.objects.get().cantidad_actual, 3)
        self.assertEqual(PiezaEtiqueta.objects.filter(ubicacion='BOUTIQUE', contada__isnull=False).count(), 3)

    def test_entry_error_rolls_back_new_receipt(self):
        self.client.post(reverse('preparacion:emitir_etiquetas', args=[self.variant.pk]), {'cantidad':2})
        new = list(PiezaEtiqueta.objects.filter(contada__isnull=True).order_by('pk'))
        from datetime import timedelta
        from .models import JornadaConteo
        close = JornadaConteo.objects.get(abierta=False)
        PiezaEtiqueta.objects.filter(pk=new[1].pk).update(emitida=close.cerrada-timedelta(days=1))
        result = self.post(self.payload(new, accion='ENTRADA', destino='BOUTIQUE'))
        self.assertEqual(result.status_code, 409)
        self.assertEqual(Producto.objects.get().cantidad_actual, 2)
        self.assertEqual(PiezaEtiqueta.objects.filter(contada__isnull=True).count(), 2)
        self.assertFalse(OperacionPrendas.objects.exists())

    def test_task_pages_drafts_and_read_only_search(self):
        for name,label in [('entradas','Entradas'), ('salidas','Salidas'), ('buscar_prendas','Buscar prendas')]:
            self.assertContains(self.client.get(reverse('preparacion:'+name)), label)
        endpoint = reverse('preparacion:borrador_entrada')
        data = {'piezas':[{'codigo':self.pieces[0].codigo}], 'fields':{'destination':'BODEGA'}}
        self.assertEqual(self.client.post(endpoint,json.dumps(data),content_type='application/json').status_code,200)
        self.assertEqual(self.client.get(endpoint).json()['borrador'],data)
        self.assertContains(self.client.get(reverse('inventario_view')), 'Continuar entrada')
        self.assertNotContains(self.client.get(reverse('preparacion:buscar_prendas')), 'Ver / seleccionar')
        self.assertFalse(MovimientoPieza.objects.exists())
        self.assertEqual(Producto.objects.get().cantidad_actual,2)
        vendor=User.objects.create_user('draft_vendor',password='pass')
        vendor.groups.add(Group.objects.get(name='Vendedor'))
        self.login(vendor)
        self.assertIsNone(self.client.get(endpoint).json()['borrador'])
