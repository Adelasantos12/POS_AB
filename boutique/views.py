from django.shortcuts import render, redirect, get_object_or_404
from .forms import CustomUserCreationForm
from django.contrib.auth import login
from django.contrib.auth.models import Group
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Q
from .models import Producto, Categoria, Color, Venta, ItemVenta, Pago, Cliente, Grupo, IntegranteGrupo
import logging
import json
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

def index(request):
    """
    Vista para la página de inicio principal.
    """
    # De momento, solo renderiza una plantilla estática de bienvenida.
    # En el futuro, aquí se podrá añadir lógica para mostrar
    # un dashboard, ventas recientes, etc.
    return render(request, 'boutique/index.html')

def signup(request):
    """
    Vista para el registro de nuevos usuarios.
    """
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            try:
                user = form.save()
                # Asignar al grupo Vendedor por defecto
                # Usamos get_or_create para evitar el error 500 si el grupo no existe aún
                vendedor_group, _ = Group.objects.get_or_create(name='Vendedor')
                user.groups.add(vendedor_group)
                login(request, user)
                return redirect('index')
            except Exception as e:
                logger.exception("Error crítico durante el registro de usuario")
                # Re-lanzamos para que Django maneje el 500 pero con el log ya guardado
                raise e
    else:
        form = CustomUserCreationForm()
    return render(request, 'boutique/signup.html', {'form': form})

@login_required
def pos_dashboard(request):
    """Interfaz principal de Punto de Venta"""
    return render(request, 'boutique/pos_dashboard.html')

@require_POST
@login_required
def api_crear_producto_rapido(request):
    """Crea un producto de forma rápida desde la caja"""
    try:
        data = json.loads(request.body)
        cat_nombre = data.get('categoria', 'General')
        color_nombre = data.get('color', 'N/A')

        categoria, _ = Categoria.objects.get_or_create(nombre=cat_nombre)
        color, _ = Color.objects.get_or_create(nombre=color_nombre)

        producto = Producto.objects.create(
            categoria=categoria,
            color=color,
            rasgo1=data.get('rasgo1', ''),
            rasgo2=data.get('rasgo2', ''),
            talla=data.get('talla', 'U'),
            precio_venta=data.get('precio', 0),
            estado=data.get('estado', 'TIENDA'),
            cantidad_actual=1
        )
        return JsonResponse({'status': 'ok', 'sku': producto.sku, 'id': producto.id, 'text': str(producto)})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

@login_required
def api_search_productos(request):
    """Buscador de productos para el POS"""
    q = request.GET.get('q', '')
    productos = Producto.objects.filter(
        Q(sku__icontains=q) |
        Q(rasgo1__icontains=q) |
        Q(rasgo2__icontains=q) |
        Q(categoria__nombre__icontains=q)
    )[:15]
    results = [{'id': p.id, 'sku': p.sku, 'text': str(p), 'precio': float(p.precio_venta)} for p in productos]
    return JsonResponse({'results': results})

@require_POST
@login_required
def api_registrar_venta(request):
    """Registra una venta o apartado con pagos parciales"""
    try:
        data = json.loads(request.body)
        items = data.get('items', [])
        total = data.get('total', 0)
        pago_inicial = data.get('pago_inicial', total)
        metodo = data.get('metodo', 'EFECTIVO')

        venta = Venta.objects.create(
            vendedor=request.user,
            total=total
        )

        for it in items:
            prod = Producto.objects.get(id=it['id'])
            ItemVenta.objects.create(
                venta=venta,
                producto=prod,
                cantidad=it.get('cantidad', 1),
                precio_unitario=prod.precio_venta
            )
            if prod.estado == 'TIENDA' and prod.cantidad_actual > 0:
                prod.cantidad_actual -= it.get('cantidad', 1)
                prod.save()

        Pago.objects.create(
            venta=venta,
            monto=pago_inicial,
            metodo=metodo
        )

        return JsonResponse({'status': 'ok', 'venta_id': venta.id})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

def fuzzy_match(s1, s2):
    if not s1 or not s2: return 0
    return SequenceMatcher(None, s1.lower(), s2.lower()).ratio()

@require_POST
@login_required
def api_check_duplicados(request):
    """Verifica posibles duplicados antes de crear un producto"""
    data = json.loads(request.body)
    cat = data.get('categoria', '')
    r1 = data.get('rasgo1', '')
    r2 = data.get('rasgo2', '')
    color = data.get('color', '')

    # Filtro inicial amplio
    posibles = Producto.objects.filter(
        Q(categoria__nombre__icontains=cat) | Q(color__nombre__icontains=color)
    ).select_related('categoria', 'color')

    coincidencias = []
    for p in posibles:
        score = 0
        if p.categoria.nombre.lower() == cat.lower(): score += 0.4
        if p.color.nombre.lower() == color.lower(): score += 0.2

        s1 = fuzzy_match(p.rasgo1, r1)
        s2 = fuzzy_match(p.rasgo2, r2)
        score += (s1 * 0.2) + (s2 * 0.2)

        if score > 0.6:
            coincidencias.append({
                'id': p.id,
                'text': str(p),
                'sku': p.sku,
                'score': round(score * 100, 1)
            })

    coincidencias.sort(key=lambda x: x['score'], reverse=True)
    return JsonResponse({'duplicados': coincidencias[:5]})

@login_required
def agenda_view(request):
    """Vista de la agenda de grupos"""
    grupos = Grupo.objects.all().order_by('fecha_entrega')
    return render(request, 'boutique/agenda.html', {'grupos': grupos})
