from django.shortcuts import render, redirect, get_object_or_404
from .forms import CustomUserCreationForm
from django.contrib.auth import login
from django.contrib.auth.models import Group, User
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Q, Sum, Count
from django.db.models.functions import TruncDate
from .models import Producto, Categoria, Color, Venta, ItemVenta, Pago, Cliente, Grupo, IntegranteGrupo, CorteCaja, Auditoria
from .middleware import profile_permission_required
from django.utils import timezone
from decimal import Decimal
from django.http import HttpResponse
import logging
import json
import csv
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

def index(request):
    """
    Vista para la página de inicio principal.
    """
    if request.user.is_authenticated:
        # Si no hay perfil activo, forzar selección
        if 'active_profile_id' not in request.session:
            return redirect('seleccionar_perfil')

        active_profile = User.objects.get(id=request.session['active_profile_id'])

        # Si es vendedor, mandarlo al POS o a abrir caja
        if not active_profile.is_superuser and not active_profile.groups.filter(name='Admin').exists():
            corte = CorteCaja.objects.filter(cerrado=False).first()
            if not corte:
                return redirect('apertura_caja')
            return redirect('pos_dashboard')
        else:
            # Si es admin, mandarlo al dashboard de admin
            return redirect('admin_dashboard')

    return render(request, 'boutique/index.html')

@login_required
def seleccionar_perfil(request):
    usuarios = User.objects.filter(is_active=True).prefetch_related('groups')
    return render(request, 'boutique/seleccionar_perfil.html', {'usuarios': usuarios})

@login_required
def autenticar_perfil(request):
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        password = request.POST.get('password')
        user = get_object_or_404(User, id=user_id)

        if user.check_password(password):
            request.session['active_profile_id'] = user.id
            Auditoria.objects.create(
                usuario=user,
                accion='Selección de Perfil',
                detalles=f'Perfil {user.username} activado'
            )
            return redirect('index')
        else:
            return render(request, 'boutique/autenticar_perfil.html', {
                'u': user,
                'error': 'Contraseña incorrecta'
            })

    user_id = request.GET.get('user_id')
    user = get_object_or_404(User, id=user_id)
    return render(request, 'boutique/autenticar_perfil.html', {'u': user})

@login_required
def cambiar_perfil(request):
    if 'active_profile_id' in request.session:
        del request.session['active_profile_id']
    return redirect('seleccionar_perfil')

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
    corte = CorteCaja.objects.filter(cerrado=False).first()
    if not corte:
        return redirect('apertura_caja')
    return render(request, 'boutique/pos_dashboard.html', {'corte': corte})

@login_required
def apertura_caja(request):
    """Vista para abrir la caja del día"""
    if CorteCaja.objects.filter(cerrado=False).exists():
        return redirect('pos_dashboard')

    if request.method == 'POST':
        monto = request.POST.get('monto_apertura', 0)
        CorteCaja.objects.create(
            abierto_por=request.active_profile,
            monto_apertura=monto,
            efectivo_esperado=monto
        )
        # Auditoría
        Auditoria.objects.create(
            usuario=request.active_profile,
            accion='Apertura de Caja',
            detalles=f'Caja abierta con {monto}'
        )
        return redirect('pos_dashboard')
    return render(request, 'boutique/apertura_caja.html')

