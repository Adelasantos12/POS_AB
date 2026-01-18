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
    ESTADOS = [
        ('TIENDA', 'En Tienda'),
        ('APARTADO', 'Apartado'),
        ('PEDIDO', 'Sobre Pedido'),
    ]
    sku = models.CharField(max_length=100, unique=True, blank=True)
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT)
    modelo = models.ForeignKey(Modelo, on_delete=models.SET_NULL, null=True, blank=True)
    tela = models.ForeignKey(Tela, on_delete=models.SET_NULL, null=True, blank=True)
    color = models.ForeignKey(Color, on_delete=models.PROTECT)
    talla = models.CharField(max_length=10)
    precio_venta = models.DecimalField(max_digits=10, decimal_places=2)
    cantidad_actual = models.PositiveIntegerField(default=0)
    vendible_sin_stock = models.BooleanField(default=False)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='TIENDA')
    foto = models.ImageField(upload_to='productos/', blank=True, null=True)
    qr_code = models.ImageField(upload_to='qrs/', blank=True, null=True)

    # Rasgos adicionales para búsqueda amigable
    rasgo1 = models.CharField(max_length=100, blank=True, help_text="Ej: Manga Larga, Escote V")
    rasgo2 = models.CharField(max_length=100, blank=True, help_text="Ej: Seda, Estilo Sirena")

    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    class Meta: unique_together = ('categoria', 'modelo', 'tela', 'color', 'talla', 'rasgo1', 'rasgo2')
    def save(self, *args, **kwargs):
        is_new = self.pk is None

        # Generar SKU si no existe
        if not self.sku:
            import uuid
            # Usamos un prefijo amigable + parte de UUID para asegurar unicidad si faltan campos
            prefix = self.categoria.nombre[:3].upper() if self.categoria else "PROD"
            self.sku = f"{prefix}-{uuid.uuid4().hex[:6].upper()}"

        # Generar QR si no existe
        if not self.qr_code:
            import qrcode
            from io import BytesIO
            from django.core.files import File
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(self.sku)
            qr.make(fit=True)
            img = qr.make_image(fill='black', back_color='white')
            buffer = BytesIO()
            img.save(buffer, format='PNG')
            filename = f"qr-{self.sku}.png"
            self.qr_code.save(filename, File(buffer), save=False)

        super().save(*args, **kwargs)
    def __str__(self):
        modelo_str = self.modelo.nombre if self.modelo else "Sin Modelo"
        tela_str = self.tela.nombre if self.tela else "Sin Tela"
        return f"{self.categoria.nombre} - {modelo_str} {tela_str} {self.color.nombre} ({self.talla})"

class Cliente(models.Model):
    nombre = models.CharField(max_length=100)
    email = models.EmailField(blank=True)
    telefono = models.CharField(max_length=20, blank=True)
    def __str__(self): return self.nombre

class Venta(models.Model):
    vendedor = models.ForeignKey('auth.User', on_delete=models.PROTECT)
    cliente = models.ForeignKey(Cliente, on_delete=models.SET_NULL, null=True, blank=True)
    fecha = models.DateTimeField(auto_now_add=True)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    def __str__(self): return f"Venta #{self.id} - {self.fecha.strftime('%Y-%m-%d')}"

class ItemVenta(models.Model):
    venta = models.ForeignKey(Venta, related_name='items', on_delete=models.CASCADE)
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT)
    cantidad = models.PositiveIntegerField(default=1)
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)

class Pago(models.Model):
    METODOS = [('EFECTIVO', 'Efectivo'), ('TARJETA', 'Tarjeta'), ('TRANSFERENCIA', 'Transferencia')]
    venta = models.ForeignKey(Venta, related_name='pagos', on_delete=models.CASCADE)
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    metodo = models.CharField(max_length=20, choices=METODOS)
    fecha = models.DateTimeField(auto_now_add=True)
    def __str__(self): return f"Pago de {self.monto} a Venta #{self.venta.id}"

class Pedido(models.Model):
    ESTADOS = [('PENDIENTE', 'Pendiente'), ('EN_PROCESO', 'En Proceso'), ('LISTO', 'Listo'), ('ENTREGADO', 'Entregado')]
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT)
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT)
    cantidad = models.PositiveIntegerField(default=1)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='PENDIENTE')
    fecha_pedido = models.DateTimeField(auto_now_add=True)
    notas = models.TextField(blank=True)
    def __str__(self): return f"Pedido #{self.id} - {self.cliente.nombre}"

class Grupo(models.Model):
    ESTADOS = [('NEGOCIACION', 'En Negociación'), ('CONFIRMADO', 'Confirmado'), ('PRODUCCION', 'En Producción'), ('LISTO', 'Listo'), ('ENTREGADO', 'Entregado')]
    nombre = models.CharField(max_length=100)
    fecha_visita = models.DateField()
    fecha_entrega = models.DateField()
    evento = models.CharField(max_length=100)
    notas = models.TextField(blank=True)
    estatus = models.CharField(max_length=20, choices=ESTADOS, default='NEGOCIACION')
    def __str__(self): return self.nombre

class IntegranteGrupo(models.Model):
    grupo = models.ForeignKey(Grupo, related_name='integrantes', on_delete=models.CASCADE)
    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT)
    modelo_elegido = models.ForeignKey(Producto, on_delete=models.SET_NULL, null=True, blank=True)
    color = models.CharField(max_length=50, blank=True)
    tela = models.CharField(max_length=50, blank=True)
    talla_medida = models.CharField(max_length=50, blank=True)
    anticipo = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    saldo = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    def __str__(self): return f"{self.cliente.nombre} en {self.grupo.nombre}"
