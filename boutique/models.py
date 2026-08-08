from django.db import models, transaction
from django.db.models import Q, F
from django.conf import settings
from django.utils import timezone
from decimal import Decimal


class Secuencia(models.Model):
    """Contador atómico de folios por prefijo y fecha (reemplaza COUNT+1)"""
    prefijo = models.CharField(max_length=20)
    fecha = models.DateField()
    ultimo_numero = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = [('prefijo', 'fecha')]

    @classmethod
    def siguiente(cls, prefijo):
        hoy = timezone.now().date()
        with transaction.atomic():
            seq, created = cls.objects.get_or_create(
                prefijo=prefijo, fecha=hoy,
                defaults={'ultimo_numero': 1}
            )
            if not created:
                cls.objects.filter(prefijo=prefijo, fecha=hoy).update(
                    ultimo_numero=F('ultimo_numero') + 1
                )
                seq.refresh_from_db()
        return f"{prefijo}-{hoy.strftime('%Y%m%d')}-{seq.ultimo_numero:04d}"


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
    telefono2 = models.CharField(max_length=20, blank=True, verbose_name="Teléfono 2")
    email = models.EmailField(blank=True)
    logo = models.ImageField(upload_to='logos/', blank=True, null=True)

    # Políticas
    politica_cambios = models.TextField(blank=True, verbose_name="Políticas de Cambios/Devoluciones")
    politica_apartados = models.TextField(blank=True, verbose_name="Políticas de Apartados")
    horarios = models.TextField(blank=True, verbose_name="Horarios de atención", help_text="Ej: Lun-Vie 10:00-20:00")

    # Folios
    prefijo_sucursal = models.CharField(max_length=10, default="GDL", help_text="Ej: GDL")

    # ── Identidad de marca (IDENTITY SLOT) ────────────────────────────
    tagline = models.CharField(
        max_length=200, blank=True,
        default="Alta moda | Guadalajara | Santa Tere",
        verbose_name="Tagline",
        help_text="Ej: Alta moda nupcial · Cuernavaca",
    )
    color_primario = models.CharField(
        max_length=7, default="#9D174D",
        verbose_name="Color primario (hex)",
        help_text="Ej: #9D174D — controla botones, acentos y encabezado del ticket",
    )
    color_secundario = models.CharField(
        max_length=7, default="#F9A8D4",
        verbose_name="Color secundario (hex)",
        help_text="Ej: #F9A8D4 — gradientes y fondos suaves",
    )
    site_url = models.CharField(
        max_length=200, blank=True, default='',
        verbose_name="URL del sitio",
        help_text="Ej: https://pos.adeleboutique.com — se usa en el QR del ticket para llevar a la página de detalle del pedido",
    )

    class Meta:
        verbose_name = "Configuración de la Tienda"
        verbose_name_plural = "Configuración de la Tienda"

    def __str__(self):
        return self.nombre_comercial

    @property
    def receipt_rgb(self):
        """Tupla RGB fraccional (para ReportLab) derivada de color_primario."""
        try:
            h = (self.color_primario or "#9D174D").lstrip('#')
            return (int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255)
        except Exception:
            return (0.616, 0.090, 0.302)

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

class CatalogoManager(models.Manager):
    """Manager para catálogos con nombre único normalizado.

    Centraliza la normalización en get_or_create para que ningún llamador
    necesite recordar invocar normalizar_nombre() antes de consultar.
    """
    DEFAULT_NAME = 'Sin Definir'

    def get_or_create_normalizado(self, nombre, **kwargs):
        from .utils import normalizar_nombre
        nombre = normalizar_nombre(nombre) or self.DEFAULT_NAME
        return self.get_or_create(nombre=nombre, **kwargs)

    def get_default(self):
        obj, _ = self.get_or_create_normalizado(self.DEFAULT_NAME)
        return obj


class Categoria(models.Model):
    DEFAULT_NAME = 'Sin Definir'

    nombre = models.CharField(max_length=100, unique=True)

    objects = CatalogoManager()

    def save(self, *args, **kwargs):
        from .utils import normalizar_nombre
        self.nombre = normalizar_nombre(self.nombre)
        super().save(*args, **kwargs)

    def __str__(self): return self.nombre


class Talla(models.Model):
    """Catálogo controlado de tallas con alias para normalización (S = CH = ch)."""
    nombre = models.CharField(max_length=20, unique=True)
    aliases_json = models.JSONField(
        default=list, blank=True,
        help_text='Lista de alias aceptados. Ej: ["ch", "chico", "small"]'
    )
    orden = models.PositiveSmallIntegerField(default=0)
    activa = models.BooleanField(default=True)

    class Meta:
        ordering = ['orden', 'nombre']
        verbose_name = 'Talla'
        verbose_name_plural = 'Tallas'

    def __str__(self):
        return self.nombre

    @classmethod
    def buscar_por_alias(cls, raw: str):
        """Return the Talla whose nombre or aliases match `raw` (case-insensitive). Returns None if no match."""
        if not raw:
            return None
        raw_lower = raw.strip().lower()
        for talla in cls.objects.filter(activa=True):
            if talla.nombre.lower() == raw_lower:
                return talla
            if any(alias.lower() == raw_lower for alias in (talla.aliases_json or [])):
                return talla
        return None


