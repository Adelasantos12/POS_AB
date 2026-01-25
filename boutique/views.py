from django.shortcuts import render, redirect, get_object_or_404
from .forms import CustomUserCreationForm
from django.contrib.auth import login, logout as auth_logout
from django.contrib.auth.models import Group, User
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum, Count
from django.db.models.functions import TruncDate
from .models import (
    Producto, Categoria, Color, Venta, ItemVenta, Pago, Cliente, 
    Grupo, IntegranteGrupo, CorteCaja, Tienda, MovimientoInventario,
    registrar_auditoria
)
from .middleware import profile_permission_required
from django.utils import timezone
from decimal import Decimal
import logging
import json
import csv
import os
import asyncio
from io import BytesIO
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

# Gemini API Key
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')


# ============================================================
# HELPERS Y UTILIDADES
# ============================================================

def get_caja_activa():
    """Obtiene la caja abierta del día actual"""
    return CorteCaja.objects.filter(cerrado=False).first()


def tiene_permiso(usuario, permiso_codigo):
    """Verifica si el perfil activo tiene un permiso específico"""
    if usuario.is_superuser:
        return True
    # Admin y Superadmin tienen todos los permisos
    if usuario.groups.filter(name__in=['Admin', 'Superadmin']).exists():
        return True
    # Verificar permisos específicos según rol
    permisos_rol = {
        'Caja': ['abrir_caja', 'vender', 'cobrar'],
        'Vendedor': ['vender', 'cobrar'],
        'Inventario': ['editar_inventario'],
        'Admin': ['abrir_caja', 'vender', 'cobrar', 'editar_inventario', 'ver_reportes', 'gestionar_usuarios'],
    }
    for grupo in usuario.groups.all():
        if permiso_codigo in permisos_rol.get(grupo.name, []):
            return True
    return False


def es_admin(usuario):
    """Verifica si el usuario tiene rol admin"""
    return usuario.is_superuser or usuario.groups.filter(name__in=['Admin', 'Superadmin']).exists()


# ============================================================
# VISTAS DE AUTENTICACIÓN Y PERFILES
# ============================================================

def index(request):
    """Vista para la página de inicio principal"""
    if request.user.is_authenticated:
        if not hasattr(request, 'active_profile') or not request.active_profile:
            return redirect('seleccionar_perfil')

        active_profile = request.active_profile

        # Si es vendedor/cajero sin rol admin
        if not es_admin(active_profile):
            corte = get_caja_activa()
            if not corte:
                return redirect('apertura_caja')
            return redirect('pos_dashboard')
        else:
            return redirect('admin_dashboard')

    return render(request, 'boutique/index.html')


@login_required
def seleccionar_perfil(request):
    """Lista de perfiles para seleccionar (estilo macOS)"""
    usuarios = User.objects.filter(is_active=True).prefetch_related('groups')
    return render(request, 'boutique/seleccionar_perfil.html', {'usuarios': usuarios})


