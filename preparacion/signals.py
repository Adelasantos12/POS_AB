"""Keep physical stock in sync for variants activated through the stocktake."""

from django.db.models import F, Value
from django.db.models.functions import Greatest
from django.db.models.signals import post_save
from django.dispatch import receiver

from boutique.models import MovimientoInventario, Producto
from .models import VariantePreparada


@receiver(post_save, sender=MovimientoInventario)
def actualizar_cantidad_preparada(sender, instance, created, **kwargs):
    if not created or not VariantePreparada.objects.filter(
        producto_id=instance.producto_id, confirmada__isnull=False
    ).exists():
        return
    Producto.objects.filter(pk=instance.producto_id).update(
        cantidad_actual=Greatest(Value(0), F('cantidad_actual') + instance.cantidad)
    )