class Modelo(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    descripcion = models.TextField(blank=True)
    # Catalog normalization fields
    referencia = models.CharField(max_length=100, blank=True, help_text='Número/código de referencia del modelo')
    foto_principal = models.ImageField(upload_to='modelos/', null=True, blank=True)
    categoria = models.ForeignKey(Categoria, on_delete=models.SET_NULL, null=True, blank=True, related_name='modelos')
    es_especial = models.BooleanField(default=False, help_text='Habilita campos adicionales para modelos hechos a medida')
    # Extra fields for special models
    combinacion_telas = models.TextField(blank=True)
    notas_confeccion = models.TextField(blank=True)
    codigo_especial = models.CharField(max_length=100, blank=True)

    class Meta:
        verbose_name = "Modelo de Producto"
        verbose_name_plural = "Modelos de Productos"

    def save(self, *args, **kwargs):
        from .utils import normalizar_nombre
        self.nombre = normalizar_nombre(self.nombre)
        super().save(*args, **kwargs)

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

    def save(self, *args, **kwargs):
        from .utils import normalizar_nombre
        self.nombre = normalizar_nombre(self.nombre)
        super().save(*args, **kwargs)

    def __str__(self):
        if self.proveedor:
            return f"{self.nombre} ({self.proveedor.nombre})"
        return self.nombre


class Medidas(models.Model):
    """Medidas detalladas del cliente (en cm)"""
    pedido = models.OneToOneField('Pedido', on_delete=models.CASCADE, related_name='medidas', null=True, blank=True)
    cliente = models.ForeignKey('Cliente', on_delete=models.CASCADE, related_name='medidas_historicas', null=True, blank=True)

    # Datos snapshot o para reuso
    cliente_nombre = models.CharField(max_length=200, blank=True)

    # Medidas en cm — primarias
    busto = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    cintura = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    cadera = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    largo_aproximado = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="Largo aprox.")
    # Medidas secundarias ampliadas
    hombro = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    brazo = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    espalda = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    talle_delantero = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    talle_trasero = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    altura_busto = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    separacion_busto = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    bajo_busto = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="Bajo busto")
    largo_talle = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="Largo talle")
    hombro_pezon = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="Hombro-pezón")
    hombro_bajo_busto = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="Hombro-bajo busto")

    observaciones = models.TextField(blank=True)
    notas = models.TextField(blank=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Medidas {self.cliente_nombre or (self.pedido.numero_ticket if self.pedido else 'S/N')}"


class Color(models.Model):
    """Catálogo de colores con muestra visual"""
    DEFAULT_NAME = 'Sin Definir'

    nombre = models.CharField(max_length=100, unique=True)
    codigo_hex = models.CharField(max_length=7, default="#CCCCCC", help_text="Ej: #FF5733")
    familia = models.CharField(max_length=50, blank=True, help_text="Ej: Rosa, Azul, Verde")
    es_predefinido = models.BooleanField(default=False, help_text="Colores del catálogo base")
    activo = models.BooleanField(default=True)
    orden = models.IntegerField(default=0, help_text="Orden de aparición")

    objects = CatalogoManager()

    class Meta:
        ordering = ['familia', 'orden', 'nombre']

    def save(self, *args, **kwargs):
        from .utils import normalizar_nombre
        self.nombre = normalizar_nombre(self.nombre)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nombre

RASGOS_ESTILO = ['Sin manga', 'Manga corta', 'Manga larga', 'Un hombro', 'Hombros descubiertos', 'Tirantes', 'Sin tirantes']
RASGOS_CORTE = ['Sirena', 'A-line', 'Princesa', 'Recto', 'Corto', 'Con cola', 'Globo', 'Crinolina']
RASGOS_ESCOTE = ['Escote V', 'Escote corazón', 'Escote cuadrado', 'Escote redondo', 'Sin escote', 'Espalda descubierta']
RASGOS_TELA = ['Satín', 'Encaje', 'Chiffón', 'Tul', 'Mikado', 'Crepé', 'Organza', 'Bordado']

class Producto(models.Model):
    ESTADOS = [
        ('TIENDA', 'En Tienda'),
        ('APARTADO', 'Apartado'),
        ('PEDIDO', 'Sobre Pedido'),
    ]
    TALLAS = [
        ('XS', 'XS'), ('S', 'S'), ('M', 'M'), ('L', 'L'),
        ('XL', 'XL'), ('2XL', '2XL'), ('3XL', '3XL'), ('4XL', '4XL'), ('U', 'Unitalla')
    ]
    sku = models.CharField(max_length=100, unique=True, blank=True)
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT)
    modelo = models.ForeignKey(Modelo, on_delete=models.SET_NULL, null=True, blank=True)
    tela = models.ForeignKey(Tela, on_delete=models.SET_NULL, null=True, blank=True)
    color = models.ForeignKey(Color, on_delete=models.PROTECT)
    talla = models.CharField(max_length=10, choices=TALLAS, default='M')
    talla_obj = models.ForeignKey('Talla', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Talla (catálogo)', related_name='productos')
    talla_especial = models.CharField(max_length=50, blank=True, help_text="Para casos no estándar")
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

    activo = models.BooleanField(default=True, db_index=True,
        help_text="Desactivar oculta el producto del inventario sin borrar el historial")

    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    class Meta:
        verbose_name = "Variante (SKU)"
        verbose_name_plural = "Variantes (SKU)"
        constraints = [
            models.UniqueConstraint(
                fields=['modelo', 'color', 'tela', 'talla_obj'],
                condition=Q(modelo__isnull=False) & Q(talla_obj__isnull=False),
                name='uq_variante_modelo_color_tela_talla',
            )
        ]

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
    telefono = models.CharField(max_length=20, unique=True, db_index=True)
    notas = models.TextField(blank=True)
    fecha_alta = models.DateTimeField(default=timezone.now)
    def __str__(self): return self.nombre

class Ticket(models.Model):
    """Tickets persistentes y reimprimibles (snapshot)"""
    TIPOS = [
        ('VENTA', 'Venta'),
        ('APARTADO', 'Apartado'),
        ('PEDIDO', 'Pedido/Hechura'),
        ('SERVICIO', 'Servicio/Ajuste'),
        ('ABONO', 'Abono'),
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
    cliente_nombre = models.CharField(max_length=200, blank=True, db_index=True)
    cliente_telefono = models.CharField(max_length=20, blank=True)

    # Snapshot completo en JSON para máxima fidelidad histórica
    snapshot_json = models.JSONField(null=True, blank=True, help_text="Copia íntegra de ítems, precios y datos al emitir")

    # Relaciones (opcionales para trazabilidad viva)
    venta = models.ForeignKey('Venta', on_delete=models.SET_NULL, null=True, blank=True, related_name='tickets_asociados')
    apartado = models.ForeignKey('Apartado', on_delete=models.SET_NULL, null=True, blank=True, related_name='tickets_asociados')
    pedido = models.ForeignKey('Pedido', on_delete=models.SET_NULL, null=True, blank=True, related_name='tickets_relacionados')
    novia = models.ForeignKey('Novia', on_delete=models.SET_NULL, null=True, blank=True, related_name='tickets_relacionados')
    servicio = models.ForeignKey('Servicio', on_delete=models.SET_NULL, null=True, blank=True, related_name='tickets')
    caja = models.ForeignKey('CorteCaja', on_delete=models.SET_NULL, null=True, blank=True, related_name='tickets')

    def save(self, *args, **kwargs):
        if not self.folio:
            config = ConfiguracionTienda.get_solo()
            self.folio = Secuencia.siguiente(config.prefijo_sucursal)
        super().save(*args, **kwargs)

    def __str__(self): return self.folio

    def populate_from_obj(self, obj):
        """Pobla el ticket desde una Venta, Apartado, Pedido o Servicio"""
        self.total = getattr(obj, 'total', getattr(obj, 'precio', getattr(obj, 'costo', 0)))
        self.subtotal = self.total
        self.cliente_nombre = (
            getattr(obj, 'cliente_nombre', '')
            or (obj.cliente.nombre if hasattr(obj, 'cliente') and obj.cliente else '')
        )
        self.cliente_telefono = (
            getattr(obj, 'cliente_telefono', '')
            or (obj.cliente.telefono if hasattr(obj, 'cliente') and obj.cliente else '')
        )

        # total_pagado is already set correctly by registrar_cobro (= monto paid now)
        self.cambio = 0

        # Items
        items_data = []
        # VestidoDama takes priority over generic items for Pedido objects
        if hasattr(obj, 'vestido_dama'):
            # Pedido con VestidoDama asignado: generar item sintético desde el vestido
            try:
                vd = obj.vestido_dama
                modelo_val = vd.modelo.nombre if vd.modelo else (obj.modelo.nombre if obj.modelo else '')
                color_val = vd.color.nombre if vd.color else (obj.color.nombre if obj.color else '')
                tela_val = vd.tela.nombre if vd.tela else (obj.tela.nombre if obj.tela else '')
                precio_val = float(vd.precio) if vd.precio else float(getattr(obj, 'precio', 0))
                items_data.append({
                    'descripcion': vd.descripcion_especial or f"{vd.get_tipo_display()} {modelo_val}".strip(),
                    'modelo': modelo_val,
                    'numero_modelo': vd.numero_modelo,
                    'tipo': vd.get_tipo_display(),
                    'codigo': vd.codigo,
                    'color': color_val,
                    'tela': tela_val,
                    'sku': vd.codigo,
                    'talla': vd.talla or getattr(obj, 'talla', ''),
                    'cantidad': 1,
                    'precio_unitario': precio_val,
                    'subtotal': precio_val,
                })
            except Exception:
                pass
        # For non-Pedido objects (Apartado, Venta) with line items
        if not items_data and hasattr(obj, 'items') and not hasattr(obj, 'vestido_dama'):
            for item in obj.items.all():
                prod = item.producto if hasattr(item, 'producto') and item.producto else None
                desc = str(prod) if prod else getattr(item, 'descripcion', 'Sin descripción')
                if prod:
                    modelo_val = str(prod.modelo.nombre if prod.modelo else (getattr(item, 'modelo', '') or ''))
                    color_val = str(prod.color.nombre if prod.color else (getattr(item, 'color', '') or ''))
                    sku_val = prod.sku or ''
                else:
                    modelo_val = str(getattr(item, 'modelo', '') or '')
                    color_val = str(getattr(item, 'color', '') or '')
                    sku_val = ''
                pu = float(getattr(item, 'precio_unitario', None) or getattr(item, 'precio', 0))
                items_data.append({
                    'descripcion': desc,
                    'modelo': modelo_val,
                    'color': color_val,
                    'sku': sku_val,
                    'talla': getattr(item, 'talla', '') or (prod.talla if prod else ''),
                    'cantidad': item.cantidad,
                    'precio_unitario': pu,
                    'subtotal': float(getattr(item, 'subtotal', None) or (item.cantidad * pu)),
                })
        # For Pedido with PedidoItems (but no VestidoDama): use the PedidoItems
        if not items_data and hasattr(obj, 'items') and hasattr(obj, 'vestido_dama'):
            for item in obj.items.all():
                pu = float(item.precio)
                items_data.append({
                    'descripcion': item.descripcion_especial or item.get_tipo_display(),
                    'modelo': item.modelo.nombre if item.modelo else '',
                    'numero_modelo': item.numero_modelo,
                    'color': item.color.nombre if item.color else '',
                    'tela': item.tela.nombre if item.tela else '',
                    'sku': item.codigo,
                    'talla': item.talla,
                    'cantidad': item.cantidad,
                    'precio_unitario': pu,
                    'subtotal': pu * item.cantidad,
                })
        if not items_data and hasattr(obj, 'precio'):
            # Pedido sin VestidoDama ni items: generar ítem sintético desde el pedido
            modelo_val = obj.modelo.nombre if obj.modelo else ''
            color_val = obj.color.nombre if obj.color else ''
            tela_val = obj.tela.nombre if obj.tela else ''
            precio_val = float(obj.precio)
            items_data.append({
                'descripcion': f"Vestido {modelo_val} {color_val}".strip() or 'Pedido',
                'modelo': modelo_val,
                'color': color_val,
                'tela': tela_val,
                'sku': getattr(obj, 'numero_ticket', ''),
                'talla': getattr(obj, 'talla', ''),
                'cantidad': 1,
                'precio_unitario': precio_val,
                'subtotal': precio_val,
            })
        # For Servicio (ajuste/costura): build items from AjusteLinea or single tipo
        if not items_data and hasattr(obj, 'pagos_servicio'):
            lineas_list = list(obj.lineas.all())  # single query; avoids exists()+all() double hit
            if lineas_list:
                for linea in lineas_list:
                    items_data.append({
                        'descripcion': linea.descripcion_ticket,
                        'prenda': linea.prenda,
                        'notas': linea.notas,
                        'color': '',
                        'talla': '',
                        'cantidad': linea.cantidad,
                        'precio_unitario': float(linea.precio_unitario),
                        'subtotal': float(linea.subtotal),
                    })
            else:
                desc = obj.get_tipo_display()
                if obj.descripcion:
                    desc += f': {obj.descripcion[:60]}'
                items_data.append({
                    'descripcion': desc,
                    'color': '',
                    'talla': '',
                    'cantidad': 1,
                    'precio_unitario': float(obj.costo),
                    'subtotal': float(obj.costo),
                })

        # Historial de abonos
        abonos = []
        abono_qs = None
        if hasattr(obj, 'pagos_pedido'):
            abono_qs = obj.pagos_pedido.order_by('fecha')
        elif hasattr(obj, 'pagos_apartado'):
            abono_qs = obj.pagos_apartado.order_by('fecha')
        elif hasattr(obj, 'pagos'):
            abono_qs = obj.pagos.order_by('fecha')
        elif hasattr(obj, 'pagos_servicio'):
            abono_qs = obj.pagos_servicio.order_by('fecha')
        if abono_qs is not None:
            for p in abono_qs:
                abonos.append({
                    'fecha': p.fecha.isoformat(),
                    'monto': float(p.monto),
                    'metodo': p.metodo,
                })

        total_pagado_acumulado = sum(a['monto'] for a in abonos)

        # Medidas
        medidas_dict = {}
        if hasattr(obj, 'medidas'):
            try:
                m = obj.medidas
                medidas_dict = {
                    'busto': str(m.busto or ''),
                    'cintura': str(m.cintura or ''),
                    'cadera': str(m.cadera or ''),
                    'largo_aproximado': str(m.largo_aproximado or ''),
                    'bajo_busto': str(m.bajo_busto or ''),
                    'largo_talle': str(m.largo_talle or ''),
                    'hombro_pezon': str(m.hombro_pezon or ''),
                    'hombro_bajo_busto': str(m.hombro_bajo_busto or ''),
                }
            except Exception:
                pass

        # Novia/dama
        novia_nombre = ''
        dama_nombre = ''
        if hasattr(obj, 'novia') and obj.novia:
            novia_nombre = obj.novia.nombre
        if hasattr(obj, 'dama') and obj.dama:
            dama_nombre = obj.dama.nombre

        # Fecha de entrega
        fecha_entrega = ''
        if getattr(obj, 'fecha_entrega_estimada', None):
            fecha_entrega = str(obj.fecha_entrega_estimada)
        elif getattr(obj, 'fecha_prometida', None):
            fecha_entrega = str(obj.fecha_prometida)

        # VestidoDama (si existe en el pedido)
        vestido_data = {}
        if hasattr(obj, 'vestido_dama'):
            try:
                vd = obj.vestido_dama
                vestido_data = vd.to_dict()
            except Exception:
                pass

        snapshot = {
            'folio': self.folio,
            'tipo': self.tipo,
            'fecha': self.fecha_hora.isoformat(),
            'cliente': self.cliente_nombre,
            'cliente_telefono': self.cliente_telefono,
            'metodo_pago': getattr(self, '_metodo_pago_snapshot', ''),
            'fecha_entrega_estimada': fecha_entrega,
            'notas_entrega': getattr(obj, 'notas_entrega', '') or '',
            'novia_nombre': novia_nombre,
            'dama_nombre': dama_nombre,
            'medidas': medidas_dict,
            'vestido': vestido_data,
            # 'total' is intentionally omitted — ticket.total is the single source of truth.
            # The QR template uses ticket.total directly; never read snapshot['total'].
            'total_pagado': float(self.total_pagado),
            'total_pagado_acumulado': total_pagado_acumulado,
            'saldo_pendiente': float(Decimal(str(self.total)) - Decimal(str(total_pagado_acumulado))),
            'abonos': abonos,
            'items': items_data,
        }
        self.snapshot_json = snapshot
        self.save()

class Venta(models.Model):
    EVENTOS = [
        ('Boda', 'Boda'), ('Graduación', 'Graduación'), ('XV años', 'XV años'),
        ('Fiesta', 'Fiesta'), ('Civil', 'Civil'), ('Formal', 'Formal'), ('Otro', 'Otro')
    ]
    OPERACIONES = [
        ('VENTA_NORMAL', 'Venta normal'),
        ('DAMA_HONOR', 'Dama de honor'),
        ('HECHURA', 'Hechura'),
        ('PEDIDO_EXTERNO', 'Pedido Externo'),
    ]
    vendedor = models.ForeignKey('auth.User', on_delete=models.PROTECT)
    cliente = models.ForeignKey(Cliente, on_delete=models.SET_NULL, null=True, blank=True)
    evento = models.CharField(max_length=50, choices=EVENTOS, blank=True)
    tipo_operacion = models.CharField(max_length=30, choices=OPERACIONES, default='VENTA_NORMAL')

    # Cache para marketing
    categoria_cache = models.CharField(max_length=100, blank=True)
    color_cache = models.CharField(max_length=100, blank=True)
    talla_cache = models.CharField(max_length=50, blank=True)

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

class IdempotencyLog(models.Model):
    key = models.CharField(max_length=100, unique=True, db_index=True)
    response_json = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, default='PROCESSING') # PROCESSING, DONE, ERROR

    def __str__(self):
        return f"{self.key} - {self.status}"


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
        ('LLEGO_A_TIENDA', 'Llegó a tienda'),
        ('CANCELADO', 'Cancelado'),
        ('ENTREGADO', 'Entregado'),
    ]
    EVENTOS = [
        ('Boda', 'Boda'), ('Graduación', 'Graduación'), ('XV años', 'XV años'),
        ('Fiesta', 'Fiesta'), ('Civil', 'Civil'), ('Formal', 'Formal'), ('Otro', 'Otro')
    ]
    OPERACIONES = [
        ('VENTA_NORMAL', 'Venta normal'),
        ('DAMA_HONOR', 'Dama de honor'),
        ('HECHURA', 'Hechura'),
        ('PEDIDO_EXTERNO', 'Pedido Externo'),
    ]

    folio = models.CharField(max_length=30, unique=True, blank=True)
    cliente = models.ForeignKey(Cliente, on_delete=models.SET_NULL, null=True, blank=True)
    cliente_nombre = models.CharField(max_length=200)
    cliente_telefono = models.CharField(max_length=20)
    evento = models.CharField(max_length=50, choices=EVENTOS, blank=True)
    tipo_operacion = models.CharField(max_length=30, choices=OPERACIONES, default='VENTA_NORMAL')

    # Cache para marketing
    categoria_cache = models.CharField(max_length=100, blank=True)
    color_cache = models.CharField(max_length=100, blank=True)
    talla_cache = models.CharField(max_length=50, blank=True)

    notas = models.TextField(blank=True)

    estado = models.CharField(max_length=20, choices=ESTADOS, default='VIGENTE', db_index=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True, db_index=True)
    fecha_vencimiento = models.DateField(null=True, blank=True)

    # Totales
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    anticipo = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    saldo = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Links opcionales
    novia = models.ForeignKey('Novia', on_delete=models.SET_NULL, null=True, blank=True, related_name='apartados_independientes')
    pedido = models.ForeignKey('Pedido', on_delete=models.SET_NULL, null=True, blank=True, related_name='apartados')

    # Entrega y Agenda
    fecha_entrega_estimada = models.DateField(null=True, blank=True)
    notas_entrega = models.TextField(blank=True)
    agenda_evento = models.ForeignKey('CitaAgenda', on_delete=models.SET_NULL, null=True, blank=True, related_name='apartados_vinculados')

    # Tracking "llegó a tienda"
    llego_a_tienda_en = models.DateTimeField(null=True, blank=True)
    llego_a_tienda_por = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='apartados_llegaron')

    def save(self, *args, **kwargs):
        if not self.folio:
            # Use Secuencia for atomic folio generation — COUNT+1 produces duplicates under concurrency.
            self.folio = Secuencia.siguiente('AP')

        self.saldo = max(Decimal('0'), self.total - self.anticipo)
        super().save(*args, **kwargs)

    def __str__(self): return f"{self.folio} - {self.cliente_nombre}"

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
    transferencia_esperada = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    # Valores reales (ingresados por el vendedor)
    efectivo_real = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    tarjeta_real = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    transferencia_real = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    diferencia = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    observaciones = models.TextField(blank=True)
    cerrado = models.BooleanField(default=False)

    def __str__(self):
        return f"Corte {self.fecha_apertura.strftime('%Y-%m-%d %H:%M')} - {self.abierto_por.username}"

    @property
    def resumen_movimientos(self):
        """Calcula totales por tipo y método"""
        from django.db.models import Sum
        return self.movimientos.values('tipo', 'metodo_pago').annotate(total=Sum('monto'))

