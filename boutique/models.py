from django.db import models
from django.conf import settings
from django.utils import timezone
from decimal import Decimal


class Tienda(models.Model):
    """Tienda o sucursal del negocio"""
    nombre = models.CharField(max_length=100, unique=True)
    direccion = models.TextField(blank=True)
    telefono = models.CharField(max_length=20, blank=True)
    activa = models.BooleanField(default=True)
    
    def __str__(self):
        return self.nombre


class ConfiguracionTienda(models.Model):
    """Configuración global de la tienda (Singleton)"""
    nombre_comercial = models.CharField(max_length=200, default="Adelé Boutique")
    razon_social = models.CharField(max_length=200, blank=True)
    rfc = models.CharField(max_length=20, blank=True, verbose_name="RFC")
    direccion = models.TextField(blank=True)
    telefono_whatsapp = models.CharField(max_length=20, blank=True, verbose_name="Teléfono/WhatsApp")
    email = models.EmailField(blank=True)
    logo = models.ImageField(upload_to='logos/', blank=True, null=True)

    # Políticas
    politica_cambios = models.TextField(blank=True, verbose_name="Políticas de Cambios/Devoluciones")
    politica_apartados = models.TextField(blank=True, verbose_name="Políticas de Apartados")

    # Folios
    prefijo_sucursal = models.CharField(max_length=10, default="GDL", help_text="Ej: GDL")

    class Meta:
        verbose_name = "Configuración de la Tienda"
        verbose_name_plural = "Configuración de la Tienda"

    def __str__(self):
        return self.nombre_comercial

    @classmethod
    def get_solo(cls):
        obj, created = cls.objects.get_or_create(pk=1)
        return obj


class Permiso(models.Model):
    """Permisos atómicos del sistema"""
    PERMISOS = [
        ('abrir_caja', 'Puede abrir caja'),
        ('vender', 'Puede realizar ventas'),
        ('cobrar', 'Puede cobrar'),
        ('editar_inventario', 'Puede editar inventario'),
        ('ver_reportes', 'Puede ver reportes'),
        ('gestionar_usuarios', 'Puede gestionar usuarios'),
        ('ver_todo', 'Acceso total'),
    ]
    codigo = models.CharField(max_length=50, unique=True, choices=PERMISOS)
    descripcion = models.CharField(max_length=100)
    
    def __str__(self):
        return self.get_codigo_display()


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
    class Meta:
        verbose_name = "Modelo de Producto"
        verbose_name_plural = "Modelos de Productos"
    def __str__(self): return self.nombre

class Tela(models.Model):
    """Catálogo de tipos de tela con código de proveedor"""
    nombre = models.CharField(max_length=100)
    proveedor = models.ForeignKey(Proveedor, on_delete=models.CASCADE, null=True, blank=True)
    codigo_proveedor = models.CharField(max_length=50, blank=True)
    descripcion = models.TextField(blank=True, help_text="Características de la tela")
    es_predefinida = models.BooleanField(default=False, help_text="Telas del catálogo base")
    activa = models.BooleanField(default=True)
    
    class Meta: 
        unique_together = ('nombre', 'proveedor')
    
    def __str__(self): 
        if self.proveedor:
            return f"{self.nombre} ({self.proveedor.nombre})"
        return self.nombre