@login_required
def cierre_caja(request):
    """Vista para cerrar la caja y confirmar montos"""
    corte = CorteCaja.objects.filter(cerrado=False).first()
    if not corte:
        return redirect('apertura_caja')

    if request.method == 'POST':
        efectivo_real = Decimal(request.POST.get('efectivo_real', 0))
        tarjeta_real = Decimal(request.POST.get('tarjeta_real', 0))

        corte.efectivo_real = efectivo_real
        corte.tarjeta_real = tarjeta_real
        corte.fecha_cierre = timezone.now()
        corte.cerrado = True
        corte.diferencia = (efectivo_real + tarjeta_real) - (corte.efectivo_esperado + corte.tarjeta_esperada)
        corte.observaciones = request.POST.get('observaciones', '')
        corte.save()

        # Auditoría
        Auditoria.objects.create(
            usuario=request.active_profile,
            accion='Cierre de Caja',
            detalles=f'Caja cerrada con diferencia de {corte.diferencia}'
        )
        return redirect('index')

    # Calcular esperados desde ventas del día vinculadas a este corte
    # (Ahora usamos todas las ventas desde la apertura del corte, sin importar quién las hizo)
    ventas = Venta.objects.filter(fecha__gte=corte.fecha_apertura)
    pagos = Pago.objects.filter(venta__in=ventas)

    efectivo_ventas = sum(p.monto for p in pagos if p.metodo == 'EFECTIVO')
    tarjeta_ventas = sum(p.monto for p in pagos if p.metodo == 'TARJETA')

    corte.efectivo_esperado = Decimal(corte.monto_apertura) + efectivo_ventas
    corte.tarjeta_esperada = tarjeta_ventas
    corte.save()

    return render(request, 'boutique/cierre_caja.html', {
        'corte': corte,
        'efectivo_ventas': efectivo_ventas,
        'tarjeta_ventas': tarjeta_ventas
    })