class MovimientoCaja(models.Model):
    """Registro contable de cada flujo de dinero en la caja"""
    TIPOS = [
        ('VENTA', 'Venta'),
        ('ABONO_PEDIDO', 'Abono de Pedido'),
        ('ABONO_APARTADO', 'Abono de Apartado'),
        ('ABONO_SERVICIO', 'Abono de Servicio'),
        ('INGRESO', 'Ingreso Extra'),
        ('GASTO', 'Gasto/Egreso'),
        ('DEVOLUCION', 'Devolución'),
    ]
    METODOS = [
        ('EFECTIVO', 'Efectivo'),
        ('TARJETA', 'Tarjeta'),
        ('TRANSFERENCIA', 'Transferencia'),
    ]

    caja = models.ForeignKey(CorteCaja, on_delete=models.PROTECT, related_name='movimientos')
    tipo = models.CharField(max_length=20, choices=TIPOS)
    metodo_pago = models.CharField(max_length=20, choices=METODOS)
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    referencia = models.CharField(max_length=100, blank=True)
    ticket_folio = models.CharField(max_length=30, blank=True)
    fecha = models.DateTimeField(auto_now_add=True)
    registrado_por = models.ForeignKey('auth.User', on_delete=models.PROTECT)

    # Origen para trazabilidad (opcionales)
    venta = models.ForeignKey('Venta', on_delete=models.SET_NULL, null=True, blank=True)
    pedido = models.ForeignKey('Pedido', on_delete=models.SET_NULL, null=True, blank=True)
    apartado = models.ForeignKey('Apartado', on_delete=models.SET_NULL, null=True, blank=True)
    servicio = models.ForeignKey('Servicio', on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['fecha'], name='movcaja_fecha_idx'),
            models.Index(fields=['caja', 'fecha'], name='movcaja_caja_fecha_idx'),
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.metodo_pago} - ${self.monto}"



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
        super().save(*args, **kwargs)
        # Atomic F()-based update — prevents lost-update race under concurrent Gunicorn workers.
        # Never read-modify-write stock_teorico at the Python level.
        Producto.objects.filter(pk=self.producto_id).update(
            stock_teorico=F('stock_teorico') + self.cantidad
        )
        # Sync audit field with the actual post-update value (single extra SELECT).
        nuevo_stock = (
            Producto.objects.filter(pk=self.producto_id)
            .values_list('stock_teorico', flat=True)
            .get()
        )
        type(self).objects.filter(pk=self.pk).update(stock_resultante=nuevo_stock)
        self.stock_resultante = nuevo_stock
        self.producto.stock_teorico = nuevo_stock