class Color(models.Model):
    """Catálogo de colores con muestra visual"""
    nombre = models.CharField(max_length=100, unique=True)
    codigo_hex = models.CharField(max_length=7, default="#CCCCCC", help_text="Ej: #FF5733")
    familia = models.CharField(max_length=50, blank=True, help_text="Ej: Rosa, Azul, Verde")
    es_predefinido = models.BooleanField(default=False, help_text="Colores del catálogo base")
    activo = models.BooleanField(default=True)
    orden = models.IntegerField(default=0, help_text="Orden de aparición")
    
    class Meta:
        ordering = ['familia', 'orden', 'nombre']
    
    def __str__(self): 
        return self.nombre

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
    stock_teorico = models.IntegerField(default=0)
    vendible_sin_stock = models.BooleanField(default=False)
    pendiente_regularizacion = models.BooleanField(default=False)
    estado = models.CharField(max_length=20, choices=ESTADOS, default='TIENDA')
    foto = models.ImageField(upload_to='productos/', blank=True, null=True)
    qr_code = models.ImageField(upload_to='qrs/', blank=True, null=True)
    barcode_image = models.ImageField(upload_to='barcodes/', blank=True, null=True)

    # Rasgos adicionales para búsqueda amigable
    rasgo1 = models.CharField(max_length=100, blank=True, help_text="Ej: Manga Larga, Escote V")
    rasgo2 = models.CharField(max_length=100, blank=True, help_text="Ej: Seda, Estilo Sirena")

    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    class Meta:
        unique_together = ('categoria', 'modelo', 'tela', 'color', 'talla', 'rasgo1', 'rasgo2')
        verbose_name = "Variante (SKU)"
        verbose_name_plural = "Variantes (SKU)"
    def save(self, *args, **kwargs):
        is_new = self.pk is None

        # Generar SKU si no existe
        if not self.sku:
            import uuid
            # Usamos un prefijo amigable + parte de UUID para asegurar unicidad si faltan campos
            prefix = "PROD"
            if self.categoria and hasattr(self.categoria, 'nombre'):
                prefix = self.categoria.nombre[:3].upper()
            self.sku = f"{prefix}-{uuid.uuid4().hex[:6].upper()}"

        # Marcar como pendiente si tiene valores placeholder
        cat_nombre = getattr(self.categoria, 'nombre', '') if self.categoria else ''
        color_nombre = getattr(self.color, 'nombre', '') if self.color else ''
        if cat_nombre == "Sin definir" or color_nombre == "Sin definir":
            self.pendiente_regularizacion = True

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
            buffer.seek(0)
            filename = f"qr-{self.sku}.png"
            self.qr_code.save(filename, File(buffer), save=False)

        # Generar Código de Barras si no existe (Code 128)
        if not self.barcode_image or is_new:
            try:
                import barcode
                from barcode.writer import ImageWriter
                from io import BytesIO
                from django.core.files import File

                CODE128 = barcode.get_barcode_class('code128')
                buffer = BytesIO()
                # Asegurar que se escriba el texto para que sea legible
                barcode_instance = CODE128(self.sku, writer=ImageWriter())
                barcode_instance.write(buffer, options={
                    "write_text": True,
                    "module_height": 15.0,
                    "text_distance": 5.0,
                    "font_size": 10
                })
                buffer.seek(0)

                filename = f"barcode-{self.sku}.png"
                # Eliminar imagen previa si existe y es cambio
                if self.barcode_image:
                    self.barcode_image.delete(save=False)
                self.barcode_image.save(filename, File(buffer), save=False)
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Error generando barcode: {e}")

        super().save(*args, **kwargs)
    def __str__(self):
        cat_nombre = self.categoria.nombre if self.categoria else "Sin Categoria"
        modelo_str = self.modelo.nombre if self.modelo else "Sin Modelo"
        tela_str = self.tela.nombre if self.tela else "Sin Tela"
        color_nombre = self.color.nombre if self.color else "Sin Color"
        return f"{cat_nombre} - {modelo_str} {tela_str} {color_nombre} ({self.talla})"

class Cliente(models.Model):
    nombre = models.CharField(max_length=100)
    email = models.EmailField(blank=True)
    telefono = models.CharField(max_length=20, blank=True)
    def __str__(self): return self.nombre

