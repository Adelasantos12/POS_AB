"""Task-oriented screens; reuse existing, locked inventory operations."""
import json
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods
from boutique.middleware import profile_permission_required
from boutique.views import es_admin
from .models import JornadaConteo, PiezaEtiqueta


@login_required
@profile_permission_required(['Inventario', 'Vendedor'])
def operacion(request, tipo):
    personas = list(PiezaEtiqueta.objects.exclude(encargado='').values_list('encargado', flat=True).distinct().order_by('encargado')[:100])
    return render(request, 'preparacion/operacion.html', {
        'tipo': tipo, 'titulo': 'Entradas' if tipo == 'ENTRADA' else 'Salidas',
        'personas': personas, 'es_admin': es_admin(request.active_profile),
        'conteo_iniciado': JornadaConteo.objects.exists(),
    })


@require_http_methods(['GET', 'POST'])
@login_required
@profile_permission_required(['Inventario', 'Vendedor'])
def borrador(request, tipo):
    key = f'prendas_borrador_{request.active_profile.pk}_{tipo}'
    if request.method == 'GET':
        return JsonResponse({'borrador': request.session.get(key)})
    if len(request.body) > 100000:
        return JsonResponse({'message': 'La selección es demasiado grande.'}, status=400)
    try:
        data = json.loads(request.body)
        if not isinstance(data, dict):
            raise ValueError()
        if data.get('limpiar'):
            request.session.pop(key, None)
        else:
            if len(data.get('piezas', [])) > 100:
                raise ValueError()
            request.session[key] = data
        request.session.modified = True
        return JsonResponse({'ok': True})
    except (ValueError, TypeError):
        return JsonResponse({'message': 'No se pudo guardar el borrador.'}, status=400)


@login_required
@profile_permission_required(['Inventario', 'Vendedor'])
def buscar(request):
    from django.core.paginator import Paginator
    from django.db.models import Q
    from .movements import piezas_detalle
    q = request.GET.get('q', '').strip()
    lugar = request.GET.get('ubicacion', '')
    prendas = piezas_detalle().order_by('-pk')
    if q:
        prendas = prendas.filter(Q(codigo__icontains=q) | Q(variante__producto__sku__icontains=q) |
            Q(variante__producto__modelo__nombre__icontains=q) | Q(variante__producto__rasgo1__icontains=q))
    if lugar in dict(PiezaEtiqueta.UBICACIONES):
        prendas = prendas.filter(ubicacion=lugar, vendida__isnull=True, contada__isnull=False)
    return render(request, 'preparacion/buscar_prendas.html', {
        'piezas': Paginator(prendas, 30).get_page(request.GET.get('page')),
        'q': q, 'lugar': lugar, 'ubicaciones': PiezaEtiqueta.UBICACIONES})
