"""Admin-only, atomic removal of a trial model and all its variants."""
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from boutique.middleware import profile_permission_required
from boutique.models import Modelo, Producto, ItemVenta
from boutique.views import registrar_auditoria
from .models import JornadaConteo, PiezaEtiqueta, VariantePreparada


@require_POST
@login_required
@profile_permission_required('Admin')
def eliminar_modelo(request, producto_id):
    try:
        with transaction.atomic():
            list(JornadaConteo.objects.select_for_update().filter(abierta=True))
            referencia = get_object_or_404(Producto, pk=producto_id)
            modelo = None
            if referencia.modelo_id:
                modelo = Modelo.objects.select_for_update().get(pk=referencia.modelo_id)
                familia = Producto.objects.filter(modelo=modelo)
            elif referencia.rasgo1:
                familia = Producto.objects.filter(modelo__isnull=True,
                    categoria_id=referencia.categoria_id, rasgo1=referencia.rasgo1)
            else:
                familia = Producto.objects.filter(pk=referencia.pk)
            productos = list(familia.select_for_update().order_by('pk'))
            ids = [p.pk for p in productos]
            preparados = list(VariantePreparada.objects.select_for_update().filter(producto_id__in=ids))
            list(PiezaEtiqueta.objects.select_for_update().filter(variante__in=preparados))
            if (any(p.cantidad_actual or p.movimientos.exists() for p in productos)
                    or any(p.confirmada for p in preparados)
                    or ItemVenta.objects.filter(producto_id__in=ids).exists()):
                return JsonResponse({'message': 'No se eliminó nada: una variante tiene inventario confirmado o historial.'}, status=409)
            nombre = modelo.nombre if modelo else referencia.rasgo1 or referencia.sku
            PiezaEtiqueta.objects.filter(variante__in=preparados).delete()
            VariantePreparada.objects.filter(producto_id__in=ids).delete()
            Producto.objects.filter(pk__in=ids).delete()
            if modelo:
                modelo.delete()
            registrar_auditoria(usuario=request.active_profile, accion='ELIMINACION_PRODUCTO',
                detalles=f'Modelo de prueba {nombre}: {len(ids)} variantes eliminadas y etiquetas invalidadas', request=request)
        return JsonResponse({'status': 'ok'})
    except ProtectedError:
        return JsonResponse({'message': 'No se eliminó nada: el modelo está vinculado a otras operaciones.'}, status=409)