class Ticket(models.Model):
    """Tickets persistentes y reimprimibles (snapshot)"""
    TIPOS = [
        ('VENTA', 'Venta'),
        ('APARTADO', 'Apartado'),
        ('PEDIDO', 'Pedido/Hechura'),
        ('AJUSTE', 'Ajuste'),
        ('DEVOLUCION', 'Devolución'),
    ]
    ESTADOS = [
        ('EMITIDO', 'Emitido'),
        ('CANCELADO', 'Cancelado'),
        ('REIMPRESO', 'Reimpreso'),
    ]

    folio = models.CharField(max_length=30, unique=True, blank=True)
    tipo = models.CharField(max_length=20, choices=TIPOS, default='VENTA')
    estado = models.CharField(max_length=20, choices=ESTADOS, default='EMITIDO')
    fecha_hora = models.DateTimeField(auto_now_add=True)

    # Datos de la Tienda al momento de emitir (snapshot parcial)
    sucursal_nombre = models.CharField(max_length=100, blank=True)
    cajero_nombre = models.CharField(max_length=100, blank=True)

    # Totales
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    descuento_total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    impuestos = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_pagado = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    cambio = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Datos del Cliente al momento
    cliente_nombre = models.CharField(max_length=200, blank=True)
    cliente_telefono = models.CharField(max_length=20, blank=True)

    # Snapshot completo en JSON para máxima fidelidad histórica
    snapshot_json = models.JSONField(null=True, blank=True, help_text="Copia íntegra de ítems, precios y datos al emitir")

    # Relaciones (opcionales para trazabilidad viva)
    venta = models.ForeignKey('Venta', on_delete=models.SET_NULL, null=True, blank=True, related_name='tickets_asociados')
    apartado = models.ForeignKey('Apartado', on_delete=models.SET_NULL, null=True, blank=True, related_name='tickets_asociados')
    pedido = models.ForeignKey('Pedido', on_delete=models.SET_NULL, null=True, blank=True, related_name='tickets_relacionados')
    novia = models.ForeignKey('Novia', on_delete=models.SET_NULL, null=True, blank=True, related_name='tickets_relacionados')

    def save(self, *args, **kwargs):
        if not self.folio:
            config = ConfiguracionTienda.get_solo()
            prefix = config.prefijo_sucursal
            today_str = timezone.now().strftime('%Y%m%d')

            # Formato: PREFIX-YYYYMMDD-####
            from django.db import transaction
            with transaction.atomic():
                # Contar tickets del mismo día para el consecutivo
                count = Ticket.objects.filter(fecha_hora__date=timezone.now().date()).count() + 1
                self.folio = f"{prefix}-{today_str}-{count:04d}"
        super().save(*args, **kwargs)

    def __str__(self): return self.folio

    def populate_from_obj(self, obj):
        """Pobla el ticket desde una Venta o Apartado"""
        from django.core.serializers.json import DjangoJSONEncoder
        import json

        self.total = obj.total
        self.subtotal = obj.total # Ajustar si hay desglose real
        self.cliente_nombre = getattr(obj, 'cliente_nombre', '') or (obj.cliente.nombre if hasattr(obj, 'cliente') and obj.cliente else '')

        if hasattr(obj, 'anticipo'):
            self.total_pagado = obj.anticipo
            self.cambio = 0

        # Generar snapshot JSON
        items_data = []
        if hasattr(obj, 'items'):
            for item in obj.items.all():
                desc = str(item.producto) if hasattr(item, 'producto') and item.producto else item.descripcion
                items_data.append({
                    'descripcion': desc,
                    'cantidad': item.cantidad,
                    'precio_unitario': float(item.precio_unitario),
                    'subtotal': float(item.subtotal if hasattr(item, 'subtotal') else item.cantidad * item.precio_unitario)
                })

        snapshot = {
            'folio': self.folio,
            'fecha': self.fecha_hora.isoformat(),
            'cliente': self.cliente_nombre,
            'total': float(self.total),
            'items': items_data
        }
        self.snapshot_json = snapshot
        self.save()

class TicketItem(models.Model):
    """Desglose de ítems en el ticket (snapshot)"""
    ticket = models.ForeignKey(Ticket, related_name='items', on_delete=models.CASCADE)
    descripcion = models.CharField(max_length=255)
    sku_snapshot = models.CharField(max_length=100, blank=True)
    cantidad = models.PositiveIntegerField(default=1)
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    descuento = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)

    # Atributos snapshot
    modelo = models.CharField(max_length=100, blank=True)
    color = models.CharField(max_length=100, blank=True)
    talla = models.CharField(max_length=50, blank=True)

    def __str__(self): return f"{self.descripcion} x {self.cantidad}"

