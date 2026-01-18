from django.test import TestCase
from django.urls import reverse

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
            'password1': 'testpass123',
            'password2': 'testpass123',
        }
        self.client.post(reverse('signup'), data)
        user = User.objects.get(username='testuser')
        self.assertTrue(user.groups.filter(name='Vendedor').exists())
