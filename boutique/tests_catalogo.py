"""
Tests: normalización de catálogos, unicidad de variantes, tallas, alias.
Cubre todos los requisitos de la sección J del requerimiento de normalización.
"""

import json
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.db import IntegrityError

from boutique.models import (
    Color, Tela, Modelo, Categoria, Talla, Producto, Proveedor
)
from boutique.utils import normalizar_nombre, quitar_acentos, nombres_son_iguales


# ─────────────────────────────────────────────────────────────
# Sección B: normalización de nombres en utils.py
# ─────────────────────────────────────────────────────────────

class TestNormalizacionUtils(TestCase):

    def test_quitar_acentos(self):
        self.assertEqual(quitar_acentos('Satín'), 'Satin')
        self.assertEqual(quitar_acentos('Aquí'), 'Aqui')
        self.assertEqual(quitar_acentos('café'), 'cafe')

    def test_normalizar_nombre_title_case(self):
        self.assertEqual(normalizar_nombre('ROJO'), 'Rojo')
        self.assertEqual(normalizar_nombre('rojo'), 'Rojo')
        self.assertEqual(normalizar_nombre('Rojo'), 'Rojo')

    def test_normalizar_nombre_quita_acentos(self):
        self.assertEqual(normalizar_nombre('satín'), 'Satin')
        self.assertEqual(normalizar_nombre('SATÍN'), 'Satin')

    def test_normalizar_nombre_strip(self):
        self.assertEqual(normalizar_nombre('  Rojo  '), 'Rojo')

    def test_normalizar_nombre_vacio(self):
        self.assertEqual(normalizar_nombre(''), '')
        self.assertIsNone(normalizar_nombre(None))

    def test_nombres_son_iguales(self):
        self.assertTrue(nombres_son_iguales('Aqua', 'aqua'))
        self.assertTrue(nombres_son_iguales('AQUA', 'Aquá'))
        self.assertFalse(nombres_son_iguales('Rojo', 'Azul'))


# ─────────────────────────────────────────────────────────────
# Sección B: normalización en save() de catálogos
# ─────────────────────────────────────────────────────────────

class TestNormalizacionSave(TestCase):

    def test_color_save_normaliza(self):
        color = Color.objects.create(nombre='aqua test zz', codigo_hex='#00FFFF')
        self.assertEqual(color.nombre, 'Aqua Test Zz')

    def test_color_save_quita_acentos(self):
        color = Color.objects.create(nombre='satín prueba', codigo_hex='#AAAAAA')
        self.assertEqual(color.nombre, 'Satin Prueba')

    def test_categoria_save_normaliza(self):
        cat = Categoria.objects.create(nombre='VESTIDOS PRUEBA')
        self.assertEqual(cat.nombre, 'Vestidos Prueba')

    def test_modelo_save_normaliza(self):
        modelo = Modelo.objects.create(nombre='mERMAID GOWN TEST')
        self.assertEqual(modelo.nombre, 'Mermaid Gown Test')

    def test_tela_save_normaliza(self):
        tela = Tela.objects.create(nombre='ENCAJE PRUEBA')
        self.assertEqual(tela.nombre, 'Encaje Prueba')


# ─────────────────────────────────────────────────────────────
# Sección C: catálogo de tallas y alias
# ─────────────────────────────────────────────────────────────

class TestTallaAliases(TestCase):

    def test_seed_cargado(self):
        # Las tallas canónicas deben existir (seed en migration 0045)
        self.assertTrue(Talla.objects.filter(nombre='S').exists())
        self.assertTrue(Talla.objects.filter(nombre='M').exists())
        self.assertTrue(Talla.objects.filter(nombre='XL').exists())

    def test_buscar_por_nombre_canonico(self):
        talla = Talla.buscar_por_alias('M')
        self.assertIsNotNone(talla)
        self.assertEqual(talla.nombre, 'M')

    def test_buscar_por_alias_ch_retorna_s(self):
        talla = Talla.buscar_por_alias('ch')
        self.assertIsNotNone(talla)
        self.assertEqual(talla.nombre, 'S')

    def test_buscar_por_alias_chico_retorna_s(self):
        talla = Talla.buscar_por_alias('chico')
        self.assertIsNotNone(talla)
        self.assertEqual(talla.nombre, 'S')

    def test_buscar_por_alias_unitalla(self):
        talla = Talla.buscar_por_alias('unitalla')
        self.assertIsNotNone(talla)
        self.assertEqual(talla.nombre, 'U')

    def test_buscar_alias_inexistente_retorna_none(self):
        self.assertIsNone(Talla.buscar_por_alias('XXXXXXXXXXXXX'))

    def test_buscar_alias_none_retorna_none(self):
        self.assertIsNone(Talla.buscar_por_alias(None))

    def test_talla_unique(self):
        # No se puede crear otra talla con el mismo nombre
        with self.assertRaises(Exception):
            Talla.objects.create(nombre='M', orden=999)

    def test_talla_orden(self):
        nombres = list(Talla.objects.filter(activa=True).order_by('orden').values_list('nombre', flat=True))
        self.assertEqual(nombres[0], 'XS')
        self.assertEqual(nombres[1], 'S')