class Venta(models.Model):
    vendedor = models.ForeignKey('auth.User', on_delete=models.PROTECT)
    cliente = models.ForeignKey(Cliente, on_delete=models.SET_NULL, null=True, blank=True)
    fecha = models.DateTimeField(auto_now_add=True)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    notas = models.TextField(blank=True)
    offline_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    ticket = models.ForeignKey(Ticket, on_delete=models.SET_NULL, null=True, blank=True, related_name='ventas')
    pedido = models.ForeignKey('Pedido', on_delete=models.SET_NULL, null=True, blank=True, related_name='ventas_asociadas')
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
    registrado_por = models.ForeignKey('auth.User', on_delete=models.PROTECT, null=True, blank=True)
    def __str__(self): return f"Pago de {self.monto} a Venta #{self.venta.id}"

class Auditoria(models.Model):
    """Auditoría centralizada para todas las acciones sensibles"""
    ACCIONES = [
        ('LOGIN_PERFIL', 'Selección de perfil'),
        ('LOGOUT', 'Cierre de sesión'),
        ('APERTURA_CAJA', 'Apertura de caja'),
        ('CIERRE_CAJA', 'Cierre de caja'),
        ('VENTA', 'Venta registrada'),
        ('PAGO', 'Pago registrado'),
        ('MOVIMIENTO_INV', 'Movimiento de inventario'),
        ('EDICION_PRODUCTO', 'Edición de producto'),
        ('ELIMINACION_PRODUCTO', 'Eliminación de producto'),
        ('CREACION_USUARIO', 'Creación de usuario'),
        ('EDICION_USUARIO', 'Edición de usuario'),
        ('CAMBIO_ROL', 'Cambio de rol'),
        ('EXPORTACION', 'Exportación de datos'),
    ]
    
    usuario = models.ForeignKey('auth.User', on_delete=models.CASCADE, related_name='auditorias')
    timestamp = models.DateTimeField(auto_now_add=True)
    accion = models.CharField(max_length=50, choices=ACCIONES)
    detalles = models.TextField(blank=True)
    tienda = models.ForeignKey(Tienda, on_delete=models.SET_NULL, null=True, blank=True)
    entidad_tipo = models.CharField(max_length=50, blank=True, help_text='Modelo afectado')
    entidad_id = models.IntegerField(null=True, blank=True, help_text='ID del objeto afectado')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    
    class Meta:
        ordering = ['-timestamp']
        verbose_name_plural = 'Auditorías'
    
    def __str__(self):
        return f"{self.usuario.username} - {self.get_accion_display()} - {self.timestamp}"


def registrar_auditoria(usuario, accion, detalles='', tienda=None, entidad=None, request=None):
    """Helper único para registrar auditoría en todo el sistema"""
    ip = None
    if request:
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        ip = x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')
    
    entidad_tipo = ''
    entidad_id = None
    if entidad:
        entidad_tipo = entidad.__class__.__name__
        entidad_id = entidad.pk
    
    return Auditoria.objects.create(
        usuario=usuario,
        accion=accion,
        detalles=detalles,
        tienda=tienda,
        entidad_tipo=entidad_tipo,
        entidad_id=entidad_id,
        ip_address=ip
    )

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

class Apartado(models.Model):
    """Módulo independiente de apartados"""
    ESTADOS = [
        ('VIGENTE', 'Vigente'),
        ('VENCIDO', 'Vencido'),
        ('CANCELADO', 'Cancelado'),
        ('ENTREGADO', 'Entregado'),
    ]

    cliente_nombre = models.CharField(max_length=200)
    cliente_telefono = models.CharField(max_length=20)
    notas = models.TextField(blank=True)

    estado = models.CharField(max_length=20, choices=ESTADOS, default='VIGENTE')
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_vencimiento = models.DateField(null=True, blank=True)

    # Totales
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    anticipo = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    saldo = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Links opcionales
    novia = models.ForeignKey('Novia', on_delete=models.SET_NULL, null=True, blank=True, related_name='apartados_independientes')
    pedido = models.ForeignKey('Pedido', on_delete=models.SET_NULL, null=True, blank=True, related_name='apartados')

    def save(self, *args, **kwargs):
        self.saldo = self.total - self.anticipo
        super().save(*args, **kwargs)

    def __str__(self): return f"Apartado {self.cliente_nombre} - {self.estado}"