# ============================================================
# SISTEMA DE AGENDA Y NOVIAS
# ============================================================

class Novia(models.Model):
    """Perfil de novia - cabeza de grupo"""
    nombre = models.CharField(max_length=200)
    activo = models.BooleanField(default=True, db_index=True)
    telefono = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)

    # Fechas importantes
    fecha_boda = models.DateField(db_index=True)
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
    notas_entrega = models.TextField(blank=True)
    agenda_evento = models.ForeignKey('CitaAgenda', on_delete=models.SET_NULL, null=True, blank=True, related_name='novias_vinculadas')
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
    m_bajo_busto = models.CharField(max_length=50, blank=True, verbose_name="Bajo Busto")
    m_largo_talle = models.CharField(max_length=50, blank=True, verbose_name="Largo Talle")
    m_hombro_pezon = models.CharField(max_length=50, blank=True, verbose_name="Hombro-Pezón")
    m_hombro_bajo_busto = models.CharField(max_length=50, blank=True, verbose_name="Hombro-Bajo Busto")
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

    def _pedidos_list(self):
        """Return pedidos from prefetch cache when available (avoids re-query)."""
        if hasattr(self, 'pedidos_cache'):
            return self.pedidos_cache
        return list(
            self.pedidos
            .select_related('modelo', 'color', 'tela')
            .prefetch_related('pagos_pedido')
        )

    @property
    def total_pagado(self):
        return sum(p.total_pagado for p in self._pedidos_list())

    @property
    def total_pendiente(self):
        return sum(p.saldo_pendiente for p in self._pedidos_list())

    @property
    def medidas_completitud_promedio(self):
        peds = self._pedidos_list()
        if not peds: return 100
        total_pct = sum(p.medidas_completitud for p in peds)
        return int(total_pct / len(peds))

    @property
    def semaforo_medidas(self):
        peds = self._pedidos_list()
        if not peds: return 'secondary'

        completos = sum(1 for p in peds if p.medidas_completitud == 100)
        if completos == len(peds): return 'success'
        if completos > 0: return 'warning'
        return 'danger'

    @property
    def semaforo_produccion(self):
        """Punto 2: Pedido listo — in-memory filter via _pedidos_list()."""
        peds = [p for p in self._pedidos_list() if p.estado != 'CANCELADO']
        if not peds: return 'secondary'

        estados_listo = {'LISTO', 'RECIBIDO', 'ENTREGADO'}
        listos = sum(1 for p in peds if p.estado in estados_listo)
        if listos == len(peds): return 'success'

        hoy = timezone.now().date()
        pendientes = [p for p in peds if p.estado not in estados_listo]
        if any(
            p.fecha_entrega_estimada is None or p.fecha_entrega_estimada < hoy
            for p in pendientes
        ):
            return 'danger'

        if listos > 0: return 'warning'
        return 'secondary'

    @property
    def semaforo_pago(self):
        """Punto 3: Liquidado — in-memory filter via _pedidos_list()."""
        peds = [p for p in self._pedidos_list() if p.estado != 'CANCELADO']
        if not peds: return 'secondary'

        liquidados = sum(1 for p in peds if p.estado_pago == 'LIQUIDADO')
        if liquidados == len(peds): return 'success'

        proxima_semana = timezone.now().date() + timezone.timedelta(days=7)
        if any(
            p.estado_pago != 'LIQUIDADO'
            and p.fecha_entrega_estimada is not None
            and p.fecha_entrega_estimada <= proxima_semana
            for p in peds
        ):
            return 'danger'

        if liquidados > 0 or any(p.estado_pago in {'APARTADO', 'PARCIAL'} for p in peds):
            return 'warning'
        return 'secondary'

    @property
    def semaforo_entrega(self):
        """Punto 4: Entregado — in-memory filter via _pedidos_list()."""
        peds = [p for p in self._pedidos_list() if p.estado != 'CANCELADO']
        if not peds: return 'secondary'

        entregados = sum(1 for p in peds if p.estado == 'ENTREGADO')
        if entregados == len(peds): return 'success'
        if entregados > 0: return 'warning'
        return 'secondary'

    @property
    def resumen_pendientes(self):
        peds = self._pedidos_list()
        total_damas = (
            len(self.damas_cache) if hasattr(self, 'damas_cache')
            else self.damas.count()
        )
        return {
            'total_damas': total_damas,
            'medidas_completas': sum(1 for p in peds if p.medidas_completitud == 100),
            'medidas_incompletas': sum(1 for p in peds if p.medidas_completitud < 100),
            'listos_entrega': sum(1 for p in peds if p.estado == 'LISTO' and p.saldo_pendiente == 0),
            'pendientes_pago': sum(1 for p in peds if p.saldo_pendiente > 0),
            'entregados': sum(1 for p in peds if p.estado == 'ENTREGADO'),
        }

    @property
    def resumen_grupo(self):
        """Genera resumen de todos los pedidos del grupo."""
        pedidos = self._pedidos_list()
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
            'total': len(pedidos)
        }


