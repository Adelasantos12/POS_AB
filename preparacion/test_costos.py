import json
from decimal import Decimal
from unittest.mock import patch, Mock
from django.contrib.auth.models import User, Group
from django.test import TestCase
from django.urls import reverse
from django.http import JsonResponse
from boutique.models import Categoria, Color, Talla, Modelo, Producto, Venta, ItemVenta, MovimientoInventario
from .models import VariantePreparada, PiezaEtiqueta, MovimientoPieza, CambioCosto, AnalisisInversion
from .inversion import resumen


class CostosTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('cost-owner', 'c@example.com', 'pass')
        self.vendor = User.objects.create_user('cost-vendor', password='pass')
        self.vendor.groups.add(Group.objects.get(name='Vendedor'))
        self.login(self.admin)
        category = Categoria.objects.create(nombre='Costo prueba')
        color = Color.objects.create(nombre='Color costo')
        Talla.objects.get_or_create(nombre='M')
        self.model = Modelo.objects.create(nombre='Modelo costos', categoria=category,
            costo_referencia=Decimal('400'), precio_sugerido=Decimal('1000'))
        self.client.post(reverse('preparacion:guardar_variante'), {'modelo_id':self.model.pk,
            'color_id':color.pk, 'talla':'M', 'precio':'1000'})
        self.variant = VariantePreparada.objects.get()
        self.assertEqual(self.variant.producto.costo_referencia, Decimal('400'))
        self.client.post(reverse('preparacion:emitir_etiquetas', args=[self.variant.pk]), {'cantidad':2})
        self.pieces = list(PiezaEtiqueta.objects.order_by('pk'))
        self.client.post(reverse('preparacion:iniciar_conteo'))
        for piece in self.pieces:
            self.client.post(reverse('preparacion:escanear'), {'codigo':piece.codigo})
            piece.refresh_from_db()
        self.client.post(reverse('preparacion:cerrar_conteo'), {'confirmar':'SI'})

    def login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session['active_profile_id'] = user.pk
        session.save()

    def test_valuation_unknown_and_locations(self):
        p = self.pieces[1]
        p.costo_unitario = None
        p.ubicacion = 'TALLER'
        p.estado = 'ARREGLO'
        p.save()
        r = resumen()
        self.assertEqual(r['total'], Decimal('400'))
        self.assertEqual(r['sin_costo'], 1)
        self.assertEqual(r['valor_venta'], Decimal('2000'))
        self.assertEqual(r['disponibles'], Decimal('400'))
        self.assertContains(self.client.get(reverse('preparacion:inversion')), 'Dinero en inventario')
        self.assertContains(self.client.get(reverse('admin_dashboard')), 'Ver inversión, ubicaciones e IA')

    def test_future_reference_does_not_revalue_old_pieces(self):
        response = self.client.post(reverse('preparacion:costo_referencia'),
            {'sku':self.variant.producto.sku, 'costo':'550'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(resumen()['total'], Decimal('800'))
        self.client.post(reverse('preparacion:emitir_etiquetas', args=[self.variant.pk]), {'cantidad':1})
        new = PiezaEtiqueta.objects.filter(contada__isnull=True).get()
        self.client.post(reverse('preparacion:recibir'), {'codigo':new.codigo,'ubicacion':'BODEGA'})
        new.refresh_from_db()
        self.assertEqual(new.costo_unitario, Decimal('550'))
        self.assertEqual(resumen()['total'], Decimal('1350'))

    def test_vendor_cannot_read_or_change_cost(self):
        self.login(self.vendor)
        self.assertEqual(self.client.get(reverse('preparacion:inversion')).status_code, 403)
        self.assertEqual(self.client.post(reverse('preparacion:guardar_costo'),
            {'codigo':self.pieces[0].codigo,'costo':'1','motivo':'hack'}).status_code, 403)
        self.assertNotContains(self.client.get(reverse('preparacion:agregar_modelo')), 'name="costo_referencia"')
        self.assertNotContains(self.client.get(reverse('preparacion:agregar_modelos_bloque')), '-costo_referencia')
        self.client.post(reverse('preparacion:emitir_etiquetas', args=[self.variant.pk]), {'cantidad':1})
        new = PiezaEtiqueta.objects.filter(contada__isnull=True).get()
        self.client.post(reverse('preparacion:recibir'), {'codigo':new.codigo,'costo_unitario':'1'})
        new.refresh_from_db()
        self.assertEqual(new.costo_unitario, Decimal('400'))

    def test_sale_cost_snapshot_and_return_reversal(self):
        piece = self.pieces[0]
        def sale(request):
            v = Venta.objects.create(vendedor=self.admin, total=1000)
            ItemVenta.objects.create(venta=v, producto=self.variant.producto, cantidad=1, precio_unitario=1000)
            MovimientoInventario.objects.create(producto=self.variant.producto, tipo='VENTA', cantidad=-1,
                motivo='VENTA', perfil_activo=self.admin, venta=v, stock_resultante=0)
            return JsonResponse({'status':'ok','tipo':'venta','venta_id':v.pk})
        with patch('preparacion.checkout.original.api_registrar_venta', side_effect=sale):
            response = self.client.post('/api/registrar-venta/', json.dumps({'items':[{
                'id':self.variant.producto_id,'cantidad':1,'unit_codes':[piece.codigo]}]}), content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(resumen()['margen_30'], Decimal('600'))
        event = MovimientoPieza.objects.get(accion='VENDIDA')
        self.assertEqual(event.costo_unitario, Decimal('400'))
        piece.refresh_from_db()
        import uuid
        returned = self.client.post(reverse('preparacion:confirmar_movimiento'), json.dumps({
            'clave':str(uuid.uuid4()),'accion':'DEVOLUCION','destino':'BOUTIQUE','estado':'REVISION',
            'notas':'Regreso de prueba','piezas':[{'codigo':piece.codigo,'revision':piece.revision}]}), content_type='application/json')
        self.assertEqual(returned.status_code, 200)
        self.assertEqual(resumen()['margen_30'], Decimal('0'))
        self.assertEqual(resumen()['total'], Decimal('800'))
        self.client.post(reverse('preparacion:guardar_costo'), {'codigo':piece.codigo,'costo':'420','motivo':'Ajuste comprobado'})
        event.refresh_from_db()
        self.assertEqual(event.costo_unitario, Decimal('400'))
        self.assertEqual(CambioCosto.objects.get().nuevo, Decimal('420'))

    def test_invalid_cost_rejected_and_ai_saved_without_mutation(self):
        for invalid in ['-1','NaN','1.234','Infinity']:
            self.assertEqual(self.client.post(reverse('preparacion:guardar_costo'),
                {'codigo':self.pieces[0].codigo,'costo':invalid,'motivo':'Prueba'}).status_code, 400)
        client = Mock()
        client.models.generate_content.return_value.text = 'Completar los costos pendientes antes de decidir descuentos.'
        with patch('boutique.ai_utils.get_gemini_client', return_value=client):
            self.assertEqual(self.client.post(reverse('preparacion:analizar_inversion')).status_code, 200)
        self.assertEqual(AnalisisInversion.objects.count(), 1)
        self.assertEqual(resumen()['total'], Decimal('800'))
        self.assertFalse(CambioCosto.objects.exists())

    def test_model_form_cost_capture_and_vendor_payload_ignored(self):
        endpoint = reverse('preparacion:agregar_modelo')
        response = self.client.post(endpoint, {'nombre':'Costo por formulario',
            'categoria':self.model.categoria_id,'costo_referencia':'725.50',
            'precio_sugerido':'1500','proveedor':'Proveedor registrado'})
        self.assertEqual(response.status_code, 302)
        model = Modelo.objects.get(nombre__iexact='Costo por formulario')
        self.assertEqual(model.costo_referencia, Decimal('725.50'))
        self.login(self.vendor)
        response = self.client.post(endpoint, {'nombre':'Modelo vendedor',
            'categoria':self.model.categoria_id,'costo_referencia':'1', 'proveedor':'Oculto'})
        self.assertEqual(response.status_code, 302)
        model = Modelo.objects.get(nombre__iexact='Modelo vendedor')
        self.assertIsNone(model.costo_referencia)
        self.assertEqual(model.proveedor, '')
