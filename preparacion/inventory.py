"""Inventory list with complete model families and one row per variant."""

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render

from boutique.middleware import profile_permission_required
from boutique.models import Categoria, Color, Modelo, Producto, Talla, Tela
from boutique.views import es_admin
from .models import VariantePreparada


@login_required
@profile_permission_required(['Inventario', 'Vendedor'])
def inventario_view(request):
    q = request.GET.get('q', '').strip()
    visibles = Producto.objects.filter(Q(activo=True) | Q(preparacion__isnull=False))
    if q:
        encontrados = visibles.filter(
            Q(sku__icontains=q) | Q(rasgo1__icontains=q) |
            Q(rasgo2__icontains=q) | Q(modelo__nombre__icontains=q) |
            Q(color__nombre__icontains=q) | Q(tela__nombre__icontains=q)
        )
        ids = list(encontrados.values_list('pk', flat=True))
        modelos = list(encontrados.exclude(modelo__isnull=True)
                       .values_list('modelo_id', flat=True).distinct())
        familias_sin_modelo = encontrados.filter(modelo__isnull=True).exclude(
            rasgo1='').values_list('categoria_id', 'rasgo1').distinct()
        familiares = Q(pk__in=ids) | Q(modelo_id__in=modelos)
        for categoria_id, rasgo1 in familias_sin_modelo:
            familiares |= Q(modelo__isnull=True, categoria_id=categoria_id, rasgo1=rasgo1)
        visibles = visibles.filter(familiares)
    visibles = visibles.select_related('categoria', 'color', 'modelo', 'tela').order_by(
        'modelo__nombre', 'rasgo1', 'color__nombre', 'tela__nombre', 'talla', 'pk')
    productos = Paginator(visibles, 100).get_page(request.GET.get('page'))
    preparados = dict(VariantePreparada.objects.filter(
        producto_id__in=[p.pk for p in productos]
    ).values_list('producto_id', 'pk'))
    for p in productos:
        p.en_preparacion = p.pk in preparados
        p.preparacion_id = preparados.get(p.pk)
    return render(request, 'boutique/inventario.html', {
        'productos': productos, 'q': q,
        'es_admin': es_admin(request.active_profile),
        'categorias': Categoria.objects.all().order_by('nombre'),
        'colores': Color.objects.filter(activo=True).order_by('nombre'),
        'tallas': Talla.objects.filter(activa=True).order_by('orden', 'nombre'),
        'modelos': Modelo.objects.all().order_by('nombre'),
        'telas': Tela.objects.filter(activa=True).order_by('nombre'),
    })