class ApartadoItem(models.Model):
    apartado = models.ForeignKey(Apartado, related_name='items', on_delete=models.CASCADE)
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, null=True, blank=True)

    # Snapshots de atributos por si el producto cambia o se elimina
    descripcion = models.CharField(max_length=255)
    modelo = models.CharField(max_length=100, blank=True)
    color = models.CharField(max_length=100, blank=True)
    talla = models.CharField(max_length=50, blank=True)

    cantidad = models.PositiveIntegerField(default=1)
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self): return self.descripcion

class CorteCaja(models.Model):
    """Caja desacoplada del usuario - pertenece a tienda y fecha"""
    tienda = models.ForeignKey(Tienda, on_delete=models.PROTECT, null=True, blank=True)
    abierto_por = models.ForeignKey('auth.User', on_delete=models.PROTECT, related_name='cajas_abiertas')
    fecha_apertura = models.DateTimeField(auto_now_add=True)
    fecha_cierre = models.DateTimeField(null=True, blank=True)
    monto_apertura = models.DecimalField(max_digits=10, decimal_places=2)

    # Valores esperados (calculados por el sistema)
    efectivo_esperado = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tarjeta_esperada = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Valores reales (ingresados por el vendedor)
    efectivo_real = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    tarjeta_real = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    diferencia = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    observaciones = models.TextField(blank=True)
    cerrado = models.BooleanField(default=False)

    def __str__(self):
        return f"Corte {self.fecha_apertura.strftime('%Y-%m-%d %H:%M')} - {self.abierto_por.username}"



class MovimientoInventario(models.Model):
    """El stock no se edita directamente. Es resultado de movimientos."""
    TIPOS = [
        ('ENTRADA', 'Entrada'),
        ('SALIDA', 'Salida'),
        ('AJUSTE', 'Ajuste'),
        ('VENTA', 'Venta'),
        ('DEVOLUCION', 'Devolución'),
    ]
    MOTIVOS = [
        ('COMPRA', 'Compra a proveedor'),
        ('VENTA', 'Venta a cliente'),
        ('MERMA', 'Merma/Pérdida'),
        ('AJUSTE_INVENTARIO', 'Ajuste de inventario'),
        ('DEVOLUCION_PROVEEDOR', 'Devolución a proveedor'),
        ('DEVOLUCION_CLIENTE', 'Devolución de cliente'),
        ('TRANSFERENCIA', 'Transferencia entre tiendas'),
    ]
    
    producto = models.ForeignKey(Producto, on_delete=models.PROTECT, related_name='movimientos')
    tipo = models.CharField(max_length=20, choices=TIPOS)
    cantidad = models.IntegerField()  # Positivo para entradas, negativo para salidas
    motivo = models.CharField(max_length=30, choices=MOTIVOS)
    notas = models.TextField(blank=True)
    
    # Trazabilidad
    perfil_activo = models.ForeignKey('auth.User', on_delete=models.PROTECT)
    tienda = models.ForeignKey(Tienda, on_delete=models.PROTECT, null=True, blank=True)
    venta = models.ForeignKey(Venta, on_delete=models.SET_NULL, null=True, blank=True)
    fecha = models.DateTimeField(auto_now_add=True)
    
    # Stock después del movimiento (para histórico)
    stock_resultante = models.IntegerField()
    
    class Meta:
        ordering = ['-fecha']
    
    def __str__(self):
        return f"{self.get_tipo_display()} {self.cantidad} x {self.producto.sku}"
    
    def save(self, *args, **kwargs):
        # Calcular stock resultante (basado en stock_teorico para permitir negativos)
        if not self.stock_resultante:
            self.stock_resultante = self.producto.stock_teorico + self.cantidad
        super().save(*args, **kwargs)
        # Actualizar stock teórico del producto
        self.producto.stock_teorico = self.stock_resultante
        self.producto.save(update_fields=['stock_teorico'])



