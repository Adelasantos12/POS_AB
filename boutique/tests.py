from django.test import TestCase
from django.urls import reverse
import json

class BoutiqueViewsTest(TestCase):
    def test_index_view(self):
        response = self.client.get(reverse('index'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'boutique/index.html')

    def test_signup_view_get(self):
        response = self.client.get(reverse('signup'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'boutique/signup.html')

    def test_signup_assigns_vendedor_group(self):
        from django.contrib.auth.models import User, Group
        # Ensure group exists
        Group.objects.get_or_create(name='Vendedor')

        data = {
            'username': 'testuser',
            'email': 'test@example.com',
            'password1': 'testpass123',
            'password2': 'testpass123',
        }
        self.client.post(reverse('signup'), data)
        user = User.objects.get(username='testuser')
        self.assertTrue(user.groups.filter(name='Vendedor').exists())

class POSAPITest(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User, Group
        from boutique.models import Categoria, Color
        self.user = User.objects.create_user(username='staff', password='pass')
        vendedor_group, _ = Group.objects.get_or_create(name='Vendedor')
        self.user.groups.add(vendedor_group)
        self.categoria = Categoria.objects.create(nombre='Vestido')
        self.color = Color.objects.create(nombre='Rojo')
        self.client.login(username='staff', password='pass')

        # Simular selección de perfil activo
        session = self.client.session
        session['active_profile_id'] = self.user.id
        session.save()

    def test_crear_producto_rapido(self):
        data = {
            'categoria': 'Top',
            'color': 'Azul',
            'rasgo1': 'Manga Corta',
            'precio': 500,
            'estado': 'TIENDA'
        }
        response = self.client.post(reverse('api_crear_producto_rapido'),
                                    data=json.dumps(data),
                                    content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.assertIn('sku', response.json())