# ─────────────────────────────────────────────────────────────
# Sección F: restricción de unicidad en Producto
# ─────────────────────────────────────────────────────────────

class TestProductoUnicidad(TestCase):

    def setUp(self):
        self.cat, _ = Categoria.objects.get_or_create(nombre='Vestidos Test')
        self.color, _ = Color.objects.get_or_create(nombre='Rojo Test', defaults={'codigo_hex': '#FF0000'})
        self.modelo, _ = Modelo.objects.get_or_create(nombre='Modelo Test Unicidad')
        self.tela, _ = Tela.objects.get_or_create(nombre='Saten Test')
        self.talla = Talla.objects.filter(nombre='M').first()

    def _make_producto(self, **kwargs):
        defaults = dict(
            categoria=self.cat,
            color=self.color,
            modelo=self.modelo,
            tela=self.tela,
            talla='M',
            talla_obj=self.talla,
            precio_venta=1000,
        )
        defaults.update(kwargs)
        return Producto.objects.create(**defaults)

    def test_primera_variante_se_crea(self):
        p = self._make_producto()
        self.assertIsNotNone(p.pk)

    def test_variante_duplicada_falla(self):
        self._make_producto()
        with self.assertRaises(IntegrityError):
            # Mismo modelo+color+tela+talla_obj → falla por UniqueConstraint
            from django.db import connection
            # Need to bypass model.save() SKU generation quirk — use atomic
            from django.db import transaction
            with transaction.atomic():
                self._make_producto()

    def test_sin_talla_obj_no_aplica_restriccion(self):
        # Si talla_obj es NULL, la restricción no aplica
        p1 = self._make_producto(talla_obj=None)
        p2 = self._make_producto(talla_obj=None)  # debe poder crearse
        self.assertNotEqual(p1.pk, p2.pk)

    def test_sin_modelo_no_aplica_restriccion(self):
        # Si modelo es NULL, la restricción no aplica
        p1 = self._make_producto(modelo=None)
        p2 = self._make_producto(modelo=None)
        self.assertNotEqual(p1.pk, p2.pk)

    def test_diferente_color_puede_crearse(self):
        self._make_producto()
        color2 = Color.objects.create(nombre='Azul', codigo_hex='#0000FF')
        p2 = self._make_producto(color=color2)
        self.assertIsNotNone(p2.pk)

    def test_diferente_talla_puede_crearse(self):
        self._make_producto()
        talla_l = Talla.objects.filter(nombre='L').first()
        p2 = self._make_producto(talla='L', talla_obj=talla_l)
        self.assertIsNotNone(p2.pk)


# ─────────────────────────────────────────────────────────────
# Sección E: extensión del Modelo
# ─────────────────────────────────────────────────────────────

class TestModeloExtendido(TestCase):

    def test_modelo_referencia(self):
        m = Modelo.objects.create(nombre='Vestido XV', referencia='XV-001')
        self.assertEqual(m.referencia, 'XV-001')

    def test_modelo_es_especial(self):
        m = Modelo.objects.create(nombre='Hechura Especial', es_especial=True)
        self.assertTrue(m.es_especial)

    def test_modelo_categoria_fk(self):
        cat, _ = Categoria.objects.get_or_create(nombre='Novias Prueba Ext')
        m = Modelo.objects.create(nombre='Modelo Novia Test Ext', categoria=cat)
        self.assertEqual(m.categoria.nombre, 'Novias Prueba Ext')

    def test_modelo_normalizacion_nombre(self):
        m = Modelo.objects.create(nombre='festivo LARGO')
        self.assertEqual(m.nombre, 'Festivo Largo')


# ─────────────────────────────────────────────────────────────
# APIs de catálogo (via cliente HTTP)
# ─────────────────────────────────────────────────────────────