# ============================================================
# SISTEMA DE AGENDA Y NOVIAS
# ============================================================

class Novia(models.Model):
    """Perfil de novia - cabeza de grupo"""
    nombre = models.CharField(max_length=200)
    activo = models.BooleanField(default=True)
    telefono = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    
    # Fechas importantes
    fecha_boda = models.DateField()
    fecha_prueba = models.DateField(null=True, blank=True, help_text="Día de prueba/ajustes")
    fecha_entrega = models.DateField(null=True, blank=True, help_text="Día de entrega")
    fecha_limite = models.DateField(null=True, blank=True, help_text="Fecha límite (antes de boda)")
    
    # Grupo de damas
    cantidad_damas = models.PositiveIntegerField(default=0)
    
    # Preferencias generales del grupo
    color_principal = models.ForeignKey(Color, on_delete=models.SET_NULL, null=True, blank=True, related_name='novias_color')
    tela_principal = models.ForeignKey(Tela, on_delete=models.SET_NULL, null=True, blank=True, related_name='novias_tela')
    modelo_principal = models.ForeignKey(Modelo, on_delete=models.SET_NULL, null=True, blank=True, related_name='novias_modelo')
    
    notas = models.TextField(blank=True)
    creado_por = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    # Medidas
    m_busto = models.CharField(max_length=50, blank=True, verbose_name="Busto")
    m_cintura = models.CharField(max_length=50, blank=True, verbose_name="Cintura")
    m_cadera = models.CharField(max_length=50, blank=True, verbose_name="Cadera")
    m_largo_total = models.CharField(max_length=50, blank=True, verbose_name="Largo Total")
    m_ancho_espalda = models.CharField(max_length=50, blank=True, verbose_name="Ancho Espalda")
    m_talle_delantero = models.CharField(max_length=50, blank=True, verbose_name="Talle Delantero")
    m_talle_trasero = models.CharField(max_length=50, blank=True, verbose_name="Talle Trasero")
    m_altura_busto = models.CharField(max_length=50, blank=True, verbose_name="Altura Busto")
    m_separacion_busto = models.CharField(max_length=50, blank=True, verbose_name="Separación Busto")
    m_notas_medidas = models.TextField(blank=True, verbose_name="Notas de Medidas")

    # Detalles para Hechura Especial
    modelo_especial = models.CharField(max_length=200, blank=True, help_text="Para modelos no en catálogo")
    color_especial = models.CharField(max_length=200, blank=True)
    tela_especial = models.CharField(max_length=200, blank=True)
    talla_especial = models.CharField(max_length=100, blank=True)
    
    class Meta:
        ordering = ['fecha_boda']
    
    def __str__(self):
        return f"{self.nombre} - Boda: {self.fecha_boda}"
    
    @property
    def total_pedidos(self):
        return self.pedidos.count()
    
    @property
    def total_pagado(self):
        return sum(p.total_pagado for p in self.pedidos.all())
    
    @property
    def total_pendiente(self):
        return sum(p.saldo_pendiente for p in self.pedidos.all())
    
    @property
    def resumen_grupo(self):
        """Genera resumen de todos los pedidos del grupo"""
        pedidos = self.pedidos.all()
        colores = set()
        telas = set()
        modelos = set()
        tallas = {}
        
        for p in pedidos:
            if p.color:
                colores.add(p.color.nombre)
            if p.tela:
                telas.add(p.tela.nombre)
            if p.modelo:
                modelos.add(p.modelo.nombre)
            if p.talla:
                tallas[p.talla] = tallas.get(p.talla, 0) + 1
        
        return {
            'colores': list(colores),
            'telas': list(telas),
            'modelos': list(modelos),
            'tallas': tallas,
            'total': pedidos.count()
        }


