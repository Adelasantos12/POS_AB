import json
from django.contrib.auth.models import User, Group
from django.test import TestCase
from django.urls import reverse
from boutique.models import Categoria, Color, Modelo, Producto
from .models import VariantePreparada, PiezaEtiqueta


class CatalogoTests(TestCase):
    def setUp(self):
        self.user=User.objects.create_superuser('catalogo','c@example.com','pass')
        self.client.force_login(self.user)
        session=self.client.session; session['active_profile_id']=self.user.pk; session.save()
        self.color=Color.objects.get_or_create(nombre='Negro')[0]
        self.vestidos=Categoria.objects.get(nombre='Vestidos')
        self.velos=Categoria.objects.get(nombre='Velos')

    def product(self,name,category,legacy=False):
        m=None if legacy else Modelo.objects.create(nombre=name,categoria=category)
        return Producto.objects.create(modelo=m,categoria=category,color=self.color,talla='M',precio_venta=100,rasgo1=name)

    def test_filter_search_and_alphabetical_families(self):
        self.product('Zeta',self.vestidos)
        self.product('Ámbar',self.vestidos)
        self.product('Beta',self.vestidos,True)
        self.product('Aaa velo',self.velos)
        page=self.client.get(reverse('inventario_view'),{'categoria':self.vestidos.pk})
        self.assertEqual([f['nombre'] for f in page.context['familias']],['Ambar','Beta','Zeta'])
        self.assertEqual(page.context['resumen']['modelos'],3)
        self.assertContains(page,'Todas las categorías')
        page=self.client.get(reverse('inventario_view'),{'categoria':self.velos.pk,'q':'Zeta'})
        self.assertEqual(page.context['resumen']['modelos'],0)

    def test_reclassify_old_category_preserves_codes_photo_stock(self):
        old=Categoria.objects.create(nombre='1 hombro manga caida')
        p=self.product('',old,True)
        variant=VariantePreparada.objects.create(producto=p)
        piece=PiezaEtiqueta.objects.create(variante=variant)
        p.refresh_from_db()
        before=(p.sku,p.cantidad_actual,p.foto.name,p.precio_venta,p.costo_referencia,piece.codigo)
        r=self.client.post(reverse('preparacion:editar_catalogo',args=[p.pk]),{'nombre':'1 hombro manga caída','categoria':self.vestidos.pk})
        self.assertEqual(r.status_code,302)
        p.refresh_from_db();piece.refresh_from_db()
        self.assertEqual(p.categoria_id,self.vestidos.pk)
        self.assertEqual(p.modelo.nombre,'1 Hombro Manga Caida')
        self.assertEqual(before,(p.sku,p.cantidad_actual,p.foto.name,p.precio_venta,p.costo_referencia,piece.codigo))
        self.assertTrue(Categoria.objects.filter(pk=old.pk).exists())
        other=self.product('Otro modelo',self.velos)
        r=self.client.post(reverse('preparacion:editar_catalogo',args=[p.pk]),{'nombre':other.modelo.nombre,'categoria':self.velos.pk})
        self.assertContains(r,'Ya existe otro modelo')
        p.refresh_from_db();self.assertEqual(p.categoria_id,self.vestidos.pk)

    def test_bulk_name_is_not_category_and_different_models_stay_separate(self):
        rows=[{'nombre_modelo':name,'categoria':'Vestidos','color':'Negro','talla':'M','precio':'200','rasgo1':'Escote asimétrico'} for name in ['1 hombro','Manga caída']]
        r=self.client.post(reverse('api_subida_bloque'),json.dumps({'filas':rows}),content_type='application/json')
        self.assertEqual(r.status_code,200,r.content)
        self.assertEqual(Producto.objects.count(),2)
        self.assertEqual(Modelo.objects.filter(producto__isnull=False).distinct().count(),2)
        self.assertEqual(set(Producto.objects.values_list('categoria_id',flat=True)),{self.vestidos.pk})
        self.assertFalse(Categoria.objects.filter(nombre__icontains='hombro').exists())
        self.assertContains(self.client.get(reverse('subida_bloque')),'name="nombre_modelo"')

    def test_vendor_cannot_reclassify(self):
        p=self.product('Prueba',self.vestidos)
        user=User.objects.create_user('vendedora',password='pass');user.groups.add(Group.objects.get(name='Vendedor'))
        self.client.force_login(user);session=self.client.session;session['active_profile_id']=user.pk;session.save()
        self.assertEqual(self.client.post(reverse('preparacion:editar_catalogo',args=[p.pk]),{'nombre':'Cambio','categoria':self.velos.pk}).status_code,403)
        p.refresh_from_db();self.assertEqual(p.categoria_id,self.vestidos.pk)
