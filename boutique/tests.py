from django.test import TestCase
from boutique.models import Producto, Categoria, Modelo, Tela, Color, Proveedor

class ProductoModelTest(TestCase):
    def setUp(self):
        self.proveedor = Proveedor.objects.create(nombre="Proveedor 1")
        self.categoria = Categoria.objects.create(nombre="Categoria 1")
        self.modelo = Modelo.objects.create(nombre="Modelo 1")
        self.tela = Tela.objects.create(nombre="Tela 1", proveedor=self.proveedor, codigo_proveedor="T1")
        self.color = Color.objects.create(nombre="Color 1", codigo_hex="#FFFFFF")

    def test_producto_str(self):
        """Verifica que la representación en cadena sea correcta."""
        producto = Producto.objects.create(
            categoria=self.categoria,
            modelo=self.modelo,
            tela=self.tela,
            color=self.color,
            talla="m",
            precio_venta=100.00
        )
        expected_str = "Modelo 1 Tela 1 Color 1 - Talla: m"
        self.assertEqual(str(producto), expected_str)

    def test_producto_sku_generation(self):
        """Verifica que el SKU se genere automáticamente al crear un producto."""
        producto = Producto.objects.create(
            categoria=self.categoria,
            modelo=self.modelo,
            tela=self.tela,
            color=self.color,
            talla="l",
            precio_venta=150.00
        )
        expected_sku = f"CAT{self.categoria.id}-MOD{self.modelo.id}-TELA{self.tela.id}-COL{self.color.id}-L"
        self.assertEqual(producto.sku, expected_sku)

    def test_producto_str_defensive(self):
        """Verifica que __str__ maneje relaciones faltantes de forma defensiva."""
        producto = Producto(talla="s")
        # En este punto, modelo, tela y color son None
        rep = str(producto)
        self.assertIn("Sin modelo", rep)
        self.assertIn("Sin tela", rep)
        self.assertIn("Sin color", rep)
        self.assertIn("Talla: s", rep)