class Dama(models.Model):
    """Integrante del grupo de la novia"""
    novia = models.ForeignKey(Novia, on_delete=models.CASCADE, related_name='damas')
    cliente = models.ForeignKey('Cliente', on_delete=models.SET_NULL, null=True, blank=True, related_name='perfiles_dama')
    nombre = models.CharField(max_length=200)
    activo = models.BooleanField(default=True)
    telefono = models.CharField(max_length=20, blank=True)
    
    # Personalización (puede diferir del grupo)
    color = models.ForeignKey(Color, on_delete=models.SET_NULL, null=True, blank=True)
    tela = models.ForeignKey(Tela, on_delete=models.SET_NULL, null=True, blank=True)
    modelo = models.ForeignKey(Modelo, on_delete=models.SET_NULL, null=True, blank=True)
    talla = models.CharField(max_length=10, blank=True)
    talla_obj = models.ForeignKey('Talla', on_delete=models.SET_NULL, null=True, blank=True, related_name='damas')

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
    m_bajo_busto = models.CharField(max_length=50, blank=True, verbose_name="Bajo Busto")
    m_largo_talle = models.CharField(max_length=50, blank=True, verbose_name="Largo Talle")
    m_hombro_pezon = models.CharField(max_length=50, blank=True, verbose_name="Hombro-Pezón")
    m_hombro_bajo_busto = models.CharField(max_length=50, blank=True, verbose_name="Hombro-Bajo Busto")
    m_notas_medidas = models.TextField(blank=True, verbose_name="Notas de Medidas")

    # Fechas individuales de la dama
    fecha_evento = models.DateField(null=True, blank=True, help_text="Fecha del evento de la dama")
    fecha_entrega = models.DateField(null=True, blank=True, help_text="Fecha de entrega del vestido")
    deadline_medidas = models.DateField(null=True, blank=True, help_text="Fecha límite para tomar medidas")
    medidas_tomadas = models.BooleanField(default=False, help_text="¿Ya se tomaron todas las medidas?")

    notas_ajustes = models.TextField(blank=True, help_text="Notas de ajustes específicos")
    
    def __str__(self):
        return f"{self.nombre} (Grupo de {self.novia.nombre})"