@require_POST
@login_required
@profile_permission_required('Vendedor')
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
            vendedor=request.active_profile,
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
            metodo=metodo,
            registrado_por=request.active_profile
        )

        # Auditoría
        Auditoria.objects.create(
            usuario=request.active_profile,
            accion='Registro de Venta',
            detalles=f'Venta #{venta.id} por total de {total}'
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

@login_required
def imprimir_etiquetas(request):
    """Genera una página para imprimir etiquetas en lote"""
    # Permitimos a Vendedores imprimir etiquetas de los productos que gestionan
    ids = request.GET.get('ids', '').split(',')
    productos = Producto.objects.filter(id__in=[i for i in ids if i.isdigit()])
    return render(request, 'boutique/etiquetas_lote.html', {'productos': productos})

@login_required
def admin_dashboard(request):
    """Dashboard para Administradores con analítica"""
    if not (request.active_profile.is_superuser or request.active_profile.groups.filter(name='Admin').exists()):
        return redirect('index')

    # Ventas por día (últimos 30 días)
    ventas_dia = Venta.objects.annotate(dia=TruncDate('fecha')).values('dia').annotate(
        total=Sum('total'),
        cantidad=Count('id')
    ).order_by('dia')

    # Ventas por modelo/categoría
    ventas_cat = ItemVenta.objects.values('producto__categoria__nombre').annotate(
        total=Sum('cantidad')
    ).order_by('-total')

    # Ventas por Color
    ventas_color = ItemVenta.objects.values('producto__color__nombre').annotate(
        total=Sum('cantidad')
    ).order_by('-total')

    context = {
        'ventas_dia': list(ventas_dia),
        'ventas_cat': list(ventas_cat),
        'ventas_color': list(ventas_color),
        'total_mensual': Venta.objects.filter(fecha__month=timezone.now().month).aggregate(Sum('total'))['total__sum'] or 0
    }
    return render(request, 'boutique/admin_dashboard.html', context)

@require_POST
@login_required
@profile_permission_required('Admin')
def api_ai_strategy(request):
    """Genera una estrategia de venta usando IA (Simulado)"""

    # Recopilar datos para el prompt
    cat_top = ItemVenta.objects.values('producto__categoria__nombre').annotate(c=Sum('cantidad')).order_by('-c')[:3]
    color_top = ItemVenta.objects.values('producto__color__nombre').annotate(c=Sum('cantidad')).order_by('-c')[:3]

    resumen = f"Categorías más vendidas: {', '.join([c['producto__categoria__nombre'] for c in cat_top])}. "
    resumen += f"Colores tendencia: {', '.join([c['producto__color__nombre'] for c in color_top])}."

    # Simulación de respuesta de IA basada en los datos reales
    estrategia = f"Basado en tus datos ({resumen}), se recomienda: \n"
    estrategia += "1. Aumentar stock de los colores tendencia para la próxima temporada.\n"
    estrategia += "2. Lanzar una promoción 'Combo' para las categorías menos movidas.\n"
    estrategia += "3. Los fines de semana muestran mayor volumen, considera reforzar el equipo esos días."

    return JsonResponse({'estrategia': estrategia})

@login_required
@profile_permission_required('Admin')
def exportar_inventario_csv(request):
    """Exporta el catálogo de productos a CSV"""

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="inventario_adele.csv"'

    writer = csv.writer(response)
    writer.writerow(['SKU', 'Categoria', 'Rasgo 1', 'Rasgo 2', 'Color', 'Talla', 'Precio', 'Stock'])

    productos = Producto.objects.all().select_related('categoria', 'color')
    for p in productos:
        writer.writerow([p.sku, p.categoria.nombre, p.rasgo1, p.rasgo2, p.color.nombre, p.talla, p.precio_venta, p.cantidad_actual])

    return response

@login_required
@profile_permission_required('Admin')
def exportar_ventas_csv(request):
    """Exporta el historial de ventas a CSV"""

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="ventas_adele.csv"'

    writer = csv.writer(response)
    writer.writerow(['ID Venta', 'Fecha', 'Vendedor', 'Total', 'Metodos de Pago'])

    ventas = Venta.objects.all().select_related('vendedor').prefetch_related('pagos')
    for v in ventas:
        metodos = ", ".join([p.metodo for p in v.pagos.all()])
        writer.writerow([v.id, v.fecha.strftime('%Y-%m-%d %H:%M'), v.vendedor.username, v.total, metodos])

    return response

@login_required
def inventario_view(request):
    """Vista de gestión de inventario con RBAC"""
    q = request.GET.get('q', '')
    productos = Producto.objects.filter(
        Q(sku__icontains=q) |
        Q(rasgo1__icontains=q) |
        Q(rasgo2__icontains=q)
    ).select_related('categoria', 'color').order_by('-fecha_creacion')[:100]

    es_admin = request.active_profile.is_superuser or request.active_profile.groups.filter(name='Admin').exists()

    return render(request, 'boutique/inventario.html', {
        'productos': productos,
        'q': q,
        'es_admin': es_admin
    })

@require_POST
@login_required
@profile_permission_required('Admin')
def api_eliminar_producto(request, pk):
    """Elimina un producto (solo Admin)"""
    producto = get_object_or_404(Producto, pk=pk)

    # Auditoría
    Auditoria.objects.create(
        usuario=request.active_profile,
        accion='Eliminación de Producto',
        detalles=f'Producto {producto.sku} eliminado'
    )

    producto.delete()
    return JsonResponse({'status': 'ok'})

@require_POST
@login_required
@profile_permission_required('Admin')
def api_editar_producto(request, pk):
    """Edita un producto (solo Admin)"""
    data = json.loads(request.body)
    producto = get_object_or_404(Producto, pk=pk)

    try:
        producto.rasgo1 = data.get('rasgo1', producto.rasgo1)
        producto.rasgo2 = data.get('rasgo2', producto.rasgo2)
        producto.precio_venta = Decimal(data.get('precio', producto.precio_venta))
        producto.cantidad_actual = int(data.get('stock', producto.cantidad_actual))
        producto.save()

        # Auditoría
        Auditoria.objects.create(
            usuario=request.active_profile,
            accion='Edición de Producto',
            detalles=f'Producto {producto.sku} editado'
        )

        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

@login_required
@profile_permission_required('Admin')
def gestion_usuarios(request):
    """Lista de personal de la boutique (solo Admin)"""
    usuarios = User.objects.all().prefetch_related('groups').order_by('username')
    return render(request, 'boutique/usuarios_list.html', {'usuarios': usuarios})

@login_required
@profile_permission_required('Admin')
def editar_usuario(request, pk):
    """Edita el rol de un usuario (solo Admin)"""

    usuario = get_object_or_404(User, pk=pk)
    grupos = Group.objects.all()

    if request.method == 'POST':
        grupo_id = request.POST.get('grupo')
        if grupo_id:
            grupo = Group.objects.get(id=grupo_id)
            usuario.groups.clear()
            usuario.groups.add(grupo)
            return redirect('gestion_usuarios')

    return render(request, 'boutique/usuario_form.html', {'u': usuario, 'grupos': grupos})
