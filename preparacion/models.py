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

    def save(self, *args, **kwargs):
        # Numeric-only Code 128 avoids HID keyboard-layout substitutions of
        # punctuation (such as '-' becoming an apostrophe on a Spanish Mac).
        if self.pk is None:
            super().save(*args, **kwargs)
            self.codigo = f'8{self.pk:011d}'
            super().save(update_fields=['codigo'])
        else:
            super().save(*args, **kwargs)