class Pedido(models.Model):
    """Pedido de vestido - puede ser de novia o dama"""
    ESTADOS = [
        # Taller / Hechura
        ('NUEVO', 'Nuevo'),
        ('PENDIENTE_TELA', 'Falta comprar tela'),
        ('TELA_COMPRADA', 'Tela comprada'),
        ('EN_CONFECCION', 'En confección'),
        # Importación / Proveedor (Pedido Externo)
        ('SOLICITADO', 'Solicitado'),
        ('EN_PROCESO', 'En proceso'),
        ('POR_RECOGER', 'Por recoger'),
        ('RECIBIDO', 'Recibido en tienda'),
        # Comunes
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
    EVENTOS = [
        ('Boda', 'Boda'), ('Graduación', 'Graduación'), ('XV años', 'XV años'),
        ('Fiesta', 'Fiesta'), ('Civil', 'Civil'), ('Formal', 'Formal'), ('Otro', 'Otro')
    ]
    TIPOS_PEDIDO = [
        ('HECHURA', 'Hechura Especial (Taller)'),
        ('PEDIDO_EXTERNO', 'Pedido Externo (Importación/Proveedor)'),
        ('ESTANDAR_GRUPO', 'Estándar Grupo / Dama'),
        ('SOBRE_PEDIDO', 'Sobre Pedido (Legacy)'),
    ]
    OPERACIONES = [
        ('VENTA_NORMAL', 'Venta normal'),
        ('DAMA_HONOR', 'Dama de honor'),
        ('HECHURA', 'Hechura'),
        ('PEDIDO_EXTERNO', 'Pedido Externo'),
    ]
    
    # Puede ser para la novia o para una dama
    cliente = models.ForeignKey(Cliente, on_delete=models.SET_NULL, null=True, blank=True)
    novia = models.ForeignKey(Novia, on_delete=models.CASCADE, related_name='pedidos', null=True, blank=True)
    dama = models.ForeignKey(Dama, on_delete=models.SET_NULL, null=True, blank=True, related_name='pedidos')
    es_vestido_novia = models.BooleanField(default=False, help_text="Es el vestido de la novia")
    
    # Producto/características
    producto = models.ForeignKey(Producto, on_delete=models.SET_NULL, null=True, blank=True, help_text="Si ya existe en inventario")
    modelo = models.ForeignKey(Modelo, on_delete=models.SET_NULL, null=True, blank=True)
    color = models.ForeignKey(Color, on_delete=models.SET_NULL, null=True, blank=True)
    tela = models.ForeignKey(Tela, on_delete=models.SET_NULL, null=True, blank=True)
    talla = models.CharField(max_length=10, blank=True)
    talla_obj = models.ForeignKey('Talla', on_delete=models.SET_NULL, null=True, blank=True, related_name='pedidos')

    # Imagen de referencia
    imagen_referencia = models.ImageField(upload_to='pedidos/', blank=True, null=True)
    
    # Precio y pagos
    precio = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    anticipo = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    evento = models.CharField(max_length=50, choices=EVENTOS, blank=True)
    tipo_operacion = models.CharField(max_length=30, choices=OPERACIONES, default='VENTA_NORMAL')
    tipo_pedido = models.CharField(max_length=20, choices=TIPOS_PEDIDO, default='SOBRE_PEDIDO')
    
    # Estados
    estado = models.CharField(max_length=20, choices=ESTADOS, default='NUEVO')
    estado_pago = models.CharField(max_length=20, choices=ESTADOS_PAGO, default='SIN_PAGO')
    
    # Fechas
    fecha_entrega_estimada = models.DateField(null=True, blank=True)
    fecha_entrega_real = models.DateField(null=True, blank=True)
    fecha_evento = models.DateField(null=True, blank=True)
    
    # Notas
    notas = models.TextField(blank=True)
    notas_ajustes = models.TextField(blank=True)
    notas_entrega = models.TextField(blank=True)
    
    # Agenda
    agenda_evento = models.ForeignKey('CitaAgenda', on_delete=models.SET_NULL, null=True, blank=True, related_name='pedidos_vinculados')

    # Ticket/referencia
    ticket = models.ForeignKey(Ticket, on_delete=models.SET_NULL, null=True, blank=True, related_name='pedidos')
    numero_ticket = models.CharField(max_length=20, unique=True, blank=True)
    offline_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    
    # Tracking
    creado_por = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, related_name='pedidos_creados')
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)
    llego_a_tienda_en = models.DateTimeField(null=True, blank=True)
    llego_a_tienda_por = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='pedidos_recibidos')
    
    class Meta:
        ordering = ['-fecha_creacion']
        indexes = [
            models.Index(fields=['estado'], name='pedido_estado_idx'),
            models.Index(fields=['fecha_entrega_estimada'], name='pedido_entrega_idx'),
            models.Index(fields=['estado', 'fecha_entrega_estimada'], name='pedido_estado_entrega_idx'),
        ]

    def save(self, *args, **kwargs):
        if not self.numero_ticket:
            import uuid
            self.numero_ticket = f"PED-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)

    def __str__(self):
        quien = "Novia" if self.es_vestido_novia else (self.dama.nombre if self.dama else "Dama")
        novia_nombre = self.novia.nombre if self.novia else 'Sin novia'
        return f"{self.numero_ticket} - {quien} ({novia_nombre})"
    
    @property
    def total_pagado(self):
        return sum(p.monto for p in self.pagos_pedido.all())

    @property
    def ultimo_pago(self):
        return self.pagos_pedido.order_by('-fecha', '-id').first()


    @property
    def saldo_pendiente(self):
        return max(Decimal('0'), self.precio - self.total_pagado)

    @property
    def esta_pagado(self):
        return self.saldo_pendiente <= 0

    @property
    def medidas_completitud(self):
        if not hasattr(self, 'medidas') or not self.medidas:
            return 0

        m = self.medidas
        campos_clave = ['busto', 'cintura', 'cadera', 'largo_aproximado']
        campos_secundarios = ['hombro', 'brazo', 'espalda', 'talle_delantero', 'talle_trasero', 'altura_busto', 'separacion_busto', 'bajo_busto', 'largo_talle', 'hombro_pezon', 'hombro_bajo_busto']

        completos_clave = sum(1 for f in campos_clave if getattr(m, f) is not None)
        completos_secundarios = sum(1 for f in campos_secundarios if getattr(m, f) is not None)

        # Clave: 60% (15% cada uno), Secundarios: 40% (~5.7% cada uno)
        pct_clave = completos_clave * 15
        pct_sec = (completos_secundarios / len(campos_secundarios)) * 40 if campos_secundarios else 0

        return int(pct_clave + pct_sec)


class PedidoItem(models.Model):
    """Línea de un pedido — cada vestido, accesorio o ajuste es un ítem separado."""
    TIPOS = [
        ('VESTIDO', 'Vestido (catálogo/importación)'),
        ('HECHURA', 'Hechura especial'),
        ('ESPECIAL', 'Modelo especial'),
        ('ACCESORIO', 'Accesorio'),
        ('AJUSTE', 'Ajuste / costura'),
    ]
    ESTADOS = [
        ('PENDIENTE', 'Pendiente'),
        ('SOLICITADO', 'Solicitado'),
        ('EN_PROCESO', 'En proceso'),
        ('POR_RECOGER', 'Por recoger'),
        ('LLEGO', 'Llegó a tienda'),
        ('ENTREGADO', 'Entregado'),
        ('CANCELADO', 'Cancelado'),
    ]

    pedido = models.ForeignKey('Pedido', on_delete=models.CASCADE, related_name='items')
    dama = models.ForeignKey('Dama', on_delete=models.SET_NULL, null=True, blank=True, related_name='pedido_items')
    codigo = models.CharField(max_length=30, unique=True, db_index=True)

    tipo = models.CharField(max_length=20, choices=TIPOS, default='VESTIDO')
    modelo = models.ForeignKey('Modelo', on_delete=models.SET_NULL, null=True, blank=True)
    numero_modelo = models.CharField(max_length=50, blank=True)
    descripcion_especial = models.TextField(blank=True)
    talla = models.CharField(max_length=10, blank=True)
    talla_obj = models.ForeignKey('Talla', on_delete=models.SET_NULL, null=True, blank=True, related_name='pedido_items')
    color = models.ForeignKey('Color', on_delete=models.SET_NULL, null=True, blank=True)
    tela = models.ForeignKey('Tela', on_delete=models.SET_NULL, null=True, blank=True)

    cantidad = models.PositiveIntegerField(default=1)
    precio = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    notas = models.TextField(blank=True)
    foto = models.ImageField(upload_to='pedido_items/', blank=True, null=True)

    estado = models.CharField(max_length=20, choices=ESTADOS, default='PENDIENTE')
    llego_en = models.DateTimeField(null=True, blank=True)
    entregado_en = models.DateTimeField(null=True, blank=True)

    vestido_dama = models.OneToOneField(
        'VestidoDama', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='pedido_item'
    )

    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['creado_en']

    def save(self, *args, **kwargs):
        if not self.codigo:
            self.codigo = Secuencia.siguiente('PI')
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.codigo} — {self.get_tipo_display()}"

    def to_dict(self):
        return {
            'id': self.pk,
            'codigo': self.codigo,
            'tipo': self.tipo,
            'tipo_display': self.get_tipo_display(),
            'modelo': self.modelo.nombre if self.modelo else '',
            'numero_modelo': self.numero_modelo,
            'descripcion_especial': self.descripcion_especial,
            'talla': self.talla,
            'color': self.color.nombre if self.color else '',
            'tela': self.tela.nombre if self.tela else '',
            'cantidad': self.cantidad,
            'precio': float(self.precio),
            'notas': self.notas,
            'estado': self.estado,
            'estado_display': self.get_estado_display(),
            'dama': self.dama.nombre if self.dama else '',
            'llego_en': self.llego_en.isoformat() if self.llego_en else None,
            'entregado_en': self.entregado_en.isoformat() if self.entregado_en else None,
        }