@login_required
def autenticar_perfil(request):
    """Autentica el perfil seleccionado con contraseña"""
    if request.method == 'POST':
        user_id = request.POST.get('user_id')
        password = request.POST.get('password')
        user = get_object_or_404(User, id=user_id)

        if user.check_password(password):
            request.session['active_profile_id'] = user.id
            registrar_auditoria(
                usuario=user,
                accion='LOGIN_PERFIL',
                detalles=f'Perfil {user.username} activado',
                request=request
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
    """Cierra el perfil activo y vuelve a selección"""
    if hasattr(request, 'active_profile') and request.active_profile:
        registrar_auditoria(
            usuario=request.active_profile,
            accion='LOGOUT',
            detalles='Cambio de perfil',
            request=request
        )
    if 'active_profile_id' in request.session:
        del request.session['active_profile_id']
    return redirect('seleccionar_perfil')


def logout_view(request):
    """Cierra la sesión del terminal completamente"""
    if hasattr(request, 'active_profile') and request.active_profile:
        registrar_auditoria(
            usuario=request.active_profile,
            accion='LOGOUT',
            detalles='Cierre de sesión terminal',
            request=request
        )
    auth_logout(request)
    return redirect('index')


def signup(request):
    """Registro de nuevos usuarios"""
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            try:
                user = form.save()
                login(request, user)
                return redirect('index')
            except Exception as e:
                logger.exception("Error durante el registro de usuario")
                raise e
    else:
        form = CustomUserCreationForm()
    return render(request, 'boutique/signup.html', {'form': form})


# ============================================================
# VISTAS DE CAJA
# ============================================================

@login_required
def pos_dashboard(request):
    """Interfaz principal de Punto de Venta"""
    corte = get_caja_activa()
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
        corte = CorteCaja.objects.create(
            abierto_por=request.active_profile,
            monto_apertura=monto,
            efectivo_esperado=monto
        )
        registrar_auditoria(
            usuario=request.active_profile,
            accion='APERTURA_CAJA',
            detalles=f'Caja abierta con ${monto}',
            entidad=corte,
            request=request
        )
        return redirect('pos_dashboard')
    return render(request, 'boutique/apertura_caja.html')


@login_required
def cierre_caja(request):
    """Vista para cerrar la caja y confirmar montos"""
    corte = get_caja_activa()
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

        registrar_auditoria(
            usuario=request.active_profile,
            accion='CIERRE_CAJA',
            detalles=f'Diferencia: ${corte.diferencia}',
            entidad=corte,
            request=request
        )
        return redirect('index')

    # Calcular esperados desde ventas
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


# ============================================================
# API DE PRODUCTOS Y VENTAS
# ============================================================

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
    results = [{'id': p.id, 'sku': p.sku, 'text': str(p), 'precio': float(p.precio_venta), 'stock': p.cantidad_actual} for p in productos]
    return JsonResponse({'results': results})


@require_POST
@login_required
def api_registrar_venta(request):
    """Registra una venta con pagos"""
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
            cantidad = it.get('cantidad', 1)
            
            ItemVenta.objects.create(
                venta=venta,
                producto=prod,
                cantidad=cantidad,
                precio_unitario=prod.precio_venta
            )
            
            # Registrar movimiento de inventario
            if prod.cantidad_actual > 0:
                MovimientoInventario.objects.create(
                    producto=prod,
                    tipo='SALIDA',
                    cantidad=-cantidad,
                    motivo='VENTA',
                    perfil_activo=request.active_profile,
                    venta=venta,
                    stock_resultante=prod.cantidad_actual - cantidad
                )

        Pago.objects.create(
            venta=venta,
            monto=pago_inicial,
            metodo=metodo,
            registrado_por=request.active_profile
        )

        registrar_auditoria(
            usuario=request.active_profile,
            accion='VENTA',
            detalles=f'Venta #{venta.id} por ${total}',
            entidad=venta,
            request=request
        )

        return JsonResponse({'status': 'ok', 'venta_id': venta.id})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


def fuzzy_match(s1, s2):
    if not s1 or not s2:
        return 0
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

    posibles = Producto.objects.filter(
        Q(categoria__nombre__icontains=cat) | Q(color__nombre__icontains=color)
    ).select_related('categoria', 'color')

    coincidencias = []
    for p in posibles:
        score = 0
        if p.categoria.nombre.lower() == cat.lower():
            score += 0.4
        if p.color.nombre.lower() == color.lower():
            score += 0.2

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


# ============================================================
# VISTAS DE INVENTARIO
# ============================================================

@login_required
def inventario_view(request):
    """Vista de gestión de inventario"""
    q = request.GET.get('q', '')
    productos = Producto.objects.filter(
        Q(sku__icontains=q) |
        Q(rasgo1__icontains=q) |
        Q(rasgo2__icontains=q)
    ).select_related('categoria', 'color').order_by('-fecha_creacion')[:100]

    # Añadir nivel de stock visual
    for p in productos:
        if p.cantidad_actual == 0:
            p.nivel_stock = 'Agotado'
            p.nivel_class = 'danger'
        elif p.cantidad_actual <= 2:
            p.nivel_stock = 'Bajo'
            p.nivel_class = 'warning'
        elif p.cantidad_actual <= 5:
            p.nivel_stock = 'Normal'
            p.nivel_class = 'info'
        else:
            p.nivel_stock = 'Alto'
            p.nivel_class = 'success'

    return render(request, 'boutique/inventario.html', {
        'productos': productos,
        'q': q,
        'es_admin': es_admin(request.active_profile)
    })


@require_POST
@login_required
@profile_permission_required('Admin')
def api_eliminar_producto(request, pk):
    """Elimina un producto (solo Admin)"""
    producto = get_object_or_404(Producto, pk=pk)
    
    registrar_auditoria(
        usuario=request.active_profile,
        accion='ELIMINACION_PRODUCTO',
        detalles=f'Producto {producto.sku} eliminado',
        entidad=producto,
        request=request
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
        
        # Si cambia el stock, registrar movimiento
        nuevo_stock = int(data.get('stock', producto.cantidad_actual))
        if nuevo_stock != producto.cantidad_actual:
            diferencia = nuevo_stock - producto.cantidad_actual
            MovimientoInventario.objects.create(
                producto=producto,
                tipo='AJUSTE',
                cantidad=diferencia,
                motivo='AJUSTE_INVENTARIO',
                perfil_activo=request.active_profile,
                notas=f'Ajuste manual de {producto.cantidad_actual} a {nuevo_stock}',
                stock_resultante=nuevo_stock
            )
        
        producto.save()

        registrar_auditoria(
            usuario=request.active_profile,
            accion='EDICION_PRODUCTO',
            detalles=f'Producto {producto.sku} editado',
            entidad=producto,
            request=request
        )

        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@login_required
def imprimir_etiquetas(request):
    """Genera una página para imprimir etiquetas en lote"""
    ids = request.GET.get('ids', '').split(',')
    productos = Producto.objects.filter(id__in=[i for i in ids if i.isdigit()])
    return render(request, 'boutique/etiquetas_lote.html', {'productos': productos})


# ============================================================
# VISTAS DE AGENDA
# ============================================================

@login_required
def agenda_view(request):
    """Vista de la agenda de grupos"""
    grupos = Grupo.objects.all().order_by('fecha_entrega')
    return render(request, 'boutique/agenda.html', {'grupos': grupos})


# ============================================================
# DASHBOARD Y REPORTES
# ============================================================

@login_required
def admin_dashboard(request):
    """Dashboard para Administradores con analítica"""
    if not es_admin(request.active_profile):
        return redirect('index')

    # Ventas por día
    ventas_dia = Venta.objects.annotate(dia=TruncDate('fecha')).values('dia').annotate(
        total=Sum('total'),
        cantidad=Count('id')
    ).order_by('dia')

    # Ventas por categoría
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
    """Genera una estrategia de venta usando IA con Gemini"""
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    
    # Recopilar datos de ventas
    cat_top = ItemVenta.objects.values('producto__categoria__nombre').annotate(c=Sum('cantidad')).order_by('-c')[:5]
    color_top = ItemVenta.objects.values('producto__color__nombre').annotate(c=Sum('cantidad')).order_by('-c')[:5]
    
    # Ventas por día de la semana
    ventas_semana = Venta.objects.extra(select={'dia_semana': "strftime('%%w', fecha)"}).values('dia_semana').annotate(
        total=Sum('total'),
        cantidad=Count('id')
    ).order_by('dia_semana')
    
    # Stock bajo
    stock_bajo = Producto.objects.filter(cantidad_actual__lte=2).count()
    total_productos = Producto.objects.count()
    
    # Construir contexto para IA
    categorias = ', '.join([f"{c['producto__categoria__nombre']} ({c['c']} vendidos)" for c in cat_top]) if cat_top else 'Sin datos'
    colores = ', '.join([f"{c['producto__color__nombre']} ({c['c']} vendidos)" for c in color_top]) if color_top else 'Sin datos'
    
    prompt = f"""Eres un consultor de retail experto. Analiza estos datos de Adelé Boutique (Gdl) y da 3-4 recomendaciones concretas y accionables.

DATOS DE LA BOUTIQUE:
- Categorías más vendidas: {categorias}
- Colores más vendidos: {colores}
- Productos con stock bajo: {stock_bajo} de {total_productos}
- Mes actual: Enero 2026

Responde en español, de forma directa y práctica. Usa emojis para hacer la lectura más amigable. Máximo 200 palabras."""

    try:
        # Usar Gemini con la API key del usuario
        async def get_ai_response():
            chat = LlmChat(
                api_key=GEMINI_API_KEY,
                session_id=f"strategy_{request.active_profile.id}",
                system_message="Eres un consultor de retail experto en boutiques de moda. Das consejos prácticos y concretos."
            ).with_model("gemini", "gemini-2.0-flash")
            
            user_message = UserMessage(text=prompt)
            response = await chat.send_message(user_message)
            return response
        
        estrategia = asyncio.run(get_ai_response())
        
    except Exception as e:
        logger.error(f"Error con Gemini AI: {e}")
        # Fallback a respuesta simulada
        estrategia = f"""📊 **Análisis de Adelé Boutique**

Basado en tus datos:
- Top categorías: {categorias}
- Colores tendencia: {colores}

**Recomendaciones:**
1. 🎯 Refuerza el stock de tus categorías top antes del fin de semana
2. 🎨 Los colores que más vendes deberían tener más variedad de tallas
3. ⚠️ Tienes {stock_bajo} productos con stock bajo - revisa reposición
4. 💡 Considera una promoción "2x1" en categorías de menor rotación

_Nota: Respuesta generada localmente (error de conexión con IA)_"""

    return JsonResponse({'estrategia': estrategia})


# ============================================================
# EXPORTACIÓN DE REPORTES
# ============================================================

@login_required
@profile_permission_required('Admin')
def exportar_inventario_csv(request):
    """Exporta el catálogo de productos a CSV"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="inventario_byeasy.csv"'

    writer = csv.writer(response)
    writer.writerow(['SKU', 'Categoria', 'Rasgo 1', 'Rasgo 2', 'Color', 'Talla', 'Precio', 'Stock'])

    productos = Producto.objects.all().select_related('categoria', 'color')
    for p in productos:
        writer.writerow([p.sku, p.categoria.nombre, p.rasgo1, p.rasgo2, p.color.nombre, p.talla, p.precio_venta, p.cantidad_actual])

    registrar_auditoria(
        usuario=request.active_profile,
        accion='EXPORTACION',
        detalles='Exportación CSV inventario',
        request=request
    )

    return response


@login_required
@profile_permission_required('Admin')
def exportar_ventas_csv(request):
    """Exporta el historial de ventas a CSV"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="ventas_byeasy.csv"'

    writer = csv.writer(response)
    writer.writerow(['ID Venta', 'Fecha', 'Vendedor', 'Total', 'Metodos de Pago'])

    ventas = Venta.objects.all().select_related('vendedor').prefetch_related('pagos')
    for v in ventas:
        metodos = ", ".join([p.metodo for p in v.pagos.all()])
        writer.writerow([v.id, v.fecha.strftime('%Y-%m-%d %H:%M'), v.vendedor.username, v.total, metodos])

    registrar_auditoria(
        usuario=request.active_profile,
        accion='EXPORTACION',
        detalles='Exportación CSV ventas',
        request=request
    )

    return response


@login_required
@profile_permission_required('Admin')
def exportar_inventario_excel(request):
    """Exporta inventario a Excel con formato"""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    
    wb = Workbook()
    ws = wb.active
    ws.title = "Inventario"
    
    # Estilos
    header_fill = PatternFill(start_color="2563EB", end_color="2563EB", fill_type="solid")
    header_font = Font(color="FFFFFF", bold=True)
    thin_border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )
    
    # Título
    ws['A1'] = "Inventario ByEasy - Adelé Boutique"
    ws['A1'].font = Font(size=16, bold=True)
    ws.merge_cells('A1:H1')
    
    # Fecha
    ws['A2'] = f"Generado: {timezone.now().strftime('%Y-%m-%d %H:%M')}"
    
    # Headers
    headers = ['SKU', 'Categoría', 'Rasgo 1', 'Rasgo 2', 'Color', 'Talla', 'Precio', 'Stock']
    for col, header in enumerate(headers, 1):
        cell = ws.cell(row=4, column=col, value=header)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center')
        cell.border = thin_border
    
    # Datos
    productos = Producto.objects.all().select_related('categoria', 'color')
    for row, p in enumerate(productos, 5):
        ws.cell(row=row, column=1, value=p.sku).border = thin_border
        ws.cell(row=row, column=2, value=p.categoria.nombre).border = thin_border
        ws.cell(row=row, column=3, value=p.rasgo1).border = thin_border
        ws.cell(row=row, column=4, value=p.rasgo2).border = thin_border
        ws.cell(row=row, column=5, value=p.color.nombre).border = thin_border
        ws.cell(row=row, column=6, value=p.talla).border = thin_border
        ws.cell(row=row, column=7, value=float(p.precio_venta)).border = thin_border
        ws.cell(row=row, column=8, value=p.cantidad_actual).border = thin_border
    
    # Ajustar anchos
    for col in range(1, 9):
        ws.column_dimensions[chr(64 + col)].width = 15
    
    # Guardar
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    
    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="inventario_byeasy.xlsx"'
    
    registrar_auditoria(
        usuario=request.active_profile,
        accion='EXPORTACION',
        detalles='Exportación Excel inventario',
        request=request
    )
    
    return response


@login_required
@profile_permission_required('Admin')
def exportar_ventas_pdf(request):
    """Exporta ventas a PDF"""
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    
    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()
    
    # Título
    elements.append(Paragraph("Reporte de Ventas - Adelé Boutique (Gdl)", styles['Heading1']))
    elements.append(Paragraph(f"Generado: {timezone.now().strftime('%Y-%m-%d %H:%M')}", styles['Normal']))
    elements.append(Spacer(1, 20))
    
    # Datos
    data = [['ID', 'Fecha', 'Vendedor', 'Total', 'Método']]
    ventas = Venta.objects.all().select_related('vendedor').prefetch_related('pagos')[:100]
    
    for v in ventas:
        metodos = ", ".join([p.metodo for p in v.pagos.all()])
        data.append([
            str(v.id),
            v.fecha.strftime('%Y-%m-%d'),
            v.vendedor.username,
            f"${v.total}",
            metodos
        ])
    
    # Tabla
    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2563EB')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    
    elements.append(table)
    doc.build(elements)
    
    output.seek(0)
    response = HttpResponse(output.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="ventas_byeasy.pdf"'
    
    registrar_auditoria(
        usuario=request.active_profile,
        accion='EXPORTACION',
        detalles='Exportación PDF ventas',
        request=request
    )
    
    return response


# ============================================================
# GESTIÓN DE USUARIOS
# ============================================================

@login_required
@profile_permission_required('Admin')
def gestion_usuarios(request):
    """Lista de personal de la boutique (solo Admin)"""
    usuarios = User.objects.all().prefetch_related('groups').order_by('username')
    
    # Añadir info de permisos legibles
    for u in usuarios:
        u.permisos_texto = []
        grupos = u.groups.all()
        for g in grupos:
            if g.name == 'Caja':
                u.permisos_texto.extend(['Puede abrir caja', 'Puede vender'])
            elif g.name == 'Vendedor':
                u.permisos_texto.extend(['Puede vender', 'Puede cobrar'])
            elif g.name == 'Inventario':
                u.permisos_texto.append('Puede editar inventario')
            elif g.name in ['Admin', 'Superadmin']:
                u.permisos_texto.append('Acceso total')
    
    return render(request, 'boutique/usuarios_list.html', {'usuarios': usuarios})


@login_required
@profile_permission_required('Admin')
def editar_usuario(request, pk):
    """Edita el rol y estado de un usuario (solo Admin)"""
    usuario = get_object_or_404(User, pk=pk)
    grupos = Group.objects.all()

    if request.method == 'POST':
        # Actualizar estado
        is_active = request.POST.get('is_active') == 'on'
        usuario.is_active = is_active
        
        # Actualizar roles (múltiples)
        roles_ids = request.POST.getlist('roles')
        usuario.groups.clear()
        for rol_id in roles_ids:
            grupo = Group.objects.get(id=rol_id)
            usuario.groups.add(grupo)
        
        usuario.save()
        
        registrar_auditoria(
            usuario=request.active_profile,
            accion='EDICION_USUARIO',
            detalles=f'Usuario {usuario.username} editado. Roles: {[g.name for g in usuario.groups.all()]}',
            entidad=usuario,
            request=request
        )
        
        return redirect('gestion_usuarios')

    return render(request, 'boutique/usuario_form.html', {'u': usuario, 'grupos': grupos})


@login_required
@profile_permission_required('Admin')
def resetear_password(request, pk):
    """Resetea la contraseña de un usuario"""
    if request.method == 'POST':
        usuario = get_object_or_404(User, pk=pk)
        nueva_password = request.POST.get('nueva_password')
        
        if nueva_password:
            usuario.set_password(nueva_password)
            usuario.save()
            
            registrar_auditoria(
                usuario=request.active_profile,
                accion='EDICION_USUARIO',
                detalles=f'Contraseña de {usuario.username} reseteada',
                entidad=usuario,
                request=request
            )
            
            return JsonResponse({'status': 'ok', 'message': 'Contraseña actualizada'})
        
    return JsonResponse({'status': 'error', 'message': 'Contraseña requerida'}, status=400)


@login_required
@profile_permission_required('Admin')
def historial_usuario(request, pk):
    """Ver historial de acciones de un usuario"""
    usuario = get_object_or_404(User, pk=pk)
    from .models import Auditoria
    historial = Auditoria.objects.filter(usuario=usuario).order_by('-timestamp')[:50]
    
    return render(request, 'boutique/usuario_historial.html', {
        'u': usuario,
        'historial': historial
    })
