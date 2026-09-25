from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.http import JsonResponse
from unittest.mock import patch
import json

from boutique.models import Categoria, Color, MovimientoInventario, Producto, Talla
from .models import PiezaEtiqueta, VariantePreparada


class PreparacionInicialTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('preparador', 'p@example.com', 'testpass')
        self.client.force_login(self.user)
        session = self.client.session
        session['active_profile_id'] = self.user.pk
        session.save()
        self.categoria = Categoria.objects.create(nombre='Vestidos')
        self.color = Color.objects.create(nombre='Magenta')
        Talla.objects.get_or_create(nombre='M')

    def _variant(self, **kwargs):
        data = {'modelo_nuevo': 'Aurora', 'categoria_id': self.categoria.pk,
                'color_id': self.color.pk, 'talla': 'M', 'precio': '1590'}
        data.update(kwargs)
        return self.client.post(reverse('preparacion:guardar_variante'), data)

    def test_family_variants_and_count_only_scanned_pieces(self):
        self.assertEqual(self._variant().status_code, 302)
        product = Producto.objects.get()
        self.assertEqual(product.sku, f'M{product.modelo_id:05d}-01')
        self.assertEqual(product.cantidad_actual, 0)
        self.assertFalse(product.activo)
        prepared = VariantePreparada.objects.get(producto=product)
        pdf = self.client.post(reverse('preparacion:emitir_etiquetas', args=[prepared.pk]),
                               {'cantidad': 3})
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf['Content-Type'], 'application/pdf')
        pieces = list(PiezaEtiqueta.objects.order_by('pk'))
        self.assertEqual(len({p.codigo for p in pieces}), 3)
        verification = self.client.post(reverse('preparacion:verificar_etiqueta'),
                                        {'codigo': pieces[0].codigo})
        self.assertEqual(verification.status_code, 200)
        self.assertEqual(verification.json()['sku'], product.sku)
        self.assertIn('pendiente de conteo', verification.json()['estado'])
        self.assertEqual(self.client.post(reverse('preparacion:verificar_etiqueta'),
                                          {'codigo': '800009999999'}).status_code, 404)
        pending = self.client.get('/api/search-global/', {'q': pieces[0].codigo}).json()
        self.assertEqual(pending['results'], [])
        self.assertIn('aún no se contó', pending['message'])
        self.assertIn(product.sku, pending['message'])
        product.refresh_from_db()
        self.assertEqual(product.cantidad_actual, 0)

        page = self.client.get(reverse('preparacion:conteo'))
        self.assertContains(page, 'Iniciar conteo')
        self.client.post(reverse('preparacion:iniciar_conteo'))
        page = self.client.get(reverse('preparacion:conteo'))
        self.assertContains(page, 'Escanea un vestido tras otro')
        response = self.client.post(reverse('preparacion:escanear'), {'codigo': pieces[0].codigo})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['sku'], product.sku)
        self.assertEqual(response.json()['cantidad_variante'], 1)
        self.assertContains(self.client.get(reverse('preparacion:conteo')), pieces[0].codigo)
        during_count = self.client.get('/api/search-global/', {'q': pieces[0].codigo}).json()
        self.assertIn('inventario inicial sigue abierto', during_count['message'])
        repeat = self.client.post(reverse('preparacion:escanear'), {'codigo': pieces[0].codigo})
        self.assertEqual(repeat.status_code, 409)
        self.assertIn('No se sumó otra vez', repeat.json()['message'])
        product.refresh_from_db()
        self.assertEqual(product.cantidad_actual, 0)

        self.client.post(reverse('preparacion:cerrar_conteo'), {'confirmar': 'SI'})
        product.refresh_from_db()
        self.assertEqual(product.cantidad_actual, 1)
        self.assertEqual(product.stock_teorico, 1)
        self.assertTrue(product.activo)
        self.assertEqual(PiezaEtiqueta.objects.filter(contada__isnull=True).count(), 2)

    def test_estimate_five_can_close_as_seven_or_three(self):
        self.assertEqual(self._variant(cantidad_estimada='5').status_code, 302)
        first = VariantePreparada.objects.get()
        self.assertEqual(first.cantidad_estimada, 5)
        self.assertContains(self.client.get(reverse('inventario_view')),
                            'Imprimir para esta variante')
        self.client.post(reverse('preparacion:emitir_etiquetas', args=[first.pk]),
                         {'cantidad': 5})
        other, _ = Color.objects.get_or_create(nombre='Azul Rey')
        self.assertEqual(self._variant(modelo_id=first.producto.modelo_id, modelo_nuevo='',
                                      color_id=other.pk, cantidad_estimada='5').status_code, 302)
        second = VariantePreparada.objects.exclude(pk=first.pk).get()
        self.client.post(reverse('preparacion:emitir_etiquetas', args=[second.pk]),
                         {'cantidad': 5})
        self.client.post(reverse('preparacion:iniciar_conteo'))
        extra = self.client.post(reverse('preparacion:emitir_etiquetas', args=[first.pk]),
                                 {'cantidad': 2})
        self.assertEqual(extra.status_code, 200)
        first.producto.refresh_from_db()
        self.assertEqual(first.producto.cantidad_actual, 0)
        for piece in first.piezas.all():
            self.assertEqual(self.client.post(reverse('preparacion:escanear'),
                                              {'codigo': piece.codigo}).status_code, 200)
        for piece in second.piezas.order_by('pk')[:3]:
            self.client.post(reverse('preparacion:escanear'), {'codigo': piece.codigo})
        self.client.post(reverse('preparacion:cerrar_conteo'), {'confirmar': 'SI'})
        first.producto.refresh_from_db()
        second.producto.refresh_from_db()
        self.assertEqual(first.producto.cantidad_actual, 7)
        self.assertEqual(second.producto.cantidad_actual, 3)

    def test_existing_model_gets_distinct_variant_without_duplicate(self):
        self._variant()
        first = Producto.objects.get()
        other_color = Color.objects.create(nombre='Azul')
        self.assertEqual(self._variant(modelo_id=first.modelo_id, modelo_nuevo='',
                                      color_id=other_color.pk).status_code, 302)
        variants = list(Producto.objects.order_by('pk'))
        self.assertEqual(variants[1].sku, f'M{first.modelo_id:05d}-02')
        self._variant(modelo_id=first.modelo_id, modelo_nuevo='', color_id=other_color.pk)
        self.assertEqual(Producto.objects.count(), 2)
        first.modelo.foto_principal = 'modelos/aurora.jpg'
        first.modelo.save(update_fields=['foto_principal'])
        response = self.client.get(reverse('inventario_view'), {'q': first.sku})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, first.sku)
        self.assertContains(response, variants[1].sku)
        self.assertContains(response, 'Imprimir para esta variante', count=2)
        self.assertContains(response, 'Agregar variante de este modelo')
        self.assertContains(response, 'modelos/aurora.jpg')
        self.assertEqual(len(response.context['familias']), 1)
        self.assertEqual(len(response.context['familias'][0]['productos']), 2)
        self.assertNotContains(response, 'Registro avanzado')
        self.assertContains(response, 'Pendiente de conteo', count=2)

    def test_existing_sku_is_prepared_without_duplicate_product(self):
        self._variant()
        product = Producto.objects.get()
        VariantePreparada.objects.all().delete()
        response = self.client.post(reverse('preparacion:agregar_existente'),
                                    {'sku': product.sku.lower().replace('-', "'")})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Producto.objects.count(), 1)
        self.assertTrue(VariantePreparada.objects.filter(producto=product).exists())

    def test_inventory_print_creates_unique_labels_and_variant_form_stays_in_family(self):
        self._variant()
        base = Producto.objects.get()
        self.assertContains(self.client.get(reverse('preparacion:nueva_variante', args=[base.pk])),
                            'Agregar variante')
        response = self.client.post(reverse('preparacion:imprimir_producto', args=[base.pk]),
                                    {'cantidad': 2})
        self.assertEqual(response['Content-Type'], 'application/pdf')
        codes = list(PiezaEtiqueta.objects.values_list('codigo', flat=True))
        self.assertEqual(len(set(codes)), 2)
        self.assertEqual(Producto.objects.get(pk=base.pk).cantidad_actual, 0)
        self.assertEqual(self.client.get(reverse('imprimir_etiquetas_pdf'),
                                         {'items': f'{base.pk}:1'}).status_code, 409)
        new_color = Color.objects.create(nombre='Azul')
        response = self.client.post(reverse('preparacion:guardar_variante'), {
            'base_producto_id': base.pk, 'color_id': new_color.pk,
            'talla': 'M', 'precio': '1590', 'cantidad_estimada': '1',
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn('inventario/?q=', response.url)
        second = Producto.objects.exclude(pk=base.pk).get()
        self.assertEqual(second.modelo_id, base.modelo_id)
        self.assertEqual(second.cantidad_actual, 0)

    def test_existing_family_without_model_can_add_color(self):
        base = Producto.objects.create(categoria=self.categoria, color=self.color,
                                       rasgo1='Vestido', talla='M', precio_venta=1590)
        azul, _ = Color.objects.get_or_create(nombre='Azul Rey')
        result = self.client.post(reverse('preparacion:guardar_variante'), {
            'base_producto_id': base.pk, 'color_id': azul.pk, 'talla': 'M',
            'precio': '1590', 'cantidad_estimada': '0',
        })
        self.assertEqual(result.status_code, 302)
        new = Producto.objects.exclude(pk=base.pk).get()
        self.assertEqual(new.rasgo1, base.rasgo1)
        self.assertEqual(new.modelo_id, base.modelo_id)
        self.assertEqual(len(self.client.get(reverse('inventario_view'),
                                             {'q': new.sku}).context['familias'][0]['productos']), 2)

    def test_after_initial_count_receiving_adds_exactly_once(self):
        self._variant()
        variant = VariantePreparada.objects.get()
        self.client.post(reverse('preparacion:emitir_etiquetas', args=[variant.pk]), {'cantidad': 2})
        self.client.post(reverse('preparacion:iniciar_conteo'))
        self.client.post(reverse('preparacion:cerrar_conteo'), {'confirmar': 'SI'})
        page = self.client.get(reverse('preparacion:inicio'))
        self.assertContains(page, 'Recibir mercancía nueva')
        self.assertContains(page, 'Registrar un modelo nuevo')
        sobrante = PiezaEtiqueta.objects.first()
        endpoint = reverse('preparacion:recibir')
        self.assertEqual(self.client.post(endpoint, {'codigo': sobrante.codigo}).status_code, 409)
        self.assertContains(self.client.get(reverse('preparacion:conteo')),
                            'Recibir mercancía')
        self.client.post(reverse('preparacion:imprimir_producto', args=[variant.producto_id]),
                         {'cantidad': 1})
        piece = PiezaEtiqueta.objects.order_by('-pk').first()
        reprint = self.client.post(reverse('preparacion:reimprimir_codigo',
                                           args=[variant.producto_id]), {'codigo': piece.codigo})
        self.assertEqual(reprint['Content-Type'], 'application/pdf')
        self.assertEqual(PiezaEtiqueta.objects.count(), 3)
        result = self.client.post(endpoint, {'codigo': piece.codigo})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['sku'], variant.producto.sku)
        self.assertEqual(result.json()['cantidad_variante'], 1)
        self.assertEqual(self.client.post(endpoint, {'codigo': piece.codigo}).status_code, 409)
        self.assertContains(self.client.get(reverse('preparacion:conteo')), piece.codigo)
        variant.producto.refresh_from_db()
        self.assertEqual(variant.producto.cantidad_actual, 1)
        self.assertEqual(variant.producto.stock_teorico, 1)

    def test_daily_new_variant_is_available_only_after_receiving_scan(self):
        self._variant()
        first = VariantePreparada.objects.get()
        self.client.post(reverse('preparacion:imprimir_producto', args=[first.producto_id]),
                         {'cantidad': 1})
        self.client.post(reverse('preparacion:iniciar_conteo'))
        self.client.post(reverse('preparacion:cerrar_conteo'), {'confirmar': 'SI'})
        azul, _ = Color.objects.get_or_create(nombre='Azul Rey')
        self.client.post(reverse('preparacion:guardar_variante'), {
            'base_producto_id': first.producto_id, 'color_id': azul.pk,
            'talla': 'M', 'precio': '1590',
        })
        new = Producto.objects.exclude(pk=first.producto_id).get()
        self.assertEqual(new.cantidad_actual, 0)
        self.client.post(reverse('preparacion:imprimir_producto', args=[new.pk]),
                         {'cantidad': 1})
        piece = PiezaEtiqueta.objects.filter(variante__producto=new).get()
        self.assertEqual(self.client.get('/api/search-global/', {'q': piece.codigo}).json()['results'], [])
        self.assertEqual(self.client.post(reverse('preparacion:recibir'),
                                          {'codigo': piece.codigo}).status_code, 200)
        new.refresh_from_db()
        self.assertEqual(new.cantidad_actual, 1)
        self.assertTrue(new.activo)
        self.assertEqual(self.client.get('/api/search-global/', {'q': piece.codigo}).json()
                         ['results'][0]['sku'], new.sku)

    def test_serial_search_and_sale_reject_repeat(self):
        self._variant()
        variant = VariantePreparada.objects.get()
        self.client.post(reverse('preparacion:emitir_etiquetas', args=[variant.pk]), {'cantidad': 1})
        piece = PiezaEtiqueta.objects.get()
        self.client.post(reverse('preparacion:iniciar_conteo'))
        self.client.post(reverse('preparacion:escanear'), {'codigo': piece.codigo})
        self.client.post(reverse('preparacion:cerrar_conteo'), {'confirmar': 'SI'})
        search = self.client.get('/api/search-global/', {'q': piece.codigo}).json()
        self.assertEqual(search['results'][0]['unit_code'], piece.codigo)
        payload = {'items': [{'id': variant.producto_id, 'cantidad': 1,
                              'unit_codes': [piece.codigo]}]}
        def record_sale(request):
            MovimientoInventario.objects.create(
                producto=variant.producto, tipo='VENTA', cantidad=-1, motivo='VENTA',
                perfil_activo=self.user, stock_resultante=0)
            return JsonResponse({'status': 'ok', 'venta_id': 1})

        with patch('preparacion.checkout.original.api_registrar_venta', side_effect=record_sale) as sale:
            self.assertEqual(self.client.post('/api/registrar-venta/',
                                              json.dumps(payload), content_type='application/json').status_code, 200)
            self.assertEqual(sale.call_count, 1)
            self.assertEqual(self.client.post('/api/registrar-venta/',
                                              json.dumps(payload), content_type='application/json').status_code, 409)
            self.assertEqual(sale.call_count, 1)
        piece.refresh_from_db()
        variant.producto.refresh_from_db()
        self.assertEqual(variant.producto.cantidad_actual, 0)
        self.assertEqual(variant.producto.stock_teorico, 0)
        self.assertIsNotNone(piece.vendida)
        self.assertEqual(self.client.get('/api/search-global/', {'q': piece.codigo}).json()['results'], [])
        self.assertIn('ya se vendió', self.client.get('/api/search-global/',
                                                     {'q': piece.codigo}).json()['message'])
