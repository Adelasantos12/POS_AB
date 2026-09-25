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
        pending = self.client.get('/api/search-global/', {'q': pieces[0].codigo}).json()
        self.assertEqual(pending['results'], [])
        self.assertIn('aún no se contó', pending['message'])
        product.refresh_from_db()
        self.assertEqual(product.cantidad_actual, 0)

        self.client.post(reverse('preparacion:iniciar_conteo'))
        response = self.client.post(reverse('preparacion:escanear'), {'codigo': pieces[0].codigo})
        self.assertEqual(response.status_code, 200)
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
        self.assertContains(self.client.get(reverse('preparacion:inicio')),
                            'value="5" aria-label="Número de etiquetas"')
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
        response = self.client.get(reverse('inventario_view'), {'q': first.sku})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, first.sku)
        self.assertContains(response, variants[1].sku)
        self.assertContains(response, 'Imprimir etiquetas de esta variante', count=2)
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

    def test_after_initial_count_receiving_adds_exactly_once(self):
        self._variant()
        variant = VariantePreparada.objects.get()
        self.client.post(reverse('preparacion:emitir_etiquetas', args=[variant.pk]), {'cantidad': 2})
        self.client.post(reverse('preparacion:iniciar_conteo'))
        self.client.post(reverse('preparacion:cerrar_conteo'), {'confirmar': 'SI'})
        page = self.client.get(reverse('preparacion:inicio'))
        self.assertContains(page, 'Recibir mercancía nueva')
        self.assertContains(page, 'Agregar nueva variante')
        piece = PiezaEtiqueta.objects.first()
        endpoint = reverse('preparacion:recibir')
        self.assertEqual(self.client.post(endpoint, {'codigo': piece.codigo}).status_code, 200)
        self.assertEqual(self.client.post(endpoint, {'codigo': piece.codigo}).status_code, 409)
        variant.producto.refresh_from_db()
        self.assertEqual(variant.producto.cantidad_actual, 1)
        self.assertEqual(variant.producto.stock_teorico, 1)

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
