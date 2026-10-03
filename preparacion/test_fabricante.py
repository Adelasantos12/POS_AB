import json
import uuid
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth.models import User, Group
from django.urls import reverse
from boutique.models import Categoria, Color, Modelo, Producto
from .models import PiezaEtiqueta, VariantePreparada, CodigoFabricante, MovimientoPieza

class FabricanteTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('fabricante', 'f@example.com', 'pass')
        self.vendor = User.objects.create_user('seller', password='pass')
        self.vendor.groups.add(Group.objects.get(name='Vendedor'))
        self.login(self.admin)
        from boutique.models import CorteCaja
        CorteCaja.objects.create(abierto_por=self.admin,monto_apertura=1000,cerrado=False)
        cat = Categoria.objects.create(nombre='Capas prueba')
        model = Modelo.objects.create(nombre='Capa compartida', categoria=cat)
        self.products=[]
        for color, size in [('Beige','M'),('Negro','L')]:
            p=Producto.objects.create(modelo=model,categoria=cat,color=Color.objects.get_or_create(nombre=color)[0],talla=size,precio_venta=100,costo_referencia=40)
            VariantePreparada.objects.create(producto=p)
            self.products.append(p)
        self.code=CodigoFabricante.objects.create(codigo='0012345678905')
        self.code.productos.add(*self.products)
        self.url=reverse('preparacion:fabricante')

    def login(self, user):
        self.client.force_login(user)
        session=self.client.session
        session['active_profile_id']=user.pk
        session.save()

    def receive(self, product=None, quantity=2, location='BOUTIQUE', key=None):
        return self.client.post(self.url,{'accion':'entrada','producto':(product or self.products[0]).pk,
            'cantidad':quantity,'ubicacion':location,'clave':key or str(uuid.uuid4())})

    def test_receive_retry_search_and_costs(self):
        key=str(uuid.uuid4())
        self.assertEqual(self.receive(key=key).status_code,302)
        self.assertEqual(self.receive(key=key).status_code,302)
        self.assertEqual(PiezaEtiqueta.objects.count(),2)
        self.assertEqual(PiezaEtiqueta.objects.first().costo_unitario,Decimal('40'))
        self.receive(self.products[1],location='BODEGA')
        data=self.client.get('/api/search-global/',{'q':self.code.codigo}).json()
        self.assertTrue(data['choose_variant'])
        self.assertEqual([i['stock'] for i in data['results']],[2,0])
        self.assertContains(self.client.get(self.url),'Códigos del fabricante')

    def test_real_sale_variant_stock_history_and_retry(self):
        self.receive(quantity=3)
        self.receive(self.products[1],quantity=2)
        payload={'items':[{'id':self.products[0].pk,'cantidad':1,'manufacturer_code':self.code.codigo}],
            'total':100,'pago_inicial':100,'sin_registro':True,'metodo':'EFECTIVO','idempotency_key':str(uuid.uuid4())}
        response=self.client.post('/api/registrar-venta/',json.dumps(payload),content_type='application/json')
        self.assertEqual(response.status_code,200,response.content)
        self.assertEqual(response.json()['status'],'ok',response.content)
        again=self.client.post('/api/registrar-venta/',json.dumps(payload),content_type='application/json')
        self.assertEqual(again.json(),response.json())
        self.assertEqual(PiezaEtiqueta.objects.filter(vendida__isnull=False).count(),1)
        self.products[0].refresh_from_db(); self.products[1].refresh_from_db()
        self.assertEqual(self.products[0].cantidad_actual,2)
        self.assertEqual(self.products[1].cantidad_actual,2)
        self.assertEqual(MovimientoPieza.objects.get(accion='VENDIDA').costo_unitario,40)

    def test_correction_preserves_total_codes_and_cost(self):
        self.receive(quantity=3)
        codes=list(PiezaEtiqueta.objects.values_list('codigo',flat=True))
        data={'accion':'corregir','origen':self.products[0].pk,'destino':self.products[1].pk,
            'cantidad':2,'ubicacion':'BOUTIQUE','motivo':'Color contado incorrectamente','clave':str(uuid.uuid4())}
        r=self.client.post(self.url,data)
        self.assertEqual(r.status_code,302,r.context.get('error') if r.context else r.content)
        r=self.client.post(self.url,data)
        self.assertEqual(r.status_code,302,r.context.get('error') if r.context else r.content)
        self.assertEqual(list(PiezaEtiqueta.objects.values_list('codigo',flat=True)),codes)
        for p,expected in zip(self.products,[1,2]):
            p.refresh_from_db(); self.assertEqual(p.cantidad_actual,expected)
        self.assertEqual(PiezaEtiqueta.objects.filter(costo_unitario=40).count(),3)
        self.assertEqual(MovimientoPieza.objects.filter(accion='CORRECCION').count(),2)

    def test_reject_oversell_wrong_code_and_seller_mapping(self):
        self.receive(location='BODEGA')
        payload={'items':[{'id':self.products[0].pk,'cantidad':1,'manufacturer_code':self.code.codigo}]}
        self.assertEqual(self.client.post('/api/registrar-venta/',json.dumps(payload),content_type='application/json').status_code,409)
        payload['items'][0]['manufacturer_code']='wrong'
        self.assertEqual(self.client.post('/api/registrar-venta/',json.dumps(payload),content_type='application/json').status_code,400)
        self.login(self.vendor)
        self.assertNotContains(self.client.get(self.url),'name="costo_unitario"')
        self.client.post(self.url,{'accion':'vincular','codigo':'999','productos':[self.products[0].pk]})
        self.assertFalse(CodigoFabricante.objects.filter(codigo='999').exists())

    def test_bulk_cost_ui_and_api(self):
        self.assertContains(self.client.get(reverse('subida_bloque')),'name="costo_referencia"')
        data={'filas':[{'categoria':'Otros','color':'Blanco','talla':'U','precio':'200','costo_referencia':'75.50'}]}
        r=self.client.post(reverse('api_subida_bloque'),json.dumps(data),content_type='application/json')
        self.assertEqual(r.status_code,200,r.content)
        self.assertEqual(Producto.objects.get(categoria__nombre='Otros').costo_referencia,Decimal('75.50'))
        self.login(self.vendor)
        self.assertNotContains(self.client.get(reverse('subida_bloque')),'name="costo_referencia"')
        data['filas'][0]['categoria']='Sin costos'
        self.client.post(reverse('api_subida_bloque'),json.dumps(data),content_type='application/json')
        self.assertIsNone(Producto.objects.get(categoria__nombre__iexact='Sin Costos').costo_referencia)