class Dama(models.Model):
    """Integrante del grupo de la novia"""
    novia = models.ForeignKey(Novia, on_delete=models.CASCADE, related_name='damas')
    nombre = models.CharField(max_length=200)
    activo = models.BooleanField(default=True)
    telefono = models.CharField(max_length=20, blank=True)
    
    # Personalización (puede diferir del grupo)
    color = models.ForeignKey(Color, on_delete=models.SET_NULL, null=True, blank=True)
    tela = models.ForeignKey(Tela, on_delete=models.SET_NULL, null=True, blank=True)
    modelo = models.ForeignKey(Modelo, on_delete=models.SET_NULL, null=True, blank=True)
    talla = models.CharField(max_length=10, blank=True)

    # Detalles para Hechura Especial
    modelo_especial = models.CharField(max_length=200, blank=True)
    color_especial = models.CharField(max_length=200, blank=True)
    tela_especial = models.CharField(max_length=200, blank=True)
    
    # Medidas
    m_busto = models.CharField(max_length=50, blank=True, verbose_name="Busto")
    m_cintura = models.CharField(max_length=50, blank=True, verbose_name="Cintura")
    m_cadera = models.CharField(max_length=50, blank=True, verbose_name="Cadera")
    m_largo_total = models.CharField(max_length=50, blank=True, verbose_name="Largo Total")
    m_ancho_espalda = models.CharField(max_length=50, blank=True, verbose_name="Ancho Espalda")
    m_talle_delantero = models.CharField(max_length=50, blank=True, verbose_name="Talle Delantero")
    m_talle_trasero = models.CharField(max_length=50, blank=True, verbose_name="Talle Trasero")
    m_altura_busto = models.CharField(max_length=50, blank=True, verbose_name="Altura Busto")
    m_separacion_busto = models.CharField(max_length=50, blank=True, verbose_name="Separación Busto")
    m_notas_medidas = models.TextField(blank=True, verbose_name="Notas de Medidas")

    notas_ajustes = models.TextField(blank=True, help_text="Notas de ajustes específicos")
    
    def __str__(self):
        return f"{self.nombre} (Grupo de {self.novia.nombre})"


class Pedido(models.Model):
    """Pedido de vestido - puede ser de novia o dama"""
    ESTADOS = [
        ('NUEVO', 'Nuevo'),
        ('PENDIENTE_TELA', 'Falta comprar tela'),
        ('TELA_COMPRADA', 'Tela comprada'),
        ('EN_CONFECCION', 'En confección'),
        ('LISTO', 'Listo en tienda'),
        ('ENTREGADO', 'Entregado'),
        ('CANCELADO', 'Cancelado'),
    ]
    
    ESTADOS_PAGO = [
        ('SIN_PAGO', 'Sin pago'),
        ('APARTADO', 'Apartado'),
        ('PARCIAL', 'Pago parcial'),
        ('LIQUIDADO', 'Liquidado'),
    ]
    
    # Puede ser para la novia o para una dama
    novia = models.ForeignKey(Novia, on_delete=models.CASCADE, related_name='pedidos')
    dama = models.ForeignKey(Dama, on_delete=models.SET_NULL, null=True, blank=True, related_name='pedidos')
    es_vestido_novia = models.BooleanField(default=False, help_text="Es el vestido de la novia")
    
    # Producto/características
    producto = models.ForeignKey(Producto, on_delete=models.SET_NULL, null=True, blank=True, help_text="Si ya existe en inventario")
    modelo = models.ForeignKey(Modelo, on_delete=models.SET_NULL, null=True, blank=True)
    color = models.ForeignKey(Color, on_delete=models.SET_NULL, null=True, blank=True)
    tela = models.ForeignKey(Tela, on_delete=models.SET_NULL, null=True, blank=True)
    talla = models.CharField(max_length=10, blank=True)
    
    # Imagen de referencia
    imagen_referencia = models.ImageField(upload_to='pedidos/', blank=True, null=True)
    
    # Precio y pagos
    precio = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    anticipo = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Estados
    estado = models.CharField(max_length=20, choices=ESTADOS, default='NUEVO')
    estado_pago = models.CharField(max_length=20, choices=ESTADOS_PAGO, default='SIN_PAGO')
    
    # Fechas
    fecha_entrega_estimada = models.DateField(null=True, blank=True)
    fecha_entrega_real = models.DateField(null=True, blank=True)
    
    # Notas
    notas = models.TextField(blank=True)
    notas_ajustes = models.TextField(blank=True)
    
    # Ticket/referencia
    ticket = models.ForeignKey(Ticket, on_delete=models.SET_NULL, null=True, blank=True, related_name='pedidos')
    numero_ticket = models.CharField(max_length=20, unique=True, blank=True)
    offline_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    
    # Tracking
    creado_por = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, related_name='pedidos_creados')
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-fecha_creacion']
    
    def save(self, *args, **kwargs):
        if not self.numero_ticket:
            import uuid
            self.numero_ticket = f"PED-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)
    
    def __str__(self):
        quien = "Novia" if self.es_vestido_novia else (self.dama.nombre if self.dama else "Dama")
        return f"{self.numero_ticket} - {quien} ({self.novia.nombre})"
    
    @property
    def total_pagado(self):
        return sum(p.monto for p in self.pagos_pedido.all())
    
    @property
    def saldo_pendiente(self):
        return self.precio - self.total_pagado
    
    @property
    def esta_pagado(self):
        return self.saldo_pendiente <= 0


