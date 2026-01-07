from django.db import models

class Proveedor(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    contacto = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return self.nombre

class Categoria(models.Model):
    nombre = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.nombre

class Modelo(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.TextField(blank=True)

    def __str__(self):
        return self.nombre

class Tela(models.Model):
    nombre = models.CharField(max_length=100)
    proveedor = models.ForeignKey(Proveedor, on_delete=models.CASCADE)
    codigo_proveedor = models.CharField(max_length=50)

    class Meta:
        unique_together = ('proveedor', 'codigo_proveedor')

    def __str__(self):
        return f"{self.nombre} ({self.proveedor.nombre})"

class Color(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    codigo_hex = models.CharField(max_length=7, blank=True, help_text="Ej: #FF5733")

    def __str__(self):
        return self.nombre

class Producto(models.Model):
    sku = models.CharField(max_length=100, unique=True, blank=True, help_text="Stock Keeping Unit, se generará automáticamente")
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

    class Meta:
        unique_together = ('categoria', 'modelo', 'tela', 'color', 'talla')

    def save(self, *args, **kwargs):
        # Primero, guarda la instancia para asegurarte de que todos los FK tienen un ID.
        # Si es un objeto nuevo, no tendrá ID hasta después del primer guardado.
        super().save(*args, **kwargs)
        if not self.sku:
            # Ahora que estamos seguros de que existen los IDs, los usamos para el SKU.
            # Ej: CAT1-MOD3-TELA5-COL10-M
            self.sku = f"CAT{self.categoria.id}-MOD{self.modelo.id}-TELA{self.tela.id}-COL{self.color.id}-{self.talla.upper()}"
            # Guardamos de nuevo para persistir el SKU. Evitamos la recursión infinita
            # ya que ahora el campo `sku` ya no está vacío.
            kwargs['force_insert'] = False # No intentes insertar de nuevo
            super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.modelo.nombre} {self.tela.nombre} {self.color.nombre} - Talla: {self.talla}"
