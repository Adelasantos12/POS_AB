from django.conf import settings
from django.db import models
from django.db.models import Q


class VariantePreparada(models.Model):
    """Catalogued variant whose quantity has not yet been established."""
    producto = models.OneToOneField('boutique.Producto', on_delete=models.PROTECT,
                                    related_name='preparacion')
    creada = models.DateTimeField(auto_now_add=True)
    confirmada = models.DateTimeField(null=True, blank=True)
    cantidad_estimada = models.PositiveIntegerField(default=0)


class JornadaConteo(models.Model):
    abierta = models.BooleanField(default=True)
    iniciada = models.DateTimeField(auto_now_add=True)
    cerrada = models.DateTimeField(null=True, blank=True)
    responsable = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['abierta'], condition=Q(abierta=True),
                                               name='una_jornada_inicial_abierta')]


class PiezaEtiqueta(models.Model):
    """One printed identifier per physical dress, independent of its variant SKU."""
    variante = models.ForeignKey(VariantePreparada, on_delete=models.PROTECT,
                                 related_name='piezas')
    codigo = models.CharField(max_length=16, unique=True, db_index=True, null=True, blank=True)
    emitida = models.DateTimeField(auto_now_add=True)
    jornada = models.ForeignKey(JornadaConteo, on_delete=models.PROTECT,
                                null=True, blank=True, related_name='piezas')
    contada = models.DateTimeField(null=True, blank=True)
    vendida = models.DateTimeField(null=True, blank=True)

    costo_unitario = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    UBICACIONES = [('BOUTIQUE', 'Boutique'), ('BODEGA', 'Bodega'), ('OTRO_LOCAL', 'Otro local'), ('TALLER', 'Taller / costura')]
    ESTADOS = [('DISPONIBLE', 'Disponible'), ('ARREGLO', 'En arreglo'), ('MUESTRA', 'Muestra para réplica'), ('REVISION', 'En revisión'), ('APARTADA', 'Apartada'), ('VENDIDA', 'Vendida')]
    ubicacion = models.CharField(max_length=30, choices=UBICACIONES, default='BOUTIQUE')
    estado = models.CharField(max_length=30, choices=ESTADOS, default='DISPONIBLE')
    encargado = models.CharField(max_length=150, blank=True)
    regreso_previsto = models.DateField(null=True, blank=True)
    revision = models.PositiveIntegerField(default=0)
    ultima_venta = models.ForeignKey('boutique.Venta', null=True, blank=True, on_delete=models.PROTECT)

    @property
    def disponible_caja(self):
        return bool(self.contada and not self.vendida and self.variante.confirmada
                    and self.estado == 'DISPONIBLE' and self.ubicacion == 'BOUTIQUE')

    def save(self, *args, **kwargs):
        # Numeric-only Code 128 avoids HID keyboard-layout substitutions of
        # punctuation (such as '-' becoming an apostrophe on a Spanish Mac).
        if self.pk is None:
            super().save(*args, **kwargs)
            self.codigo = f'8{self.pk:011d}'
            super().save(update_fields=['codigo'])
        else:
            super().save(*args, **kwargs)


class MovimientoPieza(models.Model):
    costo_unitario = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    """Append-only history; moving a garment never creates another garment."""
    pieza = models.ForeignKey(PiezaEtiqueta, on_delete=models.PROTECT, related_name='historial')
    fecha = models.DateTimeField(auto_now_add=True)
    responsable = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    accion = models.CharField(max_length=30)
    origen = models.CharField(max_length=30)
    destino = models.CharField(max_length=30)
    estado_anterior = models.CharField(max_length=30)
    estado_nuevo = models.CharField(max_length=30)
    encargado = models.CharField(max_length=150, blank=True)
    regreso_previsto = models.DateField(null=True, blank=True)
    notas = models.CharField(max_length=500, blank=True)
    venta = models.ForeignKey('boutique.Venta', null=True, blank=True, on_delete=models.PROTECT)
    operacion = models.ForeignKey('OperacionPrendas', null=True, blank=True, on_delete=models.PROTECT)

    class Meta:
        ordering = ['-fecha', '-pk']


class OperacionPrendas(models.Model):
    clave = models.UUIDField(unique=True)
    responsable = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    fecha = models.DateTimeField(auto_now_add=True)
    huella = models.CharField(max_length=64)
    cantidad = models.PositiveIntegerField(default=0)


class CambioCosto(models.Model):
    pieza = models.ForeignKey(PiezaEtiqueta, on_delete=models.PROTECT)
    anterior = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    nuevo = models.DecimalField(max_digits=10, decimal_places=2)
    responsable = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    fecha = models.DateTimeField(auto_now_add=True)
    motivo = models.CharField(max_length=300)


class AnalisisInversion(models.Model):
    responsable = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    fecha = models.DateTimeField(auto_now_add=True)
    datos = models.JSONField()
    respuesta = models.TextField()
    modelo_ia = models.CharField(max_length=100)