class PagoPedido(models.Model):
    """Pagos asociados a un pedido"""
    METODOS = [
        ('EFECTIVO', 'Efectivo'),
        ('TARJETA', 'Tarjeta'),
        ('TRANSFERENCIA', 'Transferencia'),
    ]
    
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name='pagos_pedido')
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    metodo = models.CharField(max_length=20, choices=METODOS, default='EFECTIVO')
    fecha = models.DateTimeField(auto_now_add=True)
    registrado_por = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True)
    notas = models.CharField(max_length=200, blank=True)
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Actualizar estado de pago del pedido
        pedido = self.pedido
        total_pagado = pedido.total_pagado
        if total_pagado >= pedido.precio:
            pedido.estado_pago = 'LIQUIDADO'
        elif total_pagado > 0:
            pedido.estado_pago = 'PARCIAL' if total_pagado > pedido.precio * Decimal('0.3') else 'APARTADO'
        pedido.save(update_fields=['estado_pago'])
    
    def __str__(self):
        return f"${self.monto} - {self.pedido.numero_ticket}"


class CitaAgenda(models.Model):
    """Citas en el calendario"""
    TIPOS = [
        ('PRUEBA', 'Prueba de vestido'),
        ('AJUSTE', 'Ajustes'),
        ('ENTREGA', 'Entrega'),
        ('RECOGIDA', 'Recogida'),
        ('CONSULTA', 'Consulta nueva novia'),
        ('OTRO', 'Otro'),
    ]
    
    titulo = models.CharField(max_length=200)
    tipo = models.CharField(max_length=20, choices=TIPOS, default='CONSULTA')
    
    # Fecha y hora
    fecha = models.DateField()
    hora_inicio = models.TimeField()
    hora_fin = models.TimeField(null=True, blank=True)
    
    # Relacionado a novia/pedido (opcional)
    novia = models.ForeignKey(Novia, on_delete=models.CASCADE, null=True, blank=True, related_name='citas')
    pedido = models.ForeignKey(Pedido, on_delete=models.SET_NULL, null=True, blank=True, related_name='citas')
    
    # Info adicional para consultas nuevas
    nombre_cliente = models.CharField(max_length=200, blank=True)
    telefono_cliente = models.CharField(max_length=20, blank=True)
    cantidad_damas_esperadas = models.PositiveIntegerField(default=0)
    
    notas = models.TextField(blank=True)
    completada = models.BooleanField(default=False)
    
    creado_por = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['fecha', 'hora_inicio']
    
    def __str__(self):
        return f"{self.fecha} {self.hora_inicio} - {self.titulo}"


class NotaPedido(models.Model):
    """Notas de seguimiento de pedidos"""
    pedido = models.ForeignKey(Pedido, on_delete=models.CASCADE, related_name='notas_seguimiento')
    texto = models.TextField()
    creado_por = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True)
    fecha = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-fecha']
    
    def __str__(self):
        return f"Nota {self.fecha.strftime('%d/%m')} - {self.pedido.numero_ticket}"
