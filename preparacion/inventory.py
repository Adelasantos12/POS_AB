"""Inventory list with complete model families and one row per variant."""

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render

from boutique.middleware import profile_permission_required
from boutique.models import Categoria, Color, Modelo, Producto, Talla, Tela
from boutique.views import es_admin
from .models import JornadaConteo, VariantePreparada


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
    todos = list(visibles)
    preparados = {producto_id: (pk, confirmada, estimada)
                  for producto_id, pk, confirmada, estimada in VariantePreparada.objects.filter(
        producto_id__in=[p.pk for p in todos]
    ).values_list('producto_id', 'pk', 'confirmada', 'cantidad_estimada')}
    agrupadas = {}
    for p in todos:
        p.en_preparacion = p.pk in preparados
        p.preparacion_id = preparados[p.pk][0] if p.en_preparacion else None
        p.pendiente_conteo = p.en_preparacion and preparados[p.pk][1] is None
        p.cantidad_estimada = preparados[p.pk][2] if p.en_preparacion else None
        clave = (('modelo', p.modelo_id) if p.modelo_id else
                 ('legacy', p.categoria_id, p.rasgo1) if p.rasgo1 else ('solo', p.pk))
        if clave not in agrupadas:
            agrupadas[clave] = {
                'id': p.pk, 'nombre': (p.modelo.nombre if p.modelo else p.rasgo1 or p.categoria.nombre),
                'categoria': p.categoria.nombre, 'foto_url': None, 'productos': [],
                'estimadas': 0, 'confirmadas': 0,
            }
        familia = agrupadas[clave]
        familia['productos'].append(p)
        familia['estimadas'] += p.cantidad_estimada if p.pendiente_conteo else 0
        familia['confirmadas'] += p.cantidad_actual if not p.pendiente_conteo else 0
        if not familia['foto_url']:
            foto = (p.modelo.foto_principal if p.modelo and p.modelo.foto_principal else p.foto)
            if foto:
                familia['foto_url'] = foto.url
    for familia in agrupadas.values():
        for p in familia['productos']:
            p.familia_foto_url = p.foto.url if p.foto else familia['foto_url']
    familias = Paginator(list(agrupadas.values()), 30).get_page(request.GET.get('page'))
    return render(request, 'boutique/inventario.html', {
        'familias': familias, 'q': q,
        'es_admin': es_admin(request.active_profile),
        'conteo_inicial_cerrado': JornadaConteo.objects.filter(abierta=False).exists(),
        'categorias': Categoria.objects.all().order_by('nombre'),
        'colores': Color.objects.filter(activo=True).order_by('nombre'),
        'tallas': Talla.objects.filter(activa=True).order_by('orden', 'nombre'),
        'modelos': Modelo.objects.all().order_by('nombre'),
        'telas': Tela.objects.filter(activa=True).order_by('nombre'),
    })
