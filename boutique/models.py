from django.db import models

class Proveedor(models.Model):
    """
    Representa a un proveedor de telas o insumos para la boutique.
    """
    nombre = models.CharField(max_length=100, unique=True)
    contacto = models.CharField(max_length=100, blank=True)
    def __str__(self): return self.nombre

class Categoria(models.Model):
    """
    Representa una categoría de productos (ej. Vestidos de Novia, Accesorios).
    """
    nombre = models.CharField(max_length=100, unique=True)
    def __str__(self): return self.nombre

class Modelo(models.Model):
    """
    Representa un diseño o modelo específico de prenda.
    """
    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.TextField(blank=True)
    def __str__(self): return self.nombre

class Tela(models.Model):
    """
    Representa un tipo de tela, asociada a un proveedor específico.
    """
    nombre = models.CharField(max_length=100)
    proveedor = models.ForeignKey(Proveedor, on_delete=models.CASCADE)
    codigo_proveedor = models.CharField(max_length=50)
    class Meta: unique_together = ('proveedor', 'codigo_proveedor')
    def __str__(self): return f"{self.nombre} ({self.proveedor.nombre})"

class Color(models.Model):
    """
    Representa un color disponible para las telas o productos.
    """
    nombre = models.CharField(max_length=100, unique=True)
    codigo_hex = models.CharField(max_length=7, blank=True, help_text="Ej: #FF5733")
    def __str__(self): return self.nombre

class Producto(models.Model):
    """
    Representa una variante específica (SKU) de un producto,
    definiendo la combinación de modelo, tela, color y talla.
    """
    sku = models.CharField(max_length=100, unique=True, blank=True)
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT)
    modelo = models.ForeignKey(Modelo, on_delete=models.PROTECT)
    tela = models.ForeignKey(Tela, on_delete=models.PROTECT)
    color = models.ForeignKey(Color, on_delete=models.PROTECT)
    talla = models.CharField(max_length=10)
    precio_venta = models.DecimalField(max_digits=10, decimal_places=2)
    cantidad_actual = models.PositiveIntegerField(default=0)
    vendible_sin_stock = models.BooleanField(default=False)
    foto = models.ImageField(upload_to='productos/', blank=True, null=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    class Meta: unique_together = ('categoria', 'modelo', 'tela', 'color', 'talla')
    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new and not self.sku:
            self.sku = f"CAT{self.categoria.id}-MOD{self.modelo.id}-TELA{self.tela.id}-COL{self.color.id}-{self.talla.upper()}"
            kwargs['force_insert'] = False
            super().save(update_fields=['sku'])
    def __str__(self): return f"{self.modelo.nombre} {self.tela.nombre} {self.color.nombre} - Talla: {self.talla}"
