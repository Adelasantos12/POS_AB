from django.db import models

class Proveedor(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    contacto = models.CharField(max_length=100, blank=True)
    def __str__(self): return self.nombre

class Categoria(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    def __str__(self): return self.nombre

class Modelo(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.TextField(blank=True)
    def __str__(self): return self.nombre

class Tela(models.Model):
    nombre = models.CharField(max_length=100)
    proveedor = models.ForeignKey(Proveedor, on_delete=models.CASCADE)
    codigo_proveedor = models.CharField(max_length=50)
    class Meta: unique_together = ('proveedor', 'codigo_proveedor')
    def __str__(self): return f"{self.nombre} ({self.proveedor.nombre})"

class Color(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    codigo_hex = models.CharField(max_length=7, blank=True, help_text="Ej: #FF5733")
    def __str__(self): return self.nombre

class Producto(models.Model):
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
        if not self.sku:
            cat_id = self.categoria_id or 0
            mod_id = self.modelo_id or 0
            tela_id = self.tela_id or 0
            col_id = self.color_id or 0
            talla_code = (self.talla or 'U').upper()
            self.sku = f"CAT{cat_id}-MOD{mod_id}-TELA{tela_id}-COL{col_id}-{talla_code}"
        super().save(*args, **kwargs)

    def __str__(self):
        modelo = getattr(self.modelo, 'nombre', 'Sin modelo')
        tela = getattr(self.tela, 'nombre', 'Sin tela')
        color = getattr(self.color, 'nombre', 'Sin color')
        return f"{modelo} {tela} {color} - Talla: {self.talla}"
