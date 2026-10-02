import tempfile
from io import BytesIO
from PIL import Image
from django.test import TestCase, override_settings
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from boutique.models import Modelo, Categoria, Producto


class ModelPhotoTests(TestCase):
    def setUp(self):
        user = User.objects.create_superuser('photo-admin', 'a@example.com', 'pass')
        self.client.force_login(user)
        session = self.client.session
        session['active_profile_id'] = user.pk
        session.save()
        self.category = Categoria.objects.create(nombre='Fotos prueba')
        self.temp = tempfile.TemporaryDirectory()
        self.override = override_settings(MEDIA_ROOT=self.temp.name)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.addCleanup(self.temp.cleanup)

    def photo(self):
        out = BytesIO()
        Image.new('RGB', (12,12), 'blue').save(out, format='PNG')
        return SimpleUploadedFile('modelo.png', out.getvalue(), content_type='image/png')

    def test_model_photo_saved_before_any_variant(self):
        self.assertEqual(self.client.get(reverse('preparacion:agregar_modelo')).status_code, 200)
        response = self.client.post(reverse('preparacion:agregar_modelo'), {
            'nombre':'Princesa nueva', 'categoria':self.category.pk,
            'foto_principal':self.photo(), 'combinacion_telas':'Satín',
            'descripcion':'Escote cuadrado', 'referencia':'P-01'})
        self.assertEqual(response.status_code, 302)
        model = Modelo.objects.get(nombre__iexact='Princesa nueva')
        self.assertTrue(model.foto_principal.storage.exists(model.foto_principal.name))
        self.assertEqual(model.descripcion, 'Escote cuadrado')
        self.assertFalse(Producto.objects.exists())
        page = self.client.get(response.url)
        self.assertContains(page, 'Agregar variantes de')
        self.assertContains(page, 'Satín')

    def test_batch_creates_models_without_stock_and_rejects_duplicate(self):
        endpoint = reverse('preparacion:agregar_modelos_bloque')
        self.assertEqual(self.client.get(endpoint).status_code, 200)
        data = {'modelos-TOTAL_FORMS':'2', 'modelos-INITIAL_FORMS':'0',
                'modelos-MIN_NUM_FORMS':'0', 'modelos-MAX_NUM_FORMS':'20'}
        for i in range(2):
            data.update({f'modelos-{i}-nombre':f'Modelo foto {i}',
                f'modelos-{i}-categoria':self.category.pk,
                f'modelos-{i}-foto_principal':self.photo(),
                f'modelos-{i}-descripcion':'Características', f'modelos-{i}-combinacion_telas':'Tul'})
        response = self.client.post(endpoint, data)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Modelo.objects.filter(nombre__istartswith='Modelo foto').count(), 2)
        self.assertFalse(Producto.objects.exists())
        self.assertContains(self.client.get(response.url), 'Modelos guardados con sus fotos')
        for i in range(2):
            data[f'modelos-{i}-foto_principal'] = self.photo()
        self.assertEqual(self.client.post(endpoint, data).status_code, 200)
        self.assertEqual(Modelo.objects.filter(nombre__istartswith='Modelo foto').count(), 2)