class PagoApartado(models.Model):
    """Pagos asociados a un apartado independiente"""
    METODOS = [
        ('EFECTIVO', 'Efectivo'),
        ('TARJETA', 'Tarjeta'),
        ('TRANSFERENCIA', 'Transferencia'),
    ]
    apartado = models.ForeignKey('Apartado', on_delete=models.CASCADE, related_name='pagos_apartado')
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    metodo = models.CharField(max_length=20, choices=METODOS, default='EFECTIVO')
    referencia = models.CharField(max_length=100, blank=True)
    fecha = models.DateTimeField(auto_now_add=True)
    registrado_por = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True)
    notas = models.CharField(max_length=200, blank=True)

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new:
            # Incrementar anticipo y decrementar saldo en una sola query (sin re-fetch de pagos)
            Apartado.objects.filter(pk=self.apartado_id).update(
                anticipo=F('anticipo') + self.monto,
                saldo=F('saldo') - self.monto,
            )

    def __str__(self):
        return f"${self.monto} - Apartado {self.apartado.id}"


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
    referencia = models.CharField(max_length=100, blank=True)
    fecha = models.DateTimeField(auto_now_add=True)
    registrado_por = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True)
    notas = models.CharField(max_length=200, blank=True)
    
    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new:
            # Actualizar anticipo con F() para evitar re-fetch de todos los pagos
            Pedido.objects.filter(pk=self.pedido_id).update(
                anticipo=F('anticipo') + self.monto
            )
        # Recalcular estado_pago (necesita total actualizado)
        pedido = Pedido.objects.only('precio', 'anticipo', 'estado_pago').get(pk=self.pedido_id)
        total_pagado = pedido.anticipo
        if total_pagado >= pedido.precio:
            estado_pago = 'LIQUIDADO'
        elif total_pagado > 0:
            estado_pago = 'PARCIAL' if total_pagado > Decimal(str(pedido.precio)) * Decimal('0.3') else 'APARTADO'
        else:
            estado_pago = pedido.estado_pago
        if estado_pago != pedido.estado_pago:
            Pedido.objects.filter(pk=self.pedido_id).update(estado_pago=estado_pago)
    
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
    apartado = models.ForeignKey(Apartado, on_delete=models.SET_NULL, null=True, blank=True, related_name='citas')
    
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


# ============================================================
# SERVICIOS Y AJUSTES
# ============================================================

class Servicio(models.Model):
    """Servicio de ajuste, costura u otro trabajo sin pedido de vestido"""
    TIPOS = [
        ('BASTILLA',    'Bastilla'),
        ('TALLE',       'Ajuste de talle'),
        ('TIRANTE',     'Tirante'),
        ('CREMALLERA',  'Cremallera'),
        ('PECHO',       'Ajuste de pecho'),
        ('CADERA',      'Ajuste de cadera'),
        ('MANGA',       'Manga'),
        ('APLIQUE',     'Aplique / Adorno'),
        ('BORDADO',     'Bordado'),
        ('AJUSTE',      'Ajuste general'),
        ('OTRO',        'Otro servicio'),
    ]
    ESTADOS = [
        ('RECIBIDO', 'Recibido'),
        ('EN_PROCESO', 'En proceso'),
        ('LISTO', 'Listo para entrega'),
        ('ENTREGADO', 'Entregado'),
        ('CANCELADO', 'Cancelado'),
    ]

    tipo = models.CharField(max_length=20, choices=TIPOS, default='AJUSTE')
    descripcion = models.TextField()
    cliente = models.ForeignKey('Cliente', on_delete=models.SET_NULL, null=True, blank=True, related_name='servicios')
    novia = models.ForeignKey('Novia', on_delete=models.SET_NULL, null=True, blank=True, related_name='servicios')
    estado = models.CharField(max_length=20, choices=ESTADOS, default='RECIBIDO', db_index=True)
    costo = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    anticipo = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    fecha_prometida = models.DateField(null=True, blank=True)
    notas = models.TextField(blank=True)
    venta = models.ForeignKey('Venta', on_delete=models.SET_NULL, null=True, blank=True, related_name='servicios_incluidos')
    creado_por = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-fecha_creacion']

    def __str__(self):
        cliente_str = self.cliente.nombre if self.cliente else (self.novia.nombre if self.novia else 'S/C')
        return f"SRV-{self.pk} {self.get_tipo_display()} - {cliente_str}"

    @property
    def total_pagado(self):
        return sum(p.monto for p in self.pagos_servicio.all())

    @property
    def saldo_pendiente(self):
        return max(self.costo - self.total_pagado, Decimal('0'))


class PagoServicio(models.Model):
    """Pagos contra un Servicio"""
    METODOS = [
        ('EFECTIVO', 'Efectivo'),
        ('TARJETA', 'Tarjeta'),
        ('TRANSFERENCIA', 'Transferencia'),
    ]
    servicio = models.ForeignKey(Servicio, on_delete=models.CASCADE, related_name='pagos_servicio')
    monto = models.DecimalField(max_digits=10, decimal_places=2)
    metodo = models.CharField(max_length=20, choices=METODOS, default='EFECTIVO')
    referencia = models.CharField(max_length=100, blank=True)
    fecha = models.DateTimeField(auto_now_add=True)
    registrado_por = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True)
    notas = models.CharField(max_length=200, blank=True)

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new:
            from .models import Servicio
            Servicio.objects.filter(pk=self.servicio_id).update(
                anticipo=F('anticipo') + self.monto
            )

    def __str__(self):
        return f"${self.monto} - {self.servicio}"


class AjusteLinea(models.Model):
    """Línea de ajuste dentro de un Servicio — permite múltiples tipos por operación."""
    TIPOS = [
        ('BASTILLA',  'Bastilla'),
        ('TIRANTE',   'Tirante'),
        ('HOMBRO',    'Hombro'),
        ('PIERNA',    'Pierna'),
        ('CINTURA',   'Cintura'),
        ('BUSTO',     'Busto'),
        ('CIERRE',    'Cierre / Cremallera'),
        ('MANGA',     'Manga'),
        ('COSTADO',   'Costado'),
        ('OTRO',      'Otro'),
    ]
    servicio        = models.ForeignKey(Servicio, on_delete=models.CASCADE, related_name='lineas')
    tipo            = models.CharField(max_length=20, choices=TIPOS)
    descripcion     = models.TextField(blank=True, help_text='Detalle adicional. Requerido cuando tipo=OTRO.')
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    cantidad        = models.PositiveIntegerField(default=1)
    subtotal        = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    notas           = models.TextField(blank=True)
    prenda          = models.CharField(max_length=200, blank=True, help_text='Prenda o ítem relacionado')
    orden           = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['orden', 'pk']

    def save(self, *args, **kwargs):
        self.subtotal = self.precio_unitario * self.cantidad
        super().save(*args, **kwargs)

    @property
    def descripcion_ticket(self):
        base = f"Ajuste — {self.get_tipo_display()}"
        if self.prenda:
            base += f" ({self.prenda})"
        return base

    def __str__(self):
        return self.descripcion_ticket


