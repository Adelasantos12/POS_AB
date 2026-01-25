from django.db import models
from django.conf import settings
from django.utils import timezone


class Tienda(models.Model):
    """Tienda o sucursal del negocio"""
    nombre = models.CharField(max_length=100, unique=True)
    direccion = models.TextField(blank=True)
    telefono = models.CharField(max_length=20, blank=True)
    activa = models.BooleanField(default=True)
    
    def __str__(self):
        return self.nombre


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
    estado = models.CharField(max_length=20, choices=ESTADOS, default='TIENDA')
    foto = models.ImageField(upload_to='productos/', blank=True, null=True)
    qr_code = models.ImageField(upload_to='qrs/', blank=True, null=True)
    barcode_image = models.ImageField(upload_to='barcodes/', blank=True, null=True)

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
    numero_ticket = models.CharField(max_length=20, unique=True, blank=True)
    
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
            pedido.estado_pago = 'PARCIAL' if total_pagado > pedido.precio * 0.3 else 'APARTADO'
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
