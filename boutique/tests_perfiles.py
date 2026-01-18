from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User, Group
from boutique.models import CorteCaja, Producto, Categoria, Color, Auditoria

class ProfileFlowTest(TestCase):
    def setUp(self):
        # Crear grupos
        self.vendedor_group, _ = Group.objects.get_or_create(name='Vendedor')
        self.admin_group, _ = Group.objects.get_or_create(name='Admin')

        # Crear usuarios
        self.vendedora = User.objects.create_user(username='vendedora', password='pass123')
        self.vendedora.groups.add(self.vendedor_group)

        self.admin_user = User.objects.create_user(username='admin', password='pass456')
        self.admin_user.groups.add(self.admin_group)

        # Iniciar sesión en terminal (con vendedora)
        self.client.login(username='vendedora', password='pass123')

    def test_full_profile_flow(self):
        # 1. Al entrar, debe redirigir a selección de perfil (porque no hay active_profile_id en sesión)
        response = self.client.get(reverse('index'), follow=True)
        self.assertTemplateUsed(response, 'boutique/seleccionar_perfil.html')

        # 2. Seleccionar perfil vendedora
        response = self.client.post(reverse('autenticar_perfil'), {
            'user_id': self.vendedora.id,
            'password': 'pass123'
        }, follow=True)
        # Como es vendedora y no hay caja, redirige a apertura
        self.assertTemplateUsed(response, 'boutique/apertura_caja.html')

        # 3. Abrir caja como vendedora
        response = self.client.post(reverse('apertura_caja'), {'monto_apertura': 1000}, follow=True)
        self.assertTemplateUsed(response, 'boutique/pos_dashboard.html')
        self.assertTrue(CorteCaja.objects.filter(cerrado=False).exists())
        corte = CorteCaja.objects.filter(cerrado=False).first()
        self.assertEqual(corte.abierto_por, self.vendedora)

        # 4. Cambiar a perfil admin
        self.client.get(reverse('cambiar_perfil'))
        response = self.client.post(reverse('autenticar_perfil'), {
            'user_id': self.admin_user.id,
            'password': 'pass456'
        }, follow=True)
        self.assertTemplateUsed(response, 'boutique/admin_dashboard.html')

        # 5. Verificar que la caja SIGUE abierta y accesible
        self.assertTrue(CorteCaja.objects.filter(cerrado=False).exists())

        # 6. Editar inventario como Admin (debe funcionar)
        cat = Categoria.objects.create(nombre='TestCat')
        color = Color.objects.create(nombre='TestColor')
        prod = Producto.objects.create(categoria=cat, color=color, precio_venta=100, talla='U', sku='TEST-123')

        response = self.client.post(reverse('api_editar_producto', kwargs={'pk': prod.id}),
                                    data='{"precio": 200, "stock": 10}',
                                    content_type='application/json')
        self.assertEqual(response.status_code, 200)
        prod.refresh_from_db()
        self.assertEqual(float(prod.precio_venta), 200.0)

        # Verificar auditoría
        self.assertTrue(Auditoria.objects.filter(usuario=self.admin_user, accion='Edición de Producto').exists())

        # 7. Volver a vendedora
        self.client.get(reverse('cambiar_perfil'))
        self.client.post(reverse('autenticar_perfil'), {
            'user_id': self.vendedora.id,
            'password': 'pass123'
        })

        # 8. Verificar acceso a POS y que caja sigue ahí
        response = self.client.get(reverse('pos_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'boutique/pos_dashboard.html')
        self.assertIn('corte', response.context)
        self.assertEqual(response.context['corte'].abierto_por, self.vendedora)

    def test_permission_denied_for_vendedor_on_admin_views(self):
        # Seleccionar vendedora
        self.client.post(reverse('autenticar_perfil'), {
            'user_id': self.vendedora.id,
            'password': 'pass123'
        })

        # Intentar acceder a dashboard admin
        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code, 302) # Redirects to index

        # Intentar acceder a gestion usuarios
        response = self.client.get(reverse('gestion_usuarios'))
        self.assertEqual(response.status_code, 403) # PermissionDenied returns 403