# ============================================================
# MEDIDAS POR DAMA (expediente editable con historial)
# ============================================================

class MedidasDama(models.Model):
    """Versión de medidas vinculada directamente a una Dama, con historial."""
    dama = models.ForeignKey(Dama, on_delete=models.CASCADE, related_name='medidas_registradas')
    vigente = models.BooleanField(default=True, db_index=True)

    # Medidas corporales (cm)
    busto = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    cintura = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    cadera = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    largo_aproximado = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    hombro = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    brazo = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    espalda = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    talle_delantero = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    talle_trasero = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    altura_busto = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    separacion_busto = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    bajo_busto = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    largo_talle = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    hombro_pezon = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    hombro_bajo_busto = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    notas = models.TextField(blank=True)

    fecha_medicion = models.DateField(auto_now_add=True)
    fecha_modificacion = models.DateTimeField(auto_now=True)
    registrado_por = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='medidas_dama_registradas'
    )
    modificado_por = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='medidas_dama_modificadas'
    )

    class Meta:
        ordering = ['-fecha_medicion', '-fecha_modificacion']

    def __str__(self):
        estado = 'vigente' if self.vigente else 'histórica'
        return f"Medidas {estado} — {self.dama.nombre} ({self.fecha_medicion})"

    def to_dict(self):
        campos = [
            'busto', 'cintura', 'cadera', 'largo_aproximado', 'hombro', 'brazo',
            'espalda', 'talle_delantero', 'talle_trasero', 'altura_busto',
            'separacion_busto', 'bajo_busto', 'largo_talle', 'hombro_pezon',
            'hombro_bajo_busto',
        ]
        return {
            'id': self.pk,
            'vigente': self.vigente,
            'notas': self.notas,
            'fecha_medicion': str(self.fecha_medicion),
            'fecha_modificacion': self.fecha_modificacion.isoformat(),
            'registrado_por': self.registrado_por.get_full_name() or self.registrado_por.username if self.registrado_por else None,
            'modificado_por': self.modificado_por.get_full_name() or self.modificado_por.username if self.modificado_por else None,
            **{campo: float(getattr(self, campo)) if getattr(self, campo) is not None else None for campo in campos},
        }


# ============================================================
# VESTIDO DE DAMA (trazabilidad completa)
# ============================================================

class VestidoDama(models.Model):
    """Artículo identificable asignado a una dama: catálogo, especial o hecho a la medida."""
    TIPOS = [
        ('CATALOGO', 'De catálogo'),
        ('ESPECIAL', 'Modelo especial'),
        ('HECHURA', 'Hecho a la medida'),
    ]
    ESTADOS = [
        ('PENDIENTE_FABRICACION', 'Pendiente de fabricación'),
        ('PEDIDO', 'Pedido / Solicitado'),
        ('EN_TRANSITO', 'En tránsito'),
        ('LLEGO_A_TIENDA', 'Llegó a tienda'),
        ('RESERVADO', 'Reservado para la dama'),
        ('ENTREGADO', 'Entregado'),
        ('CANCELADO', 'Cancelado'),
        ('DEVUELTO', 'Devuelto'),
    ]

    codigo = models.CharField(max_length=30, unique=True, db_index=True)
    dama = models.ForeignKey(Dama, on_delete=models.CASCADE, related_name='vestidos')
    pedido = models.OneToOneField(
        Pedido, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='vestido_dama'
    )
    tipo = models.CharField(max_length=20, choices=TIPOS, default='ESPECIAL')
    modelo = models.ForeignKey(Modelo, on_delete=models.SET_NULL, null=True, blank=True)
    numero_modelo = models.CharField(max_length=100, blank=True)
    descripcion_especial = models.TextField(blank=True)
    talla = models.CharField(max_length=10, blank=True)
    talla_obj = models.ForeignKey('Talla', on_delete=models.SET_NULL, null=True, blank=True, related_name='vestidos_dama')
    color = models.ForeignKey(Color, on_delete=models.SET_NULL, null=True, blank=True)
    tela = models.ForeignKey(Tela, on_delete=models.SET_NULL, null=True, blank=True)
    foto_referencia = models.ImageField(upload_to='vestidos/', null=True, blank=True)
    precio = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    costo = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    estado = models.CharField(max_length=30, choices=ESTADOS, default='PEDIDO', db_index=True)

    # Cuando entra físicamente al inventario se puede vincular a un Producto
    producto = models.OneToOneField(
        Producto, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='vestido_dama'
    )

    llego_en = models.DateTimeField(null=True, blank=True)
    llego_por = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='vestidos_recibidos'
    )
    entregado_en = models.DateTimeField(null=True, blank=True)
    entregado_por = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='vestidos_entregados'
    )
    creado_por = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='vestidos_creados'
    )
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-fecha_creacion']

    def save(self, *args, **kwargs):
        if not self.codigo:
            self.codigo = Secuencia.siguiente('VD')
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.codigo} — {self.dama.nombre}"

    @property
    def existencia_fisica(self):
        entradas = sum(
            m.cantidad for m in self.movimientos_vestido.filter(tipo__in=['ENTRADA', 'DEVOLUCION'])
        )
        salidas = sum(
            m.cantidad for m in self.movimientos_vestido.filter(tipo__in=['SALIDA', 'MERMA'])
        )
        return entradas - salidas

    @property
    def disponible(self):
        reservas = sum(m.cantidad for m in self.movimientos_vestido.filter(tipo='RESERVA'))
        liberaciones = sum(m.cantidad for m in self.movimientos_vestido.filter(tipo='LIBERACION_RESERVA'))
        return self.existencia_fisica - max(0, reservas - liberaciones)

    def to_dict(self):
        return {
            'id': self.pk,
            'codigo': self.codigo,
            'tipo': self.tipo,
            'tipo_display': self.get_tipo_display(),
            'modelo': self.modelo.nombre if self.modelo else '',
            'numero_modelo': self.numero_modelo,
            'descripcion_especial': self.descripcion_especial,
            'talla': self.talla,
            'color': self.color.nombre if self.color else '',
            'tela': self.tela.nombre if self.tela else '',
            'precio': float(self.precio),
            'costo': float(self.costo),
            'estado': self.estado,
            'estado_display': self.get_estado_display(),
            'existencia_fisica': self.existencia_fisica,
            'disponible': self.disponible,
            'llego_en': self.llego_en.isoformat() if self.llego_en else None,
            'entregado_en': self.entregado_en.isoformat() if self.entregado_en else None,
        }


class MovimientoVestido(models.Model):
    """Registro de cada evento de inventario/ciclo de vida de un VestidoDama."""
    TIPOS = [
        ('ENTRADA', 'Entrada — llegó a tienda'),
        ('RESERVA', 'Reserva — asignado a dama'),
        ('SALIDA', 'Salida — vendido o entregado'),
        ('LIBERACION_RESERVA', 'Liberación de reserva'),
        ('DEVOLUCION', 'Devolución'),
        ('MERMA', 'Merma o baja por daño'),
    ]

    vestido = models.ForeignKey(VestidoDama, on_delete=models.CASCADE, related_name='movimientos_vestido')
    tipo = models.CharField(max_length=25, choices=TIPOS)
    cantidad = models.PositiveIntegerField(default=1)
    fecha = models.DateTimeField(auto_now_add=True)
    usuario = models.ForeignKey('auth.User', on_delete=models.PROTECT)
    notas = models.TextField(blank=True)

    class Meta:
        ordering = ['-fecha']

    def __str__(self):
        return f"{self.get_tipo_display()} — {self.vestido.codigo} ({self.fecha.strftime('%d/%m/%Y')})"