class TestCatalogAPIs(TestCase):

    def setUp(self):
        from django.contrib.auth.models import Group
        self.user = User.objects.create_user('test_cat', password='pass')
        grp, _ = Group.objects.get_or_create(name='Inventario')
        self.user.groups.add(grp)
        self.client = Client()
        self.client.force_login(self.user)
        # Set active_profile in session (ProfileMiddleware reads this)
        session = self.client.session
        session['active_profile_id'] = self.user.pk
        session.save()

    def test_api_listar_tallas(self):
        resp = self.client.get('/api/tallas/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'ok')
        nombres = [t['nombre'] for t in data['tallas']]
        self.assertIn('M', nombres)
        self.assertIn('S', nombres)

    def test_api_crear_talla_nueva(self):
        resp = self.client.post(
            '/api/crear-talla/',
            data=json.dumps({'nombre': '38-EU'}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'ok')
        # Talla names are stored as-is (not normalized) to preserve e.g. "XS", "2XL"
        self.assertTrue(Talla.objects.filter(nombre='38-EU').exists())

    def test_api_crear_talla_duplicada(self):
        resp = self.client.post(
            '/api/crear-talla/',
            data=json.dumps({'nombre': 'M'}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()['status'], 'blocked')

    def test_api_crear_talla_alias_existente(self):
        # 'ch' is an alias of 'S' — should be blocked
        resp = self.client.post(
            '/api/crear-talla/',
            data=json.dumps({'nombre': 'ch'}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()['status'], 'blocked')

    def test_api_listar_modelos(self):
        Modelo.objects.create(nombre='Sirena Test')
        resp = self.client.get('/api/modelos/')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        nombres = [m['nombre'] for m in data['modelos']]
        self.assertIn('Sirena Test', nombres)

    def test_api_crear_modelo(self):
        resp = self.client.post(
            '/api/crear-modelo/',
            data=json.dumps({'nombre': 'Modelo Nuevo'}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Modelo.objects.filter(nombre='Modelo Nuevo').exists())

    def test_api_crear_modelo_duplicado(self):
        Modelo.objects.create(nombre='Modelo Existente')
        resp = self.client.post(
            '/api/crear-modelo/',
            data=json.dumps({'nombre': 'Modelo Existente'}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()['status'], 'blocked')


# ─────────────────────────────────────────────────────────────
# Regresión R-UNIQUE-001: get_or_create_normalizado no debe
# disparar UNIQUE constraint cuando el modelo normaliza en save().
# Escenario: nombre en minúscula ingresado por usuario vs nombre
# en title-case almacenado tras normalización.
# ─────────────────────────────────────────────────────────────

class TestCatalogoManagerRegresion(TestCase):
    """Prueba de regresión para el bug UNIQUE constraint en Categoria y Color.

    Antes del fix: get_or_create(nombre='sin definir') → GET fallaba
    (DB tenía 'Sin Definir') → INSERT → save() normalizaba → UNIQUE crash.
    """

    def test_get_or_create_normalizado_categoria_lowercase(self):
        """get_or_create_normalizado no falla con entrada sin normalizar.

        El escenario crítico: DB ya tiene 'Sin Definir' (lo que save() produce).
        get_or_create_normalizado('sin definir') debe hacer GET exitoso, no INSERT.
        Antes del fix: GET fallaba → INSERT → save() colisionaba → UNIQUE crash.
        """
        # Garantizar que ya existe el registro normalizado (simula estado de producción)
        Categoria.objects.get_or_create(nombre='Sin Definir')

        # Llamada con minúscula — debe encontrar el existente sin IntegrityError
        cat1, created1 = Categoria.objects.get_or_create_normalizado('sin definir')
        self.assertFalse(created1, "Debe encontrar el existente, no crear uno nuevo")
        self.assertEqual(cat1.nombre, 'Sin Definir')

        # Llamada con mayúsculas — mismo resultado
        cat2, created2 = Categoria.objects.get_or_create_normalizado('SIN DEFINIR')
        self.assertFalse(created2)
        self.assertEqual(cat1.pk, cat2.pk)

    def test_get_or_create_normalizado_color_lowercase(self):
        """Mismo escenario para Color."""
        Color.objects.get_or_create(nombre='Azul Marino')

        c1, created1 = Color.objects.get_or_create_normalizado('azul marino')
        self.assertFalse(created1, "Debe encontrar el existente, no crear uno nuevo")
        self.assertEqual(c1.nombre, 'Azul Marino')

        c2, created2 = Color.objects.get_or_create_normalizado('AZUL MARINO')
        self.assertFalse(created2)
        self.assertEqual(c1.pk, c2.pk)

    def test_get_default_categoria(self):
        """get_default() devuelve siempre el mismo objeto normalizado."""
        d1 = Categoria.objects.get_default()
        d2 = Categoria.objects.get_default()
        self.assertEqual(d1.pk, d2.pk)
        self.assertEqual(d1.nombre, 'Sin Definir')

    def test_api_crear_producto_rapido_no_unique_crash(self):
        """api_crear_producto_rapido no debe fallar con categoría en minúscula."""
        from django.contrib.auth.models import User, Group
        user = User.objects.create_user(username='v2', password='pass')
        g, _ = Group.objects.get_or_create(name='Vendedor')
        user.groups.add(g)
        self.client.login(username='v2', password='pass')
        session = self.client.session
        session['active_profile_id'] = user.id
        session.save()

        import json
        # Primera llamada crea 'Sin Definir'
        r1 = self.client.post(
            '/api/producto-rapido/',
            data=json.dumps({'categoria': 'sin definir', 'color': 'sin definir',
                             'precio': 100, 'estado': 'TIENDA'}),
            content_type='application/json',
        )
        self.assertEqual(r1.status_code, 200, r1.content.decode())

        # Segunda llamada no debe disparar IntegrityError
        r2 = self.client.post(
            '/api/producto-rapido/',
            data=json.dumps({'categoria': 'SIN DEFINIR', 'color': 'SIN DEFINIR',
                             'precio': 200, 'estado': 'TIENDA'}),
            content_type='application/json',
        )
        self.assertEqual(r2.status_code, 200, r2.content.decode())
