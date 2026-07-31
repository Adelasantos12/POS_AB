from django.shortcuts import render, redirect, get_object_or_404
from .forms import CustomUserCreationForm
from django.contrib.auth import login, logout as auth_logout
from django.contrib.auth.models import Group, User
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q, Sum, Count
from django.db.models.functions import TruncDate
from .models import (
    Producto, Categoria, Color, Venta, ItemVenta, Pago, Cliente,
    CorteCaja, Tienda, MovimientoInventario, Modelo, Tela, Talla,
    registrar_auditoria, Ticket, Pedido, Apartado, Novia, Dama
)
from .middleware import profile_permission_required
from .utils import safe_decimal, normalizar_nombre, nombres_son_iguales
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
import logging
import json
import csv
import os
from io import BytesIO
from difflib import SequenceMatcher
from django.conf import settings

logger = logging.getLogger(__name__)


@login_required
def api_search_global(request):
    """
    Buscador global para POS: Productos, Pedidos, Apartados y Novias.
    Habilita el cobro desde cualquier módulo.
    """
    q = request.GET.get('q', '').strip()
    if not q:
        return JsonResponse({'results': []})

    results = []

    # 1. Productos (SKU, Rasgos, Categoría)
    productos = Producto.objects.filter(
        Q(sku__icontains=q) |
        Q(rasgo1__icontains=q) |
        Q(rasgo2__icontains=q) |
        Q(categoria__nombre__icontains=q)
    ).select_related('categoria', 'color', 'modelo')[:10]

    for p in productos:
        results.append({
            'type': 'PRODUCTO',
            'id': p.id,
            'sku': p.sku,
            'text': str(p),
            'precio': float(p.precio_venta),
            'stock': p.cantidad_actual,
            'folio': p.sku,
            'foto_url': p.foto.url if p.foto else None,
        })

    # 2. Apartados (Folio, Cliente, Teléfono)
    apartados = Apartado.objects.filter(
        Q(folio__icontains=q) |
        Q(cliente_nombre__icontains=q) |
        Q(cliente_telefono__icontains=q)
    ).order_by('-fecha_creacion')[:10]

    for a in apartados:
        results.append({
            'type': 'APARTADO',
            'id': a.id,
            'folio': a.folio,
            'label': f"Apartado: {a.folio}",
            'customer': a.cliente_nombre,
            'telefono': a.cliente_telefono,
            'detalle': f"{a.categoria_cache} {a.color_cache} {a.talla_cache}".strip(),
            'total': float(a.total),
            'balance': float(a.saldo),
            'delivery_date': a.fecha_entrega_estimada.isoformat() if a.fecha_entrega_estimada else None,
            'status': a.get_estado_display(),
            'status_code': a.estado,
        })

    # 3. Pedidos (Folio, Cliente, Novia, Dama, Teléfono, Modelo, Color, Talla)
    pedidos = Pedido.objects.filter(
        Q(numero_ticket__icontains=q) |
        Q(novia__nombre__icontains=q) |
        Q(dama__nombre__icontains=q) |
        Q(cliente__nombre__icontains=q) |
        Q(cliente__telefono__icontains=q) |
        Q(novia__telefono__icontains=q) |
        Q(dama__telefono__icontains=q)
    ).select_related('novia', 'dama', 'cliente', 'modelo', 'color').order_by('-fecha_creacion')[:10]

    for ped in pedidos:
        customer, telefono = "", ""
        if ped.dama:
            customer, telefono = ped.dama.nombre, ped.dama.telefono or ""
        elif ped.novia:
            customer, telefono = ped.novia.nombre, ped.novia.telefono or ""
        elif ped.cliente:
            customer, telefono = ped.cliente.nombre, ped.cliente.telefono or ""

        detalle_parts = []
        if ped.modelo: detalle_parts.append(ped.modelo.nombre)
        if ped.color: detalle_parts.append(ped.color.nombre)
        if ped.talla: detalle_parts.append(f"T:{ped.talla}")

        results.append({
            'type': 'PEDIDO',
            'id': ped.id,
            'folio': ped.numero_ticket,
            'label': f"Pedido: {ped.numero_ticket}",
            'customer': customer,
            'telefono': telefono,
            'detalle': " · ".join(detalle_parts),
            'total': float(ped.precio),
            'balance': float(ped.saldo_pendiente),
            'delivery_date': ped.fecha_entrega_estimada.isoformat() if ped.fecha_entrega_estimada else None,
            'status': ped.get_estado_display(),
            'status_code': ped.estado,
        })

    # 4. Novias (Nombre, Teléfono) — prefetch to avoid N+1
    novias = Novia.objects.filter(
        Q(nombre__icontains=q) |
        Q(telefono__icontains=q)
    ).filter(activo=True).prefetch_related('pedidos__pagos_pedido')[:5]

    for n in novias:
        pedidos_n = list(n.pedidos.all())
        total_n = sum(p.precio for p in pedidos_n)
        pendiente_n = sum(p.saldo_pendiente for p in pedidos_n)
        results.append({
            'type': 'NOVIA',
            'id': n.id,
            'folio': f"NV-{n.id}",
            'label': f"Novia: {n.nombre}",
            'customer': n.nombre,
            'telefono': n.telefono,
            'detalle': f"Boda: {n.fecha_boda.strftime('%d/%m/%Y') if n.fecha_boda else '—'}",
            'total': float(total_n),
            'balance': float(pendiente_n),
            'delivery_date': n.fecha_entrega.isoformat() if n.fecha_entrega else None,
            'status': 'Activa',
            'status_code': 'ACTIVA',
        })

    return JsonResponse({'results': results})


@login_required
@profile_permission_required('Vendedor')
def api_ai_analyze_image(request):
    """Analiza imagen de producto usando Gemini Vision"""
    from .ai_utils import analyze_product_image
    if request.method == 'POST' and request.FILES.get('image'):
        try:
            image_file = request.FILES['image']
            image_data = image_file.read()
            mime_type = image_file.content_type or 'image/jpeg'

            atributos = analyze_product_image(image_data, mime_type=mime_type)
            if atributos:
                # Validar contra catálogo
                cat_exists = Categoria.objects.filter(nombre=atributos.get('categoria')).exists()
                if not cat_exists: atributos['categoria'] = None

                col_exists = Color.objects.filter(nombre=atributos.get('color')).exists()
                if not col_exists: atributos['color'] = None

                tela_exists = Tela.objects.filter(nombre=atributos.get('rasgo2')).exists()
                if not tela_exists: atributos['rasgo2'] = None

                return JsonResponse({'status': 'ok', 'atributos': atributos})
            else:
                return JsonResponse({'status': 'error', 'message': 'No se pudo analizar la imagen'}, status=500)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'error', 'message': 'Método no permitido o imagen faltante'}, status=405)


@login_required
@profile_permission_required('Vendedor')
def api_ai_extract_attributes(request):
    """Extrae atributos de producto desde una descripción usando Gemini"""
    from .ai_utils import extract_product_attributes
    try:
        data = json.loads(request.body)
        descripcion = data.get('descripcion', '')
        if not descripcion:
            return JsonResponse({'status': 'error', 'message': 'Descripción vacía'}, status=400)

        atributos = extract_product_attributes(descripcion)
        if atributos:
            # Validar contra catálogo
            cat_exists = Categoria.objects.filter(nombre=atributos.get('categoria')).exists()
            if not cat_exists: atributos['categoria'] = None

            col_exists = Color.objects.filter(nombre=atributos.get('color')).exists()
            if not col_exists: atributos['color'] = None

            tela_exists = Tela.objects.filter(nombre=atributos.get('rasgo2')).exists()
            if not tela_exists: atributos['rasgo2'] = None

            return JsonResponse({'status': 'ok', 'atributos': atributos})
        else:
            return JsonResponse({'status': 'error', 'message': 'No se pudo procesar la descripción'}, status=500)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


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
    # Admin, Superadmin y CEO tienen todos los permisos
    if usuario.groups.filter(name__in=['Admin', 'Superadmin', 'CEO']).exists():
        return True
    # Verificar permisos específicos según rol
    permisos_rol = {
        'Caja': ['abrir_caja', 'vender', 'cobrar'],
        'Vendedor': ['vender', 'cobrar'],
        'Inventario': ['editar_inventario'],
        'Admin': ['abrir_caja', 'vender', 'cobrar', 'editar_inventario', 'ver_reportes', 'gestionar_usuarios'],
        'CEO': ['abrir_caja', 'vender', 'cobrar', 'editar_inventario', 'ver_reportes', 'gestionar_usuarios', 'ver_todo'],
    }
    for grupo in usuario.groups.all():
        if permiso_codigo in permisos_rol.get(grupo.name, []):
            return True
    return False


def es_admin(usuario):
    """Verifica si el usuario tiene rol admin, CEO o Supervisora"""
    return usuario.is_superuser or usuario.groups.filter(name__in=['Admin', 'Superadmin', 'CEO', 'Supervisora']).exists()


def puede_gestionar_usuarios(usuario):
    """Solo Superadmin y CEO pueden crear/gestionar usuarios"""
    return usuario.is_superuser or usuario.groups.filter(name__in=['Superadmin', 'CEO', 'Supervisora']).exists()


def health_check(request):
    """Endpoint para monitoreo de salud del sistema"""
    return JsonResponse({'status': 'ok', 'timestamp': timezone.now().isoformat()})


def scan_ticket(request, folio):
    """
    Página pública (sin login) para escanear el QR del ticket.
    Muestra al personal los detalles del pedido: prenda, foto, estado, saldo.
    """
    from .models import ConfiguracionTienda
    ticket = get_object_or_404(Ticket, folio=folio)
    config = ConfiguracionTienda.get_solo()
    snap = ticket.snapshot_json or {}

    # ── Foto(s) del producto ─────────────────────────────────────
    fotos = []
    try:
        if ticket.venta:
            for item in ticket.venta.items.select_related('producto').all():
                p = item.producto
                if p and p.foto:
                    fotos.append({'url': p.foto.url, 'descripcion': str(p)})
        elif ticket.apartado:
            for item in ticket.apartado.items.select_related('producto').all():
                p = item.producto
                if p and p.foto:
                    fotos.append({'url': p.foto.url, 'descripcion': str(p)})
        elif ticket.pedido:
            ped = ticket.pedido
            if ped.modelo and ped.modelo.foto_principal:
                fotos.append({'url': ped.modelo.foto_principal.url, 'descripcion': str(ped.modelo)})
    except Exception:
        pass

    # ── Estado y saldo en vivo ───────────────────────────────────
    estado_display = None
    estado_css = 'neutral'
    saldo = None
    fecha_entrega = None
    detalles_extra = {}

    try:
        if ticket.venta:
            v = ticket.venta
            estado_display = 'Entregado' if v.estado == 'ENTREGADO' else 'Completado'
            estado_css = 'ok'
            saldo = 0
        elif ticket.apartado:
            ap = ticket.apartado
            estado_display = ap.get_estado_display()
            saldo = float(ap.saldo)
            fecha_entrega = ap.fecha_vencimiento
            estado_css = 'warn' if saldo > 0 else 'ok'
            if ap.estado == 'CANCELADO':
                estado_css = 'cancel'
        elif ticket.pedido:
            ped = ticket.pedido
            estado_display = ped.get_estado_display()
            saldo = float(ped.saldo_pendiente)
            fecha_entrega = ped.fecha_entrega_estimada if hasattr(ped, 'fecha_entrega_estimada') else None
            estado_css = 'ok' if ped.estado in ('LISTO', 'ENTREGADO') else ('cancel' if ped.estado == 'CANCELADO' else 'progress')
            if saldo > 0 and ped.estado == 'LISTO':
                estado_css = 'warn'
            if ped.modelo:
                detalles_extra['Modelo'] = str(ped.modelo)
            if ped.color:
                detalles_extra['Color'] = str(ped.color)
            if ped.talla:
                detalles_extra['Talla'] = ped.talla
        elif ticket.servicio:
            srv = ticket.servicio
            estado_display = srv.get_estado_display()
            saldo = float(srv.costo - srv.anticipo)
            estado_css = 'ok' if srv.estado == 'ENTREGADO' else 'progress'
    except Exception:
        pass

    context = {
        'ticket': ticket,
        'config': config,
        'snap': snap,
        'fotos': fotos,
        'estado_display': estado_display,
        'estado_css': estado_css,
        'saldo': saldo,
        'fecha_entrega': fecha_entrega,
        'detalles_extra': detalles_extra,
        'items': snap.get('items', []),
        'cliente_nombre': ticket.cliente_nombre or snap.get('cliente', ''),
        'cliente_telefono': ticket.cliente_telefono or snap.get('cliente_telefono', ''),
    }
    return render(request, 'boutique/scan_ticket.html', context)


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

@profile_permission_required('Vendedor')
def pos_dashboard(request):
    """Interfaz principal de Punto de Venta"""
    corte = get_caja_activa()
    if not corte:
        return redirect('apertura_caja')

    from .models import RASGOS_ESTILO, RASGOS_CORTE, RASGOS_ESCOTE, RASGOS_TELA
    context = {
        'corte': corte,
        'telas': Tela.objects.filter(activa=True),
        'colores': Color.objects.filter(activo=True),
        'categorias': Categoria.objects.all(),
        'rasgos_estilo': RASGOS_ESTILO,
        'rasgos_corte': RASGOS_CORTE,
        'rasgos_escote': RASGOS_ESCOTE,
        'rasgos_tela': RASGOS_TELA,
    }
    return render(request, 'boutique/pos_dashboard.html', context)


@profile_permission_required(['Caja', 'Vendedor'])
def apertura_caja(request):
    """Vista para abrir la caja del día"""
    if CorteCaja.objects.filter(cerrado=False).exists():
        return redirect('pos_dashboard')

    if request.method == 'POST':
        monto = safe_decimal(request.POST.get('monto_apertura', 0))
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
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json' or 'X-CSRFToken' in request.headers:
            return JsonResponse({'status': 'ok', 'message': 'Caja abierta correctamente'})
        return redirect('pos_dashboard')
    return render(request, 'boutique/apertura_caja.html')


@profile_permission_required(['Caja', 'Vendedor'])
def cierre_caja(request):
    """Vista para cerrar la caja y confirmar montos"""
    corte = get_caja_activa()
    if not corte:
        return redirect('apertura_caja')

    if request.method == 'POST':
        efectivo_real = safe_decimal(request.POST.get('efectivo_real', 0))
        tarjeta_real = safe_decimal(request.POST.get('tarjeta_real', 0))
        transferencia_real = safe_decimal(request.POST.get('transferencia_real', 0))

        corte.efectivo_real = efectivo_real
        corte.tarjeta_real = tarjeta_real
        corte.transferencia_real = transferencia_real
        corte.fecha_cierre = timezone.now()
        corte.cerrado = True

        total_esperado = corte.efectivo_esperado + corte.tarjeta_esperada + corte.transferencia_esperada
        total_real = efectivo_real + tarjeta_real + transferencia_real

        corte.diferencia = total_real - total_esperado
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

    # Calcular esperados con una sola query de aggregate
    from django.db.models import Sum as _Sum, Q as _Q, Count as _Count
    movs = corte.movimientos.all()

    # Un aggregate en lugar de iterar 3–4 veces en Python
    totales = movs.aggregate(
        efectivo=_Sum('monto', filter=_Q(metodo_pago='EFECTIVO')),
        tarjeta=_Sum('monto', filter=_Q(metodo_pago='TARJETA')),
        transferencia=_Sum('monto', filter=_Q(metodo_pago='TRANSFERENCIA')),
        total_tickets=_Count('id', filter=_Q(ticket_folio__isnull=False)),
    )
    efectivo_movs = totales['efectivo'] or 0
    tarjeta_movs = totales['tarjeta'] or 0
    transf_movs = totales['transferencia'] or 0

    corte.efectivo_esperado = safe_decimal(corte.monto_apertura) + safe_decimal(efectivo_movs)
    corte.tarjeta_esperada = tarjeta_movs
    corte.transferencia_esperada = transf_movs
    corte.save()

    # Resumen por tipo: una pasada en Python sobre queryset ya evaluado
    resumen_tipos = {}
    for m in movs:
        resumen_tipos[m.tipo] = resumen_tipos.get(m.tipo, 0) + m.monto

    return render(request, 'boutique/cierre_caja.html', {
        'corte': corte,
        'efectivo_movs': efectivo_movs,
        'tarjeta_movs': tarjeta_movs,
        'transf_movs': transf_movs,
        'resumen_tipos': resumen_tipos,
        'total_tickets': totales['total_tickets'] or 0,
    })


# ============================================================
# API DE PRODUCTOS Y VENTAS
# ============================================================

@require_POST
@login_required
@profile_permission_required('Vendedor')
def api_sync(request):
    """Sincroniza operaciones offline (Ventas y Movimientos)"""
    try:
        data = json.loads(request.body)
        operaciones = data.get('operaciones', [])
        resultados = []

        for op in operaciones:
            tipo_op = op.get('tipo_op') # 'venta'
            payload = op.get('payload')
            offline_id = op.get('offline_id')

            try:
                with transaction.atomic():
                    if tipo_op == 'venta':
                        # Verificar si ya se procesó este offline_id (idempotencia)
                        if Venta.objects.filter(offline_id=offline_id).exists():
                            resultados.append({'offline_id': offline_id, 'status': 'already_synced'})
                            continue

                        items = payload.get('items', [])
                        total = payload.get('total', 0)
                        metodo = payload.get('metodo', 'EFECTIVO')
                        fecha_offline = payload.get('fecha')

                        venta = Venta.objects.create(
                            vendedor=request.active_profile,
                            total=total,
                            offline_id=offline_id
                        )
                        # Guardamos el offline_id en detalles para auditoría e idempotencia
                        registrar_auditoria(
                            usuario=request.active_profile,
                            accion='VENTA',
                            detalles=f'Sincronización Offline ID:{offline_id}',
                            entidad=venta,
                            request=request
                        )

                        for it in items:
                            prod = Producto.objects.get(id=it['id'])
                            ItemVenta.objects.create(
                                venta=venta,
                                producto=prod,
                                cantidad=it['cantidad'],
                                precio_unitario=prod.precio_venta
                            )
                            MovimientoInventario.objects.create(
                                producto=prod,
                                tipo='VENTA',
                                cantidad=-it['cantidad'],
                                motivo='VENTA',
                                perfil_activo=request.active_profile,
                                venta=venta,
                                stock_resultante=prod.stock_teorico - it['cantidad']
                            )

                        Pago.objects.create(
                            venta=venta,
                            monto=total,
                            metodo=metodo,
                            registrado_por=request.active_profile
                        )
                        resultados.append({'offline_id': offline_id, 'status': 'ok', 'id': venta.id})
            except Exception as e:
                resultados.append({'offline_id': offline_id, 'status': 'error', 'message': str(e)})

        return JsonResponse({'status': 'ok', 'resultados': resultados})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@require_POST
@login_required
@profile_permission_required('Vendedor')
def api_liquidar_pedido(request, pk):
    """Convierte un pedido en venta al ser liquidado"""
    from .models import PagoPedido
    from .services.cash_service import registrar_cobro
    pedido = get_object_or_404(Pedido, pk=pk)
    try:
        data = json.loads(request.body)
        metodo = data.get('metodo', 'EFECTIVO')
        monto = safe_decimal(data.get('monto', pedido.saldo_pendiente))

        with transaction.atomic():
            # Registrar el cobro en caja
            ticket = registrar_cobro(
                origen_tipo='pedido',
                origen_obj=pedido,
                monto=monto,
                metodo=metodo,
                usuario=request.active_profile,
                notas='Liquidación de pedido'
            )

            # Recargar pedido para ver saldo actualizado
            pedido.refresh_from_db()

            if pedido.esta_pagado:
                # Crear la Venta oficial para que cuente en estadísticas de productos
                venta = Venta.objects.create(
                    vendedor=request.active_profile,
                    total=pedido.precio,
                    ticket=ticket, # Usamos el ticket generado
                    pedido=pedido,
                    notas=f"Liquidación de Ticket {pedido.numero_ticket}"
                )

                if pedido.producto:
                    ItemVenta.objects.create(
                        venta=venta,
                        producto=pedido.producto,
                        cantidad=1,
                        precio_unitario=pedido.precio
                    )

                registrar_auditoria(
                    usuario=request.active_profile,
                    accion='VENTA',
                    detalles=f'Pedido {pedido.id} liquidado y convertido a Venta #{venta.id}',
                    entidad=venta,
                    request=request
                )

                return JsonResponse({
                    'status': 'ok',
                    'venta_id': venta.id,
                    'liquidado': True,
                    'ticket_folio': ticket.folio
                })

            return JsonResponse({'status': 'ok', 'pedido_id': pedido.id, 'liquidado': False, 'saldo': float(pedido.saldo_pendiente)})
    except ValueError as ve:
        return JsonResponse({'status': 'caja_cerrada', 'message': str(ve)}, status=400)
    except Exception as e:
        logger.exception("Error en api_liquidar_pedido")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


def _parse_servicios_bundled(servicios_json_str, cliente_obj, perfil, venta, ticket, adjust_total=True):
    """Crea servicios adicionales vinculados a una venta y los añade al snapshot del ticket."""
    from .models import Servicio
    try:
        servicios_data = json.loads(servicios_json_str or '[]')
    except Exception:
        return []
    creados = []
    meta_map = {}
    for srv_data in servicios_data:
        precio_unit = safe_decimal(srv_data.get('precio_unitario', 0) or 0)
        cantidad = int(srv_data.get('cantidad', 1) or 1)
        costo = safe_decimal(srv_data.get('costo', 0) or 0)
        if costo <= 0:
            costo = precio_unit * cantidad
        if costo <= 0:
            continue
        if precio_unit <= 0:
            precio_unit = costo / cantidad if cantidad else costo
        nota = srv_data.get('nota', '').strip()
        prenda = srv_data.get('prenda', '').strip()
        tipo_raw = srv_data.get('tipo', 'AJUSTE')
        _LINEA_TO_SRV = {
            'BASTILLA': 'BASTILLA', 'TIRANTE': 'TIRANTE', 'MANGA': 'MANGA',
            'CINTURA': 'TALLE', 'BUSTO': 'PECHO', 'CIERRE': 'CREMALLERA',
            'HOMBRO': 'AJUSTE', 'COSTADO': 'AJUSTE', 'PIERNA': 'BASTILLA',
        }
        tipo_srv = _LINEA_TO_SRV.get(tipo_raw, tipo_raw if tipo_raw in [
            'BASTILLA','TALLE','TIRANTE','CREMALLERA','PECHO','CADERA',
            'MANGA','APLIQUE','BORDADO','AJUSTE','OTRO'] else 'AJUSTE')
        s = Servicio.objects.create(
            tipo=tipo_srv,
            descripcion=nota or prenda or tipo_raw,
            cliente=cliente_obj,
            costo=costo,
            anticipo=costo,
            estado='RECIBIDO',
            creado_por=perfil,
            venta=venta,
        )
        creados.append(s)
        meta_map[s.pk] = {
            'cantidad': cantidad,
            'precio_unitario': float(precio_unit),
            'nota': nota,
            'prenda': prenda,
            'tipo_raw': tipo_raw,
        }
    if creados and ticket:
        snapshot = ticket.snapshot_json or {}
        items = snapshot.get('items', [])
        for s in creados:
            meta = meta_map[s.pk]
            label = s.get_tipo_display()
            if meta['prenda']:
                label = f"{label} — {meta['prenda']}"
            if meta['nota']:
                label = f"{label} ({meta['nota'][:30]})"
            items.append({
                'descripcion': label,
                'cantidad': meta['cantidad'],
                'precio_unitario': meta['precio_unitario'],
                'subtotal': float(s.costo),
                'es_servicio': True,
            })
        snapshot['items'] = items
        if adjust_total:
            snapshot['total'] = float(ticket.total) + sum(float(s.costo) for s in creados)
        ticket.snapshot_json = snapshot
        ticket.save(update_fields=['snapshot_json'])
    return creados


@require_POST
@login_required
@profile_permission_required('Vendedor')
def api_venta_rapida(request):
    """Crea producto al vuelo + registra venta/apartado/pedido + movimiento en una sola transacción"""
    from .models import Novia, Dama, PagoPedido, Apartado, ApartadoItem, Medidas, Pedido
    from .services.cash_service import registrar_cobro
    from .services.agenda_service import sync_delivery_with_agenda
    try:
        # 1. Parámetros básicos
        tipo_op = request.POST.get('tipo_operacion', 'VENTA_NORMAL')
        cat_nombre = request.POST.get('categoria', 'General')
        color_nombre = request.POST.get('color', 'N/A')
        talla = request.POST.get('talla', 'U')
        precio = safe_decimal(request.POST.get('precio', 0))
        _anticipo_raw = request.POST.get('anticipo', '').strip()
        anticipo = safe_decimal(_anticipo_raw, precio)  # si vacío → cobro total
        metodo = request.POST.get('metodo', 'EFECTIVO')
        rasgo1 = request.POST.get('rasgo1', '')
        rasgo2 = request.POST.get('rasgo2', '')
        es_apartado = request.POST.get('es_apartado') == 'true'
        foto = request.FILES.get('foto')

        # Idempotencia
        idem_key = request.POST.get('idempotency_key')
        if idem_key:
            from .models import IdempotencyLog
            log, created = IdempotencyLog.objects.get_or_create(key=idem_key, defaults={'status': 'PROCESSING'})
            if not created and log.status == 'DONE':
                return JsonResponse(log.response_json)

        # Datos del cliente
        cliente_telefono = request.POST.get('cliente_telefono', '').strip()
        cliente_nombre = (request.POST.get('cliente_nombre') or '').strip()
        cliente_notas = request.POST.get('cliente_notas')
        evento = request.POST.get('evento', '')
        fecha_entrega_est = request.POST.get('fecha_entrega_estimada')
        fecha_evento = request.POST.get('fecha_evento')
        sin_registro = request.POST.get('sin_registro') == 'true'

        # 1.5 Validaciones de identidad de cliente
        if tipo_op == 'VENTA_NORMAL' and not es_apartado:
            # Venta inmediata: nombre obligatorio O sin_registro explícito
            if not sin_registro and not cliente_nombre:
                return JsonResponse({'status': 'error', 'message': 'Ingresa el nombre del cliente o selecciona "Sin registro".'}, status=400)
        elif tipo_op == 'VENTA_NORMAL' and es_apartado:
            if not cliente_nombre:
                return JsonResponse({'status': 'error', 'message': 'El nombre del cliente es obligatorio para apartados.'}, status=400)
            if cliente_nombre.lower() == 'sin registro':
                return JsonResponse({'status': 'error', 'message': 'Un apartado con saldo pendiente no puede quedar sin registro de cliente.'}, status=400)
        elif tipo_op in ['HECHURA', 'PEDIDO_EXTERNO', 'DAMA_HONOR']:
            if not cliente_nombre:
                return JsonResponse({'status': 'error', 'message': 'El nombre del cliente es obligatorio para este tipo de operación.'}, status=400)

        if tipo_op in ['HECHURA', 'PEDIDO_EXTERNO']:
            if not cliente_telefono:
                return JsonResponse({'status': 'error', 'message': 'El teléfono del cliente es obligatorio para este tipo de pedido.'}, status=400)
            if not fecha_entrega_est:
                return JsonResponse({'status': 'error', 'message': 'La fecha de entrega estimada es obligatoria.'}, status=400)

        with transaction.atomic():
            # 2. Gestionar cliente
            cliente_obj = None
            if cliente_telefono:
                cliente_obj, created = Cliente.objects.get_or_create(
                    telefono=cliente_telefono,
                    defaults={'nombre': cliente_nombre or 'Sin nombre', 'notas': cliente_notas or ''}
                )
                if not created and cliente_nombre:
                    cliente_obj.nombre = cliente_nombre
                    if cliente_notas:
                        cliente_obj.notas = cliente_notas
                    cliente_obj.save()

            # 3. Gestionar Catálogos
            categoria = Categoria.objects.filter(nombre=cat_nombre).first()
            if not categoria:
                categoria, _ = Categoria.objects.get_or_create(nombre="Sin definir")

            color = Color.objects.filter(nombre=color_nombre).first()
            if not color:
                color, _ = Color.objects.get_or_create(nombre="Sin definir")

            # Intentar asociar Tela desde rasgo2 o tela_id
            tela_id = request.POST.get('tela_id')
            tela_obj = None
            if tela_id:
                tela_obj = Tela.objects.filter(id=tela_id).first()
            if not tela_obj:
                tela_obj = Tela.objects.filter(nombre__iexact=rasgo2).first()

            # 4. Crear producto físico (si aplica)
            # Reutilizar si ya existe (prevención de duplicados)
            producto, _ = Producto.objects.get_or_create(
                categoria=categoria,
                color=color,
                tela=tela_obj,
                rasgo1=rasgo1,
                rasgo2=rasgo2,
                talla=talla,
                defaults={
                    'precio_venta': precio,
                    'estado': 'TIENDA' if not es_apartado and tipo_op == 'VENTA_NORMAL' else 'APARTADO',
                    'cantidad_actual': 0,
                    'stock_teorico': 0,
                    'foto': foto
                }
            )

            # 5. Lógica según Tipo de Operación
            if tipo_op == 'VENTA_NORMAL':
                if es_apartado:
                    # FLUJO APARTADO
                    apartado = Apartado.objects.create(
                        cliente=cliente_obj,
                        cliente_nombre=cliente_nombre,
                        cliente_telefono=cliente_telefono or '',
                        total=precio,
                        anticipo=0,
                        evento=evento,
                        categoria_cache=cat_nombre,
                        color_cache=color_nombre,
                        talla_cache=talla,
                        notas=f"Apartado Rápido SKU {producto.sku}",
                        fecha_entrega_estimada=fecha_entrega_est or None
                    )
                    ApartadoItem.objects.create(
                        apartado=apartado,
                        producto=producto,
                        descripcion=str(producto),
                        cantidad=1,
                        precio_unitario=precio,
                        subtotal=precio
                    )
                    ticket = registrar_cobro(
                        origen_tipo='apartado', origen_obj=apartado,
                        monto=anticipo, metodo=metodo, usuario=request.active_profile,
                        notas='Anticipo Venta Rápida'
                    )

                    if apartado.fecha_entrega_estimada:
                        sync_delivery_with_agenda(apartado)

                    res = {'status': 'ok', 'tipo': 'apartado', 'ticket': ticket.folio, 'producto': {'id': producto.id, 'sku': producto.sku}}
                else:
                    # FLUJO VENTA COMPLETA
                    venta = Venta.objects.create(
                        vendedor=request.active_profile, cliente=cliente_obj,
                        total=precio, evento=evento, categoria_cache=cat_nombre,
                        color_cache=color_nombre, talla_cache=talla, tipo_operacion=tipo_op
                    )
                    ItemVenta.objects.create(venta=venta, producto=producto, cantidad=1, precio_unitario=precio)
                    MovimientoInventario.objects.create(
                        producto=producto, tipo='VENTA', cantidad=-1, motivo='VENTA',
                        perfil_activo=request.active_profile, venta=venta,
                        stock_resultante=producto.stock_teorico - 1
                    )
                    ticket = registrar_cobro(
                        origen_tipo='venta', origen_obj=venta,
                        monto=anticipo, metodo=metodo, usuario=request.active_profile
                    )
                    # Venta.cliente_nombre no existe como campo; parchamos el ticket
                    if not ticket.cliente_nombre:
                        ticket.cliente_nombre = 'Sin registro' if sin_registro else (cliente_nombre or '')
                        ticket.cliente_telefono = '' if sin_registro else cliente_telefono
                        _snap = ticket.snapshot_json or {}
                        _snap['cliente'] = ticket.cliente_nombre
                        _snap['cliente_telefono'] = ticket.cliente_telefono
                        ticket.snapshot_json = _snap
                        ticket.save(update_fields=['cliente_nombre', 'cliente_telefono', 'snapshot_json'])
                    # Guardar largo_aprox en snapshot si se proporcionó en el formulario
                    _m_largo = request.POST.get('m_largo', '').strip()
                    if _m_largo:
                        _snap = ticket.snapshot_json or {}
                        _snap['largo_aprox'] = _m_largo
                        ticket.snapshot_json = _snap
                        ticket.save(update_fields=['snapshot_json'])
                    # Servicios adicionales bundled (bastillas, ajustes, etc.)
                    _servicios_extra = _parse_servicios_bundled(
                        request.POST.get('servicios_json', '[]'),
                        cliente_obj, request.active_profile, venta, ticket
                    )
                    if _servicios_extra:
                        venta.total += sum(s.costo for s in _servicios_extra)
                        venta.save(update_fields=['total'])
                    res = {'status': 'ok', 'tipo': 'venta', 'id': venta.id, 'sku': producto.sku, 'folio': ticket.folio}

            elif tipo_op in ['DAMA_HONOR', 'HECHURA', 'PEDIDO_EXTERNO']:
                # FLUJO PEDIDO (Dama, Hechura o Pedido Externo)
                novia_id = request.POST.get('novia_id')
                dama_id = request.POST.get('dama_id')
                nueva_dama_nombre = request.POST.get('nueva_dama_nombre')
                novia_obj = None
                dama_obj = None

                if novia_id:
                    novia_obj = Novia.objects.filter(id=novia_id).first()

                if dama_id:
                    dama_obj = Dama.objects.filter(id=dama_id).first()
                elif nueva_dama_nombre and novia_obj:
                    # Crear nueva dama si se proporcionó nombre
                    dama_obj = Dama.objects.create(
                        novia=novia_obj,
                        cliente=cliente_obj,
                        nombre=nueva_dama_nombre,
                        telefono=cliente_telefono or '',
                        talla=talla
                    )
                    # Actualizar contador
                    novia_obj.cantidad_damas = novia_obj.damas.count()
                    novia_obj.save(update_fields=['cantidad_damas'])

                # Determinar tipo de pedido y estado inicial
                tp = 'ESTANDAR_GRUPO'
                est = 'NUEVO'

                if tipo_op == 'HECHURA':
                    tp = 'HECHURA'
                    est = 'NUEVO'
                elif tipo_op == 'PEDIDO_EXTERNO':
                    tp = 'PEDIDO_EXTERNO'
                    est = 'SOLICITADO'

                pedido = Pedido.objects.create(
                    cliente=cliente_obj,
                    novia=novia_obj or (dama_obj.novia if dama_obj else None),
                    dama=dama_obj,
                    producto=producto,
                    color=color,
                    tela=tela_obj,
                    talla=talla,
                    precio=precio,
                    evento=evento,
                    tipo_operacion=tipo_op,
                    tipo_pedido=tp,
                    estado=est,
                    fecha_entrega_estimada=fecha_entrega_est or None,
                    fecha_evento=fecha_evento or None,
                    creado_por=request.active_profile
                )

                # Guardar medidas si vienen en el POST
                if any([request.POST.get('m_busto'), request.POST.get('medidas_busto'), request.POST.get('m_cintura'), request.POST.get('m_notas')]):
                    def get_d(key1, key2):
                        val = request.POST.get(key1) or request.POST.get(key2)
                        return safe_decimal(val, None)

                    Medidas.objects.create(
                        pedido=pedido,
                        cliente=cliente_obj,
                        cliente_nombre=cliente_nombre or (dama_obj.nombre if dama_obj else 'Sin nombre'),
                        busto=get_d('m_busto', 'medidas_busto'),
                        cintura=get_d('m_cintura', 'medidas_cintura'),
                        cadera=get_d('m_cadera', 'medidas_cadera'),
                        hombro=get_d('m_hombro', 'medidas_hombro'),
                        largo_aproximado=get_d('m_largo', 'medidas_largo'),
                        brazo=get_d('m_brazo', 'medidas_brazo'),
                        espalda=get_d('m_espalda', 'medidas_espalda'),
                        bajo_busto=get_d('m_bajo_busto', 'bajo_busto'),
                        largo_talle=get_d('m_largo_talle', 'largo_talle'),
                        hombro_pezon=get_d('m_hombro_pezon', 'hombro_pezon'),
                        hombro_bajo_busto=get_d('m_hombro_bajo_busto', 'hombro_bajo_busto'),
                        talle_delantero=get_d('m_talle_frente', 'medidas_talle_frente'),
                        talle_trasero=get_d('m_talle_espalda', 'medidas_talle_espalda'),
                        observaciones=request.POST.get('m_notas') or request.POST.get('medidas_notas', '')
                    )

                # Auto-crear VestidoDama si hay una dama asignada
                if dama_obj:
                    from .models import VestidoDama as VD
                    tipo_vd_map = {'HECHURA': 'HECHURA', 'PEDIDO_EXTERNO': 'ESPECIAL', 'DAMA_HONOR': 'CATALOGO'}
                    VD.objects.create(
                        dama=dama_obj,
                        pedido=pedido,
                        tipo=tipo_vd_map.get(tipo_op, 'ESPECIAL'),
                        modelo=pedido.modelo,
                        talla=talla or dama_obj.talla or '',
                        color=color,
                        tela=tela_obj,
                        precio=precio,
                        estado='PEDIDO',
                        creado_por=request.active_profile,
                    )

                ticket = registrar_cobro(
                    origen_tipo='pedido', origen_obj=pedido,
                    monto=anticipo, metodo=metodo, usuario=request.active_profile,
                    notas=f'Anticipo {tipo_op}'
                )

                if pedido.fecha_entrega_estimada:
                    sync_delivery_with_agenda(pedido)

                res = {'status': 'ok', 'tipo': 'pedido', 'id': pedido.id, 'folio': ticket.folio}

            registrar_auditoria(
                usuario=request.active_profile,
                accion='VENTA',
                detalles=f'Venta Rápida ({tipo_op}) Ticket {ticket.folio}',
                entidad=producto,
                request=request
            )

            if idem_key:
                log.response_json = res
                log.status = 'DONE'
                log.save()
            return JsonResponse(res)

    except ValueError as ve:
        return JsonResponse({'status': 'caja_cerrada', 'message': str(ve)}, status=400)
    except Exception as e:
        logger.exception("Error en api_venta_rapida")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@require_POST
@login_required
@profile_permission_required('Vendedor')
def api_crear_producto_rapido(request):
    """Crea un producto de forma rápida desde la caja"""
    try:
        data = json.loads(request.body)
        cat_nombre = data.get('categoria', 'Sin definir')
        color_nombre = data.get('color', 'Sin definir')

        categoria = Categoria.objects.filter(nombre=cat_nombre).first()
        if not categoria:
            categoria, _ = Categoria.objects.get_or_create(nombre="Sin definir")

        color = Color.objects.filter(nombre=color_nombre).first()
        if not color:
            color, _ = Color.objects.get_or_create(nombre="Sin definir")

        rasgo2 = data.get('rasgo2', '')
        tela_obj = Tela.objects.filter(nombre__iexact=rasgo2).first()

        producto = Producto.objects.create(
            categoria=categoria,
            color=color,
            tela=tela_obj,
            rasgo1=data.get('rasgo1', ''),
            rasgo2=rasgo2,
            talla=data.get('talla', 'U'),
            talla_especial=data.get('talla_especial', ''),
            precio_venta=data.get('precio', 0),
            estado=data.get('estado', 'TIENDA'),
            cantidad_actual=int(data.get('stock', 1))
        )
        return JsonResponse({'status': 'ok', 'sku': producto.sku, 'id': producto.id, 'text': str(producto)})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@login_required
@profile_permission_required('Vendedor')
def api_search_productos(request):
    """Buscador de productos para el POS"""
    q = request.GET.get('q', '')
    productos = Producto.objects.filter(
        Q(sku__icontains=q) |
        Q(rasgo1__icontains=q) |
        Q(rasgo2__icontains=q) |
        Q(categoria__nombre__icontains=q)
    ).select_related('categoria', 'color', 'modelo', 'tela')[:15]
    results = [{'id': p.id, 'sku': p.sku, 'text': str(p), 'precio': float(p.precio_venta), 'stock': p.cantidad_actual, 'foto_url': p.foto.url if p.foto else None} for p in productos]
    return JsonResponse({'results': results})


@login_required
def cliente_detalle(request, pk):
    """Ficha del cliente con historial unificado completo"""
    from .models import Servicio
    cliente = get_object_or_404(Cliente, pk=pk)

    ventas    = Venta.objects.filter(cliente=cliente).prefetch_related('items', 'pagos').order_by('-fecha')
    apartados = Apartado.objects.filter(cliente=cliente).prefetch_related('items', 'pagos_apartado', 'tickets_asociados').order_by('-fecha_creacion')
    pedidos   = Pedido.objects.filter(cliente=cliente).prefetch_related('pagos_pedido', 'tickets_relacionados', 'notas_seguimiento').select_related('novia', 'dama', 'modelo', 'color').order_by('-fecha_creacion')
    servicios = Servicio.objects.filter(cliente=cliente).prefetch_related('pagos_servicio').order_by('-fecha_creacion')
    medidas   = cliente.medidas_historicas.order_by('-fecha_actualizacion')
    tickets   = Ticket.objects.filter(cliente_nombre=cliente.nombre).order_by('-fecha_hora')

    # Saldos pendientes
    saldo_apartados = sum(a.saldo for a in apartados if a.estado not in ['CANCELADO', 'ENTREGADO'])
    saldo_pedidos   = sum(p.saldo_pendiente for p in pedidos if p.estado not in ['CANCELADO', 'ENTREGADO'])
    saldo_servicios = sum(s.saldo_pendiente for s in servicios if s.estado not in ['CANCELADO', 'ENTREGADO'])
    saldo_total     = saldo_apartados + saldo_pedidos + saldo_servicios

    # Historial cronológico unificado
    historial = []
    for v in ventas:
        historial.append({'tipo': 'VENTA', 'obj': v, 'fecha': v.fecha,
                          'total': v.total, 'folio': f'V-{v.id}', 'estado': 'Completada',
                          'saldo': 0, 'detalle': f"{v.categoria_cache} {v.color_cache}".strip() or 'Venta directa'})
    for a in apartados:
        historial.append({'tipo': 'APARTADO', 'obj': a, 'fecha': a.fecha_creacion,
                          'total': a.total, 'folio': a.folio, 'estado': a.get_estado_display(),
                          'saldo': a.saldo, 'detalle': f"{a.categoria_cache} {a.color_cache}".strip() or a.notas[:50]})
    for p in pedidos:
        desc = ''
        if p.modelo: desc += p.modelo.nombre
        if p.color: desc += f' {p.color.nombre}'
        if p.talla: desc += f' T:{p.talla}'
        historial.append({'tipo': 'PEDIDO', 'obj': p, 'fecha': p.fecha_creacion,
                          'total': p.precio, 'folio': p.numero_ticket, 'estado': p.get_estado_display(),
                          'saldo': p.saldo_pendiente, 'detalle': desc.strip() or p.notas[:50]})
    for s in servicios:
        historial.append({'tipo': 'SERVICIO', 'obj': s, 'fecha': s.fecha_creacion,
                          'total': s.costo, 'folio': f'SRV-{s.id}', 'estado': s.get_estado_display(),
                          'saldo': s.saldo_pendiente, 'detalle': s.descripcion[:60]})

    historial.sort(key=lambda x: x['fecha'], reverse=True)

    return render(request, 'boutique/cliente_detalle.html', {
        'cliente': cliente,
        'historial': historial,
        'apartados_activos': apartados.exclude(estado__in=['CANCELADO', 'ENTREGADO']),
        'pedidos': pedidos,
        'servicios': servicios,
        'medidas': medidas,
        'tickets': tickets[:20],
        'saldo_total': saldo_total,
        'saldo_apartados': saldo_apartados,
        'saldo_pedidos': saldo_pedidos,
        'saldo_servicios': saldo_servicios,
    })


@login_required
def api_search_clientes(request):
    """Buscador de clientes por teléfono o nombre"""
    q = request.GET.get('q', '')
    if not q:
        return JsonResponse({'results': []})

    clientes = Cliente.objects.filter(
        Q(telefono__icontains=q) |
        Q(nombre__icontains=q)
    )[:10]

    results = [{
        'id': c.id,
        'nombre': c.nombre,
        'telefono': c.telefono,
        'email': c.email,
        'notas': c.notas
    } for c in clientes]
    return JsonResponse({'results': results})


@require_POST
@login_required
@profile_permission_required('Vendedor')
def api_registrar_venta(request):
    """Registra una venta o un apartado"""
    from .models import Novia, PagoPedido, Apartado, ApartadoItem
    from .services.cash_service import registrar_cobro
    try:
        data = json.loads(request.body)
        items = data.get('items', [])
        total = safe_decimal(data.get('total', 0))
        pago_inicial = safe_decimal(data.get('pago_inicial', total))
        metodo = data.get('metodo', 'EFECTIVO')
        es_apartado = data.get('es_apartado', False)
        cliente_nombre = (data.get('cliente_nombre') or '').strip()
        cliente_telefono = (data.get('cliente_telefono') or '').strip()
        sin_registro = bool(data.get('sin_registro', False))
        notas_operacion = (data.get('notas_operacion') or '').strip()
        cliente_id_hint = data.get('cliente_id')
        tiene_saldo = pago_inicial < total

        # Identidad mínima obligatoria
        if es_apartado or tiene_saldo:
            if not cliente_nombre:
                return JsonResponse({
                    'status': 'error', 'field': 'cliente_nombre',
                    'message': 'Agrega el nombre del cliente para continuar con el apartado.'
                }, status=400)
            if cliente_nombre.lower() == 'sin registro':
                return JsonResponse({
                    'status': 'error', 'field': 'cliente_nombre',
                    'message': 'Un apartado con saldo pendiente no puede quedar sin registro de cliente.'
                }, status=400)
        else:
            if not sin_registro and not cliente_nombre:
                return JsonResponse({
                    'status': 'error', 'field': 'cliente_nombre',
                    'message': 'Agrega el nombre del cliente, o selecciona "Continuar sin registro" para ventas anónimas.'
                }, status=400)

        with transaction.atomic():
            if es_apartado:
                # Nuevo flujo de Apartado Independiente
                apartado = Apartado.objects.create(
                    cliente_nombre=cliente_nombre,
                    cliente_telefono=cliente_telefono,
                    total=total,
                    anticipo=0,
                    notas_entrega=notas_operacion,
                )

                for it in items:
                    prod = Producto.objects.get(id=it['id'])
                    ApartadoItem.objects.create(
                        apartado=apartado,
                        producto=prod,
                        descripcion=str(prod),
                        cantidad=it['cantidad'],
                        precio_unitario=prod.precio_venta,
                        subtotal=it['cantidad'] * prod.precio_venta
                    )
                    # Apartar stock
                    prod.estado = 'APARTADO'
                    prod.save()

                    MovimientoInventario.objects.create(
                        producto=prod,
                        tipo='SALIDA',
                        cantidad=-it['cantidad'],
                        motivo='VENTA',
                        perfil_activo=request.active_profile,
                        stock_resultante=prod.stock_teorico - it['cantidad']
                    )

                # Registrar cobro inicial
                ticket = registrar_cobro(
                    origen_tipo='apartado',
                    origen_obj=apartado,
                    monto=pago_inicial,
                    metodo=metodo,
                    usuario=request.active_profile,
                    notas=notas_operacion or 'Anticipo POS',
                )
                if notas_operacion:
                    snap = ticket.snapshot_json or {}
                    snap['notas_operacion'] = notas_operacion
                    ticket.snapshot_json = snap
                    ticket.save(update_fields=['snapshot_json'])

                registrar_auditoria(
                    usuario=request.active_profile,
                    accion='VENTA',
                    detalles=f'Apartado POS Ticket {ticket.folio}',
                    entidad=apartado,
                    request=request
                )

                return JsonResponse({'status': 'ok', 'tipo': 'apartado', 'ticket': ticket.folio})

            else:
                # Flujo de Venta normal
                # Vincular cliente: primero por ID explícito, luego por teléfono
                cliente_obj = None
                if cliente_id_hint:
                    try:
                        cliente_obj = Cliente.objects.get(pk=int(cliente_id_hint))
                        if cliente_nombre and cliente_obj.nombre != cliente_nombre:
                            cliente_obj.nombre = cliente_nombre
                            cliente_obj.save(update_fields=['nombre'])
                    except (Cliente.DoesNotExist, ValueError):
                        pass
                if not cliente_obj and cliente_telefono:
                    cliente_obj, created = Cliente.objects.get_or_create(
                        telefono=cliente_telefono,
                        defaults={'nombre': cliente_nombre or 'Sin nombre'}
                    )
                    if not created and cliente_nombre:
                        cliente_obj.nombre = cliente_nombre
                        cliente_obj.save(update_fields=['nombre'])

                venta = Venta.objects.create(
                    vendedor=request.active_profile,
                    cliente=cliente_obj,
                    total=total,
                    notas=notas_operacion,
                )

                for it in items:
                    prod = Producto.objects.get(id=it['id'])
                    ItemVenta.objects.create(
                        venta=venta,
                        producto=prod,
                        cantidad=it['cantidad'],
                        precio_unitario=prod.precio_venta
                    )

                    MovimientoInventario.objects.create(
                        producto=prod,
                        tipo='VENTA',
                        cantidad=-it['cantidad'],
                        motivo='VENTA',
                        perfil_activo=request.active_profile,
                        venta=venta,
                        stock_resultante=prod.stock_teorico - it['cantidad']
                    )

                # Registrar cobro en caja
                ticket = registrar_cobro(
                    origen_tipo='venta',
                    origen_obj=venta,
                    monto=pago_inicial,
                    metodo=metodo,
                    usuario=request.active_profile
                )

                # Parchamos ticket con nombre, teléfono y notas de operación
                snap = ticket.snapshot_json or {}
                update_fields = []
                if not ticket.cliente_nombre:
                    ticket.cliente_nombre = 'Sin registro' if sin_registro else (cliente_nombre or '')
                    ticket.cliente_telefono = '' if sin_registro else cliente_telefono
                    snap['cliente'] = ticket.cliente_nombre
                    snap['cliente_telefono'] = ticket.cliente_telefono
                    update_fields += ['cliente_nombre', 'cliente_telefono']
                if notas_operacion:
                    snap['notas_operacion'] = notas_operacion
                if update_fields or notas_operacion:
                    ticket.snapshot_json = snap
                    ticket.save(update_fields=update_fields + ['snapshot_json'])

                # Servicios extra bundled en la misma venta (ya incluidos en total del frontend)
                servicios_extra = data.get('servicios_extra') or []
                if servicios_extra:
                    import json as _json
                    _parse_servicios_bundled(
                        _json.dumps(servicios_extra),
                        cliente_obj,
                        request.active_profile,
                        venta,
                        ticket,
                        adjust_total=False,
                    )

                registrar_auditoria(
                    usuario=request.active_profile,
                    accion='VENTA',
                    detalles=f'Venta #{venta.id} por ${total} (Ticket {ticket.folio})',
                    entidad=venta,
                    request=request
                )

                return JsonResponse({'status': 'ok', 'tipo': 'venta', 'venta_id': venta.id, 'folio': ticket.folio})
    except ValueError as ve:
        return JsonResponse({'status': 'caja_cerrada', 'message': str(ve)}, status=400)
    except Exception as e:
        logger.exception("Error en api_registrar_venta")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


def fuzzy_match(s1, s2):
    if not s1 or not s2:
        return 0
    return SequenceMatcher(None, s1.lower(), s2.lower()).ratio()


@require_POST
@login_required
def api_check_duplicados(request):
    """Verifica posibles duplicados con IA antes de crear un producto"""
    from .ai_utils import analyze_duplicate_ai
    
    data = json.loads(request.body)
    cat = data.get('categoria', '')
    r1 = data.get('rasgo1', '')
    r2 = data.get('rasgo2', '')
    color = data.get('color', '')
    talla = data.get('talla', '')

    # Buscar productos similares en la misma categoría
    posibles = Producto.objects.filter(
        Q(categoria__nombre__icontains=cat) | 
        Q(rasgo1__icontains=r1) |
        Q(rasgo2__icontains=r2)
    ).select_related('categoria', 'color')[:20]

    coincidencias = []
    productos_texto = []
    
    for p in posibles:
        score = 0
        # Misma categoría = alto score
        if p.categoria.nombre.lower() == cat.lower():
            score += 0.35
        
        # Similitud en rasgos
        s1 = fuzzy_match(p.rasgo1, r1)
        s2 = fuzzy_match(p.rasgo2, r2)
        score += (s1 * 0.25) + (s2 * 0.25)
        
        # Color similar (considerar variantes como rosa palo, rosa mauve)
        color_score = fuzzy_match(p.color.nombre, color)
        if 'rosa' in p.color.nombre.lower() and 'rosa' in color.lower():
            color_score = max(color_score, 0.7)  # Boost para variantes de rosa
        score += color_score * 0.15

        if score > 0.5:
            coincidencias.append({
                'id': p.id,
                'text': str(p),
                'sku': p.sku,
                'categoria': p.categoria.nombre,
                'rasgo1': p.rasgo1,
                'rasgo2': p.rasgo2,
                'color': p.color.nombre,
                'talla': p.talla,
                'score': round(score * 100, 1)
            })
            productos_texto.append(f"- {p.categoria.nombre} {p.rasgo1} {p.rasgo2} ({p.color.nombre}, talla {p.talla}) [SKU: {p.sku}]")

    coincidencias.sort(key=lambda x: x['score'], reverse=True)
    top_coincidencias = coincidencias[:5]
    
    # Si hay coincidencias altas, usar IA para analizar si es duplicado
    ai_analysis = None
    if top_coincidencias and top_coincidencias[0]['score'] > 60:
        try:
            nuevo_prod = {
                'categoria': cat,
                'rasgo1': r1,
                'rasgo2': r2,
                'color': color,
                'talla': talla
            }
            ai_analysis = analyze_duplicate_ai(nuevo_prod, "\n".join(productos_texto[:5]))
        except Exception as e:
            logger.error(f"Error en análisis IA de duplicados: {e}")
            ai_analysis = None
    
    # Construir respuesta con guía
    response_data = {
        'duplicados': top_coincidencias,
        'ai_analysis': ai_analysis,
        'hay_alerta': len(top_coincidencias) > 0 and top_coincidencias[0]['score'] > 70,
        'mensaje_guia': None
    }
    
    if top_coincidencias:
        if top_coincidencias[0]['score'] > 80:
            response_data['mensaje_guia'] = f"⚠️ ALTO: Este producto parece muy similar a '{top_coincidencias[0]['text']}'. Verifica antes de crear."
        elif top_coincidencias[0]['score'] > 60:
            response_data['mensaje_guia'] = f"⚡ Revisa: Encontramos productos parecidos. ¿Es una variante de color/tela diferente?"
    
    return JsonResponse(response_data)


@require_POST
@profile_permission_required('Inventario')
def api_validar_crear_producto(request):
    """Valida y crea producto solo si no hay duplicados confirmados"""
    if request.content_type == 'application/json':
        data = json.loads(request.body)
        foto = None
    else:
        data = request.POST
        foto = request.FILES.get('foto')

    # Idempotencia
    idem_key = data.get('idempotency_key')
    if idem_key:
        from .models import IdempotencyLog
        log, created = IdempotencyLog.objects.get_or_create(key=idem_key, defaults={'status': 'PROCESSING'})
        if not created and log.status == 'DONE':
            return JsonResponse(log.response_json)

    forzar_crear = data.get('forzar_crear') == True or data.get('forzar_crear') == 'true'
    
    # Si no se fuerza, verificar duplicados primero
    if not forzar_crear:
        cat = data.get('categoria', '')
        r1 = data.get('rasgo1', '')
        r2 = data.get('rasgo2', '')
        color = data.get('color', '')
        
        existe_similar = Producto.objects.filter(
            categoria__nombre__iexact=cat,
            rasgo1__iexact=r1,
            rasgo2__iexact=r2,
            color__nombre__iexact=color
        ).exists()
        
        if existe_similar:
            return JsonResponse({
                'status': 'blocked',
                'message': '🚫 Ya existe un producto IDÉNTICO. No se puede crear duplicado.',
                'requiere_confirmacion': False
            }, status=400)
    
    # Resolver objetos FK: accept both ID (preferred) and name (legacy AI fill)
    try:
        # Categoría
        if data.get('categoria_id'):
            categoria = get_object_or_404(Categoria, pk=data['categoria_id'])
        else:
            cat_nombre = data.get('categoria', 'Sin definir')
            categoria = Categoria.objects.filter(nombre__iexact=cat_nombre).first()
            if not categoria:
                categoria, _ = Categoria.objects.get_or_create(nombre=normalizar_nombre(cat_nombre) or 'Sin definir')

        # Color
        if data.get('color_id'):
            color_obj = get_object_or_404(Color, pk=data['color_id'])
        else:
            color_nombre = data.get('color', 'Sin definir')
            color_obj = Color.objects.filter(nombre__iexact=color_nombre).first()
            if not color_obj:
                color_obj, _ = Color.objects.get_or_create(nombre=normalizar_nombre(color_nombre) or 'Sin definir')

        # Modelo
        modelo_obj = None
        if data.get('modelo_id'):
            modelo_obj = Modelo.objects.filter(pk=data['modelo_id']).first()
        elif data.get('rasgo1'):
            modelo_obj = Modelo.objects.filter(nombre__iexact=data['rasgo1']).first()

        # Tela
        tela_obj = None
        if data.get('tela_id'):
            tela_obj = Tela.objects.filter(pk=data['tela_id']).first()
        else:
            rasgo2 = data.get('rasgo2', '')
            if rasgo2:
                tela_obj = Tela.objects.filter(nombre__iexact=rasgo2).first()

        # Talla FK
        talla_str = data.get('talla', 'U')
        talla_obj_cat = None
        if data.get('talla_id'):
            talla_obj_cat = Talla.objects.filter(pk=data['talla_id']).first()
        if talla_obj_cat is None:
            talla_obj_cat = Talla.buscar_por_alias(talla_str)

        # Uniqueness check via FK constraint (when modelo + talla are set)
        if not forzar_crear and modelo_obj and talla_obj_cat:
            qs = Producto.objects.filter(
                modelo=modelo_obj,
                color=color_obj,
                tela=tela_obj,
                talla_obj=talla_obj_cat,
            )
            if qs.exists():
                return JsonResponse({
                    'status': 'blocked',
                    'message': '🚫 Ya existe una variante con ese modelo, color, tela y talla.',
                    'requiere_confirmacion': False,
                }, status=400)

        rasgo1 = data.get('rasgo1', modelo_obj.nombre if modelo_obj else '')
        rasgo2 = data.get('rasgo2', tela_obj.nombre if tela_obj else '')

        producto, created = Producto.objects.get_or_create(
            categoria=categoria,
            color=color_obj,
            tela=tela_obj,
            modelo=modelo_obj,
            rasgo1=rasgo1,
            rasgo2=rasgo2,
            talla=talla_str,
            talla_obj=talla_obj_cat,
            defaults={
                'precio_venta': safe_decimal(data.get('precio', 0)),
                'estado': data.get('estado', 'TIENDA'),
                'cantidad_actual': int(data.get('stock', 1)),
                'foto': foto,
            }
        )

        res = {
            'status': 'ok',
            'sku': producto.sku,
            'id': producto.id,
            'text': str(producto),
            'message': '✅ Producto creado correctamente' if created else '✅ Producto existente reutilizado',
        }

        if idem_key:
            log.response_json = res
            log.status = 'DONE'
            log.save()

        return JsonResponse(res)

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


# ============================================================
# VISTAS DE INVENTARIO
# ============================================================

@login_required
@profile_permission_required(['Inventario', 'Vendedor'])
def pendientes_regularizacion(request):
    """Vista para productos que requieren completar datos"""
    productos = Producto.objects.filter(pendiente_regularizacion=True).select_related('categoria', 'color').order_by('-fecha_creacion')

    return render(request, 'boutique/pendientes_regularizacion.html', {
        'productos': productos,
        'categorias': Categoria.objects.all().order_by('nombre'),
        'colores': Color.objects.filter(activo=True).order_by('nombre')
    })


@login_required
@profile_permission_required(['Inventario', 'Vendedor'])
def inventario_view(request):
    """Vista de gestión de inventario"""
    q = request.GET.get('q', '')
    productos = Producto.objects.filter(
        Q(sku__icontains=q) |
        Q(rasgo1__icontains=q) |
        Q(rasgo2__icontains=q)
    ).select_related('categoria', 'color', 'modelo', 'tela').order_by('-fecha_creacion')[:100]

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
        'es_admin': es_admin(request.active_profile),
        'categorias': Categoria.objects.all().order_by('nombre'),
        'colores': Color.objects.filter(activo=True).order_by('nombre'),
        'tallas': Talla.objects.filter(activa=True).order_by('orden', 'nombre'),
        'modelos': Modelo.objects.all().order_by('nombre'),
        'telas': Tela.objects.filter(activa=True).order_by('nombre'),
    })


# ============================================================
# IMPRESIÓN DE ETIQUETAS - BROTHER QL-800
# ============================================================

@require_POST
@profile_permission_required('Inventario')
def api_imprimir_etiqueta(request, pk):
    """Imprime etiqueta para un producto en la Brother QL-800"""
    from .services.printer_service import imprimir_etiqueta_brother
    
    producto = get_object_or_404(Producto, pk=pk)
    data = json.loads(request.body) if request.body else {}
    cantidad = int(data.get('cantidad', 1))
    
    resultado = imprimir_etiqueta_brother(producto, cantidad)
    
    if resultado['success']:
        registrar_auditoria(
            usuario=request.active_profile,
            accion='EXPORTACION',
            detalles=f'Etiqueta impresa: {producto.sku} x{cantidad}',
            entidad=producto,
            request=request
        )
    
    return JsonResponse(resultado)


@require_POST
@profile_permission_required('Inventario')
def api_imprimir_etiquetas_lote(request):
    """Imprime etiquetas para múltiples productos"""
    from .services.printer_service import imprimir_etiqueta_brother
    
    data = json.loads(request.body)
    raw_productos = data.get('productos', [])
    # Accept [{id, cantidad}, ...] or [id, ...] (backward-compat)
    if raw_productos and isinstance(raw_productos[0], dict):
        producto_entries = [(int(e['id']), int(e.get('cantidad', 1))) for e in raw_productos]
    else:
        cantidad_cada = int(data.get('cantidad', 1))
        producto_entries = [(int(pid), cantidad_cada) for pid in raw_productos]

    resultados = []
    exitosos = 0
    fallidos = 0

    for pid, cantidad in producto_entries:
        try:
            producto = Producto.objects.get(pk=pid)
            resultado = imprimir_etiqueta_brother(producto, cantidad)
            resultados.append({
                'sku': producto.sku,
                'success': resultado['success'],
                'message': resultado['message']
            })
            if resultado['success']:
                exitosos += 1
            else:
                fallidos += 1
        except Producto.DoesNotExist:
            resultados.append({
                'sku': f'ID:{pid}',
                'success': False,
                'message': 'Producto no encontrado'
            })
            fallidos += 1
    
    return JsonResponse({
        'success': fallidos == 0,
        'exitosos': exitosos,
        'fallidos': fallidos,
        'detalles': resultados,
        'message': f'✅ {exitosos} etiquetas impresas' if fallidos == 0 else f'⚠️ {exitosos} impresas, {fallidos} fallidas'
    })


@login_required
def api_preview_etiqueta(request, pk):
    """Genera preview de etiqueta sin imprimir"""
    from .services.printer_service import generar_preview_etiqueta
    
    producto = get_object_or_404(Producto, pk=pk)
    resultado = generar_preview_etiqueta(producto)
    return JsonResponse(resultado)


@profile_permission_required('Inventario')
def api_verificar_impresora(request):
    """Verifica el estado de la impresora Brother"""
    from .services.printer_service import verificar_impresora
    return JsonResponse(verificar_impresora())


@login_required
def api_get_variantes(request, pk):
    """Obtiene variantes del mismo modelo y categoría"""
    producto = get_object_or_404(Producto, pk=pk)
    # Si no tiene modelo, buscar por rasgos similares
    if producto.modelo:
        variantes = Producto.objects.filter(
            categoria=producto.categoria,
            modelo=producto.modelo
        ).exclude(id=pk).select_related('color')
    else:
        variantes = Producto.objects.filter(
            categoria=producto.categoria,
            rasgo1=producto.rasgo1
        ).exclude(id=pk).select_related('color')

    results = [{
        'id': v.id,
        'sku': v.sku,
        'color': v.color.nombre,
        'talla': v.talla,
        'stock': v.cantidad_actual
    } for v in variantes]

    return JsonResponse({'status': 'ok', 'results': results})


@require_POST
@login_required
@profile_permission_required('Inventario')
def api_clonar_variante(request, pk):
    """Clona un producto base para crear una variante (mismo modelo/tela, diferente color/talla)."""
    try:
        producto_base = get_object_or_404(Producto, pk=pk)
        data = json.loads(request.body)
        stock_inicial = int(data.get('stock', 0))

        # Resolver color
        if data.get('color_id'):
            color_obj = get_object_or_404(Color, pk=data['color_id'])
        else:
            color_nombre = data.get('color', '')
            color_obj, _ = Color.objects.get_or_create(nombre=normalizar_nombre(color_nombre) or color_nombre)

        # Resolver talla
        talla_str = data.get('talla', '')
        if data.get('talla_id'):
            talla_obj_cat = Talla.objects.filter(pk=data['talla_id']).first()
        else:
            talla_obj_cat = Talla.buscar_por_alias(talla_str) if talla_str else None

        modelo_obj = producto_base.modelo
        tela_obj = producto_base.tela

        # Dedup check via FK constraint
        if modelo_obj and talla_obj_cat:
            if Producto.objects.filter(
                modelo=modelo_obj,
                color=color_obj,
                tela=tela_obj,
                talla_obj=talla_obj_cat,
            ).exists():
                return JsonResponse({
                    'status': 'blocked',
                    'message': 'Ya existe una variante con ese modelo, color, tela y talla.',
                }, status=400)

        nueva_variante = Producto.objects.create(
            categoria=producto_base.categoria,
            modelo=modelo_obj,
            tela=tela_obj,
            color=color_obj,
            talla=talla_str,
            talla_obj=talla_obj_cat,
            precio_venta=producto_base.precio_venta,
            rasgo1=producto_base.rasgo1,
            rasgo2=producto_base.rasgo2,
            cantidad_actual=stock_inicial,
            stock_teorico=stock_inicial,
            estado='TIENDA',
        )

        registrar_auditoria(
            usuario=request.active_profile,
            accion='MOVIMIENTO_INV',
            detalles=f'Variante creada para {producto_base.sku}: {nueva_variante.sku}',
            entidad=nueva_variante,
            request=request,
        )

        return JsonResponse({
            'status': 'ok',
            'sku': nueva_variante.sku,
            'id': nueva_variante.id,
            'message': 'Variante agregada con éxito',
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@require_POST
@login_required
@profile_permission_required(['Inventario', 'Vendedor'])
def api_producto_regularizar(request, pk):
    """Regulariza un producto pendiente"""
    data = json.loads(request.body)
    producto = get_object_or_404(Producto, pk=pk)

    try:
        cat_nombre = data.get('categoria')
        color_nombre = data.get('color')

        if cat_nombre:
            producto.categoria, _ = Categoria.objects.get_or_create(nombre=cat_nombre)
        if color_nombre:
            producto.color, _ = Color.objects.get_or_create(nombre=color_nombre)

        producto.rasgo1 = data.get('rasgo1', producto.rasgo1)
        producto.rasgo2 = data.get('rasgo2', producto.rasgo2)
        producto.precio_venta = safe_decimal(data.get('precio', producto.precio_venta))
        producto.pendiente_regularizacion = data.get('pendiente_regularizacion', False)

        producto.save()

        registrar_auditoria(
            usuario=request.active_profile,
            accion='EDICION_PRODUCTO',
            detalles=f'Producto {producto.sku} regularizado',
            entidad=producto,
            request=request
        )

        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@require_POST
@login_required
@profile_permission_required('Admin')
def api_eliminar_producto(request, pk):
    """Elimina un producto (solo Admin)"""
    from django.db.models.deletion import ProtectedError
    from django.db import IntegrityError
    producto = get_object_or_404(Producto, pk=pk)
    sku = producto.sku  # capturar antes de borrar

    try:
        producto.delete()
        registrar_auditoria(
            usuario=request.active_profile,
            accion='ELIMINACION_PRODUCTO',
            detalles=f'Producto {sku} eliminado',
            request=request
        )
        return JsonResponse({'status': 'ok'})
    except ProtectedError:
        return JsonResponse({
            'status': 'error',
            'message': 'No se puede eliminar: el producto tiene ventas, movimientos o pedidos relacionados.'
        }, status=400)
    except IntegrityError as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


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
        producto.precio_venta = safe_decimal(data.get('precio', producto.precio_venta))
        
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
            producto.cantidad_actual = nuevo_stock

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


@require_POST
@login_required
@profile_permission_required('Inventario')
def api_regenerar_barcodes(request):
    """Regenera códigos de barras para productos que no los tienen."""
    sin_barcode = Producto.objects.filter(
        Q(barcode_image='') | Q(barcode_image__isnull=True)
    )
    total = sin_barcode.count()
    generados = 0
    errores = []
    for prod in sin_barcode:
        try:
            prod.barcode_image = None
            prod.save()
            generados += 1
        except Exception as e:
            errores.append(f"{prod.sku}: {e}")
    return JsonResponse({
        'status': 'ok',
        'total_sin_barcode': total,
        'generados': generados,
        'errores': errores[:10],
        'message': f'✅ {generados} barcodes generados de {total} sin código'
    })


# ============================================================
# VISTAS DE AGENDA
# ============================================================



# ============================================================
# SERVICIOS Y AJUSTES
# ============================================================

@login_required
@profile_permission_required('Vendedor')
def servicios_list(request):
    """Lista de servicios activos y búsqueda"""
    from .models import Servicio
    q = request.GET.get('q', '').strip()
    estado = request.GET.get('estado', '')

    servicios = Servicio.objects.select_related('cliente', 'novia', 'creado_por').prefetch_related('pagos_servicio')

    if q:
        servicios = servicios.filter(
            Q(descripcion__icontains=q) |
            Q(cliente__nombre__icontains=q) |
            Q(cliente__telefono__icontains=q) |
            Q(novia__nombre__icontains=q)
        )
    if estado:
        servicios = servicios.filter(estado=estado)
    else:
        servicios = servicios.exclude(estado__in=['ENTREGADO', 'CANCELADO'])

    clientes = []
    try:
        from .models import Cliente
        clientes = Cliente.objects.order_by('nombre').values('id', 'nombre', 'telefono')[:200]
    except Exception:
        pass

    from .models import AjusteLinea
    return render(request, 'boutique/servicios_list.html', {
        'servicios': servicios,
        'q': q,
        'estado_filtro': estado,
        'clientes': list(clientes),
        'ESTADOS': Servicio.ESTADOS,
        'TIPOS': Servicio.TIPOS,
        'TIPOS_LINEA': AjusteLinea.TIPOS,
    })


@require_POST
@login_required
@profile_permission_required('Vendedor')
def api_crear_servicio(request):
    """Crea un nuevo servicio/ajuste con líneas de ajuste opcionales."""
    from .models import Servicio, Cliente, AjusteLinea
    from .services.cash_service import registrar_cobro
    try:
        data = json.loads(request.body)
        cliente_nombre_input = (data.get('cliente_nombre') or '').strip()
        if not data.get('cliente_id') and not cliente_nombre_input:
            return JsonResponse({'status': 'error', 'message': 'El nombre del cliente es obligatorio para registrar un servicio.'}, status=400)

        lineas_data = data.get('lineas', [])

        with transaction.atomic():
            # Resolve cliente
            cliente = None
            if data.get('cliente_id'):
                cliente = Cliente.objects.filter(pk=data['cliente_id']).first()
            elif cliente_nombre_input:
                tel = (data.get('cliente_telefono') or '').strip() or '0000000000'
                cliente, _ = Cliente.objects.get_or_create(
                    telefono=tel,
                    defaults={'nombre': cliente_nombre_input}
                )

            # Resolve novia if provided
            novia = None
            novia_id = data.get('novia_id')
            if novia_id:
                from .models import Novia
                novia = Novia.objects.filter(pk=novia_id).first()

            # Costo: sum from lineas when provided, else explicit field
            if lineas_data:
                costo = sum(
                    safe_decimal(l.get('precio_unitario', 0)) * int(l.get('cantidad', 1) or 1)
                    for l in lineas_data
                )
            else:
                costo = safe_decimal(data.get('costo', 0))

            # Derive service tipo from first linea type when not explicitly provided
            _LINEA_TO_SRV = {
                'BASTILLA': 'BASTILLA', 'TIRANTE': 'TIRANTE', 'MANGA': 'MANGA',
                'CINTURA': 'TALLE', 'BUSTO': 'PECHO', 'CIERRE': 'CREMALLERA',
                'HOMBRO': 'AJUSTE', 'COSTADO': 'AJUSTE', 'PIERNA': 'BASTILLA',
            }
            tipo = data.get('tipo') or (
                _LINEA_TO_SRV.get(lineas_data[0].get('tipo', ''), 'AJUSTE')
                if lineas_data else 'AJUSTE'
            )

            # Create Servicio — anticipo starts at 0; PagoServicio updates it
            srv = Servicio.objects.create(
                tipo=tipo,
                descripcion=data.get('descripcion', ''),
                cliente=cliente,
                novia=novia,
                costo=costo,
                fecha_prometida=data.get('fecha_prometida') or None,
                notas=data.get('notas', ''),
                creado_por=request.active_profile,
            )

            # Create AjusteLinea records
            for i, l in enumerate(lineas_data):
                AjusteLinea.objects.create(
                    servicio=srv,
                    tipo=(l.get('tipo') or 'OTRO'),
                    descripcion=(l.get('descripcion') or '').strip(),
                    precio_unitario=safe_decimal(l.get('precio_unitario', 0)),
                    cantidad=int(l.get('cantidad', 1) or 1),
                    notas=(l.get('notas') or '').strip(),
                    prenda=(l.get('prenda') or '').strip(),
                    orden=i,
                )

            # Register anticipo through caja (requires open CorteCaja)
            anticipo = safe_decimal(data.get('anticipo', 0))
            ticket_folio = None
            if anticipo > 0:
                ticket = registrar_cobro(
                    origen_tipo='servicio',
                    origen_obj=srv,
                    monto=anticipo,
                    metodo=data.get('metodo_pago', 'EFECTIVO'),
                    usuario=request.active_profile,
                    notas='Anticipo inicial',
                )
                ticket_folio = ticket.folio

        return JsonResponse({'status': 'ok', 'id': srv.pk, 'folio': ticket_folio})
    except ValueError as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    except Exception as e:
        logger.exception("Error en api_crear_servicio")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@require_POST
@login_required
@profile_permission_required('Vendedor')
def api_cobrar_servicio(request, pk):
    """Registra un pago para un servicio (pasa por caja y genera ticket)"""
    from .models import Servicio
    from .services.cash_service import registrar_cobro
    srv = get_object_or_404(Servicio, pk=pk)
    try:
        data = json.loads(request.body)
        monto = safe_decimal(data.get('monto', 0))
        if monto <= 0:
            return JsonResponse({'status': 'error', 'message': 'Monto inválido'}, status=400)

        ticket = registrar_cobro(
            origen_tipo='servicio',
            origen_obj=srv,
            monto=monto,
            metodo=data.get('metodo', 'EFECTIVO'),
            usuario=request.active_profile,
            referencia=data.get('referencia', ''),
            notas=data.get('notas', ''),
        )
        srv.refresh_from_db()
        return JsonResponse({'status': 'ok', 'saldo': float(srv.saldo_pendiente), 'folio': ticket.folio})
    except ValueError as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    except Exception as e:
        logger.exception("Error en api_cobrar_servicio")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@require_POST
@login_required
@profile_permission_required('Vendedor')
def api_cambiar_estado_servicio(request, pk):
    """Cambia el estado de un servicio"""
    from .models import Servicio
    srv = get_object_or_404(Servicio, pk=pk)
    try:
        data = json.loads(request.body)
        nuevo_estado = data.get('estado')
        estados_validos = [s[0] for s in Servicio.ESTADOS]
        if nuevo_estado not in estados_validos:
            return JsonResponse({'status': 'error', 'message': 'Estado inválido'}, status=400)
        srv.estado = nuevo_estado
        srv.save(update_fields=['estado'])
        return JsonResponse({'status': 'ok', 'estado_display': srv.get_estado_display()})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@require_POST
@login_required
@profile_permission_required(['Admin', 'CEO'])
def api_eliminar_servicio(request, pk):
    """Elimina un servicio (solo admin)"""
    from .models import Servicio
    srv = get_object_or_404(Servicio, pk=pk)
    srv.delete()
    return JsonResponse({'status': 'ok'})


# ============================================================
# DASHBOARD Y REPORTES
# ============================================================

@login_required
def admin_dashboard(request):
    """Dashboard para Administradores con analítica y resumen diario"""
    if not es_admin(request.active_profile):
        return redirect('index')

    from .models import MovimientoCaja
    from django.db.models.functions import TruncDate

    # 1. Resumen Diario (Hoy) - Basado en MovimientoCaja
    hoy_date = timezone.now().date()
    movs_hoy = MovimientoCaja.objects.filter(fecha__date=hoy_date)

    resumen_diario = {
        'total': movs_hoy.aggregate(Sum('monto'))['monto__sum'] or 0,
        'breakdown': movs_hoy.values('metodo_pago').annotate(total=Sum('monto')),
        'tickets_count': movs_hoy.exclude(ticket_folio='').count(),
        'anticipos': movs_hoy.filter(tipo__in=['ABONO_PEDIDO', 'ABONO_APARTADO']).aggregate(Sum('monto'))['monto__sum'] or 0,
        'liquidaciones': movs_hoy.filter(tipo='VENTA').aggregate(Sum('monto'))['monto__sum'] or 0,
    }

    # 2. Ingresos por día - últimos 60 días
    fecha_desde = timezone.now() - timedelta(days=60)
    ventas_dia = MovimientoCaja.objects.filter(fecha__gte=fecha_desde).annotate(dia=TruncDate('fecha')).values('dia').annotate(
        total=Sum('monto'),
        cantidad=Count('id')
    ).order_by('dia')

    # Serializar fechas para JSON
    ventas_dia_list = []
    for v in ventas_dia:
        ventas_dia_list.append({
            'dia': v['dia'].strftime('%Y-%m-%d') if hasattr(v['dia'], 'strftime') else str(v['dia']),
            'total': float(v['total'])
        })

    # 3. Ventas por categoría
    ventas_cat = ItemVenta.objects.values('producto__categoria__nombre').annotate(
        total=Sum('cantidad')
    ).order_by('-total')

    # 4. Ventas por Color
    ventas_color = ItemVenta.objects.values('producto__color__nombre').annotate(
        total=Sum('cantidad')
    ).order_by('-total')

    ahora = timezone.now()
    context = {
        'resumen_diario': resumen_diario,
        'ventas_dia': ventas_dia_list,
        'ventas_cat': list(ventas_cat),
        'ventas_color': list(ventas_color),
        'total_mensual': MovimientoCaja.objects.filter(fecha__month=ahora.month, fecha__year=ahora.year).aggregate(Sum('monto'))['monto__sum'] or 0
    }
    return render(request, 'boutique/admin_dashboard.html', context)


@require_POST
@login_required
@profile_permission_required('Admin')
def api_ai_strategy(request):
    """Genera una estrategia de venta usando IA con Gemini"""
    from .ai_utils import generate_sales_strategy
    
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
    
    contexto = f"""DATOS DE LA BOUTIQUE:
- Categorías más vendidas: {categorias}
- Colores más vendidos: {colores}
- Productos con stock bajo: {stock_bajo} de {total_productos}
- Mes actual: Enero 2026"""

    try:
        estrategia = generate_sales_strategy(contexto)
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
def importar_excel(request):
    """Carga masiva de modelos y telas desde Excel"""
    from openpyxl import load_workbook

    if request.method == 'POST' and request.FILES.get('archivo'):
        archivo = request.FILES['archivo']
        tipo = request.POST.get('tipo')  # 'modelos' o 'telas'

        try:
            wb = load_workbook(archivo, data_only=True)
            ws = wb.active

            resumen = {'creados': 0, 'actualizados': 0, 'errores': []}

            # Saltamos el header
            for row in ws.iter_rows(min_row=2, values_only=True):
                if not any(row): continue
                try:
                    if tipo == 'modelos':
                        # Formato: Modelo, Descripción, Precio
                        nombre = str(row[0]).strip()
                        descripcion = str(row[1]) if len(row) > 1 and row[1] else ""
                        precio = safe_decimal(row[2]) if len(row) > 2 and row[2] else 0

                        obj, created = Modelo.objects.update_or_create(
                            nombre=nombre,
                            defaults={'descripcion': descripcion}
                        )
                        # Nota: El precio no está en Modelo, sino en Producto.
                        # Según requerimiento, solo cargamos "bases" (ModeloProducto y catálogos).

                        if created: resumen['creados'] += 1
                        else: resumen['actualizados'] += 1

                    elif tipo == 'telas':
                        # Formato: Tela, Proveedor, Notas
                        nombre = str(row[0]).strip()
                        proveedor_nombre = str(row[1]).strip() if len(row) > 1 and row[1] else ""
                        notas = str(row[2]) if len(row) > 2 and row[2] else ""

                        from .models import Proveedor
                        proveedor = None
                        if proveedor_nombre:
                            proveedor, _ = Proveedor.objects.get_or_create(nombre=proveedor_nombre)

                        obj, created = Tela.objects.update_or_create(
                            nombre=nombre,
                            proveedor=proveedor,
                            defaults={'descripcion': notas}
                        )

                        if created: resumen['creados'] += 1
                        else: resumen['actualizados'] += 1

                except Exception as row_err:
                    resumen['errores'].append(f"Fila {row}: {str(row_err)}")

            registrar_auditoria(
                usuario=request.active_profile,
                accion='EXPORTACION', # Usamos exportación para importación por ahora o añadir uno nuevo
                detalles=f"Importación {tipo}: {resumen['creados']} creados, {resumen['actualizados']} actualizados",
                request=request
            )

            return render(request, 'boutique/importar_excel.html', {'resumen': resumen, 'tipo': tipo})

        except Exception as e:
            return render(request, 'boutique/importar_excel.html', {'error': str(e)})

    return render(request, 'boutique/importar_excel.html')


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


@login_required
def print_ticket_pdf(request, folio):
    """Retorna el PDF del ticket para impresión"""
    from .models import Ticket, Apartado
    from .services.ticket_service import generate_pdf_ticket

    ticket = Ticket.objects.filter(folio=folio).first()
    if ticket is None:
        # Folio de Apartado (AP-YYYYMMDD-XXXX) — buscar ticket asociado
        apartado = get_object_or_404(Apartado, folio=folio)
        ticket = apartado.tickets_asociados.order_by('-fecha_hora').first()
        if ticket is None:
            from django.http import Http404
            raise Http404("No hay ticket asociado a este apartado")

    pdf_buffer = generate_pdf_ticket(ticket.id)
    response = HttpResponse(pdf_buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="ticket_{folio}.pdf"'
    return response

@login_required
def get_ticket_escpos(request, folio):
    """Retorna los datos ESC/POS binarios"""
    from .models import Ticket
    from .services.ticket_service import generate_escpos_data
    ticket = get_object_or_404(Ticket, folio=folio)

    escpos_data = generate_escpos_data(ticket.id)
    return HttpResponse(escpos_data, content_type='application/octet-stream')


@login_required
def api_ticket_detalle(request, folio):
    """Retorna el detalle de un ticket por folio"""
    from .models import Ticket
    ticket = get_object_or_404(Ticket, folio=folio)
    return JsonResponse({
        'status': 'ok',
        'ticket': {
            'folio': ticket.folio,
            'tipo': ticket.get_tipo_display(),
            'fecha': ticket.fecha_hora.isoformat(),
            'cliente': ticket.cliente_nombre,
            'total': float(ticket.total),
            'items': ticket.snapshot_json.get('items', []) if ticket.snapshot_json else []
        }
    })

@require_POST
@login_required
@profile_permission_required(['Admin', 'CEO', 'Vendedor'])
def api_cobrar_item(request, tipo, pk):
    """
    Endpoint unificado para cobrar Pedidos o Apartados.
    Usa el servicio de caja centralizado.
    """
    from .services.cash_service import registrar_cobro
    from .models import Pedido, Apartado

    try:
        data = json.loads(request.body)
        monto = safe_decimal(data.get('monto', 0))
        metodo = data.get('metodo', 'EFECTIVO')
        referencia = data.get('referencia', '')
        notas = data.get('notas', '')

        if monto <= 0:
            return JsonResponse({'status': 'error', 'message': 'Monto inválido'}, status=400)

        if tipo == 'pedido':
            item = get_object_or_404(Pedido, pk=pk)
        elif tipo == 'apartado':
            item = get_object_or_404(Apartado, pk=pk)
        else:
            return JsonResponse({'status': 'error', 'message': 'Tipo inválido'}, status=400)

        ticket = registrar_cobro(
            origen_tipo=tipo,
            origen_obj=item,
            monto=monto,
            metodo=metodo,
            usuario=request.active_profile,
            referencia=referencia,
            notas=notas
        )

        return JsonResponse({
            'status': 'ok',
            'ticket_folio': ticket.folio,
            'ticket_print_url': f"/api/tickets/{ticket.folio}/pdf/"
        })
    except ValueError as ve:
        return JsonResponse({'status': 'caja_cerrada', 'message': str(ve)}, status=400)
    except Exception as e:
        logger.exception("Error en api_cobrar_item")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@require_POST
@login_required
@profile_permission_required(['Admin', 'CEO', 'Vendedor'])
def api_guardar_medidas(request, pedido_id):
    """Guarda o actualiza medidas asociadas a un pedido"""
    from .models import Medidas, Pedido
    pedido = get_object_or_404(Pedido, pk=pedido_id)
    try:
        data = json.loads(request.body)
        medidas, _ = Medidas.objects.get_or_create(pedido=pedido)

        for field in ['busto', 'cintura', 'cadera', 'hombro', 'largo_aproximado', 'brazo', 'espalda',
                      'talle_delantero', 'talle_trasero', 'altura_busto', 'separacion_busto',
                      'bajo_busto', 'largo_talle', 'hombro_pezon', 'hombro_bajo_busto']:
            # Accept 'largo' as alias for backwards compat
            key = 'largo_aproximado' if field == 'largo_aproximado' and 'largo_aproximado' not in data and 'largo' in data else field
            src_key = 'largo' if field == 'largo_aproximado' and 'largo' in data and 'largo_aproximado' not in data else field
            if src_key in data:
                val = data.get(src_key)
                setattr(medidas, field, safe_decimal(val, None) if val and val != '' else None)

        medidas.observaciones = data.get('observaciones', '')
        medidas.notas = data.get('notas', medidas.notas)
        if pedido.cliente:
            medidas.cliente = pedido.cliente
        if pedido.novia:
            medidas.cliente_nombre = pedido.novia.nombre

        medidas.save()
        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

@login_required
@profile_permission_required(['Admin', 'CEO', 'Vendedor'])
def api_obtener_medidas_reutilizar(request, pedido_id):
    """Busca medidas previas de la misma novia/dama para copiar"""
    from .models import Pedido
    pedido = get_object_or_404(Pedido, pk=pedido_id)
    prev_pedido = None
    if pedido.dama:
        prev_pedido = Pedido.objects.filter(dama=pedido.dama).exclude(pk=pedido.pk).order_by('-id').first()
    elif pedido.novia:
        prev_pedido = Pedido.objects.filter(novia=pedido.novia, dama__isnull=True).exclude(pk=pedido.pk).order_by('-id').first()

    if prev_pedido and hasattr(prev_pedido, 'medidas'):
        m = prev_pedido.medidas
        def fv(val):
            return float(val) if val is not None else None
        data = {
            'busto': fv(m.busto), 'cintura': fv(m.cintura), 'cadera': fv(m.cadera),
            'hombro': fv(m.hombro), 'largo_aproximado': fv(m.largo_aproximado),
            'brazo': fv(m.brazo), 'espalda': fv(m.espalda),
            'talle_delantero': fv(m.talle_delantero), 'talle_trasero': fv(m.talle_trasero),
            'altura_busto': fv(m.altura_busto), 'separacion_busto': fv(m.separacion_busto),
            'bajo_busto': fv(m.bajo_busto), 'largo_talle': fv(m.largo_talle),
            'hombro_pezon': fv(m.hombro_pezon), 'hombro_bajo_busto': fv(m.hombro_bajo_busto),
            'observaciones': m.observaciones, 'notas': m.notas,
        }
        return JsonResponse({'medidas': data})

    return JsonResponse({'status': 'error', 'message': 'No se encontraron medidas previas'}, status=404)

@require_POST
@login_required
@profile_permission_required(['Admin', 'CEO', 'Vendedor'])
def api_entregar_item(request, tipo, pk):
    """Marca un Pedido o Apartado como ENTREGADO."""
    from .models import Pedido, Apartado
    if tipo == 'pedido':
        item = get_object_or_404(Pedido, pk=pk)
        saldo = item.saldo_pendiente
    else:
        item = get_object_or_404(Apartado, pk=pk)
        saldo = item.saldo

    if saldo > 0:
        return JsonResponse({'status': 'error', 'message': 'No se puede entregar con saldo pendiente'}, status=400)

    item.estado = 'ENTREGADO'
    item.save()
    return JsonResponse({'status': 'ok'})


@require_POST
@login_required
@profile_permission_required(['Admin', 'CEO', 'Vendedor'])
def api_llego_a_tienda(request, tipo, pk):
    """Marca un Pedido o Apartado como llegado a tienda."""
    from .models import Pedido, Apartado
    if tipo == 'pedido':
        item = get_object_or_404(Pedido, pk=pk)
        item.estado = 'RECIBIDO'
    elif tipo == 'apartado':
        item = get_object_or_404(Apartado, pk=pk)
        item.estado = 'LLEGO_A_TIENDA'
    else:
        return JsonResponse({'status': 'error', 'message': 'Tipo inválido'}, status=400)
    item.llego_a_tienda_en = timezone.now()
    item.llego_a_tienda_por = request.active_profile
    item.save()
    return JsonResponse({'status': 'ok'})


@require_POST
@login_required
@profile_permission_required(['Admin', 'CEO', 'Vendedor'])
def api_cambiar_estado_pedido(request, pk):
    """Actualiza el estado de un Pedido (transiciones de taller/proveedor)."""
    from .models import Pedido
    pedido = get_object_or_404(Pedido, pk=pk)
    try:
        data = json.loads(request.body)
        nuevo_estado = data.get('estado', '').strip()
        estados_validos = [s[0] for s in Pedido.ESTADOS]
        if nuevo_estado not in estados_validos:
            return JsonResponse({'status': 'error', 'message': f'Estado inválido: {nuevo_estado}'}, status=400)
        if nuevo_estado == 'ENTREGADO' and pedido.saldo_pendiente > 0:
            return JsonResponse({'status': 'error', 'message': 'No se puede entregar con saldo pendiente'}, status=400)
        pedido.estado = nuevo_estado
        pedido.save(update_fields=['estado', 'fecha_actualizacion'])
        return JsonResponse({'status': 'ok', 'estado_display': pedido.get_estado_display()})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@require_POST
@login_required
@profile_permission_required(['Admin', 'CEO', 'Vendedor'])
def api_editar_entrega(request, tipo, pk):
    """
    Actualiza la fecha de entrega y notas de un Pedido, Apartado o Novia.
    Sincroniza automáticamente con la Agenda.
    """
    from .services.agenda_service import sync_delivery_with_agenda
    from .models import Pedido, Apartado, Novia

    try:
        data = json.loads(request.body)
        fecha_str = data.get('fecha_entrega')
        notas = data.get('notas_entrega', '')

        if tipo == 'pedido':
            obj = get_object_or_404(Pedido, pk=pk)
            obj.fecha_entrega_estimada = fecha_str if fecha_str else None
            obj.notas_entrega = notas
        elif tipo == 'apartado':
            obj = get_object_or_404(Apartado, pk=pk)
            obj.fecha_entrega_estimada = fecha_str if fecha_str else None
            obj.notas_entrega = notas
        elif tipo == 'novia':
            obj = get_object_or_404(Novia, pk=pk)
            obj.fecha_entrega = fecha_str if fecha_str else None
            obj.notas_entrega = notas
        else:
            return JsonResponse({'status': 'error', 'message': 'Tipo inválido'}, status=400)

        obj.save()
        sync_delivery_with_agenda(obj)

        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


# ──────────────────────────────────────────────────────────────────────────────
# SUBIDA EN BLOQUE
# ──────────────────────────────────────────────────────────────────────────────

@login_required
@profile_permission_required(['Admin', 'CEO', 'Inventario', 'Vendedor'])
def subida_bloque(request):
    """Vista para cargar múltiples vestidos de una vez"""
    from .models import RASGOS_ESTILO, RASGOS_CORTE, RASGOS_ESCOTE, RASGOS_TELA
    return render(request, 'boutique/subida_bloque.html', {
        'categorias': Categoria.objects.all().order_by('nombre'),
        'colores': Color.objects.filter(activo=True).order_by('nombre'),
        'rasgos_estilo': RASGOS_ESTILO,
        'rasgos_corte': RASGOS_CORTE,
        'rasgos_escote': RASGOS_ESCOTE,
        'rasgos_tela': RASGOS_TELA,
    })


@require_POST
@login_required
@profile_permission_required(['Admin', 'CEO', 'Inventario', 'Vendedor'])
def api_subida_bloque(request):
    """Crea múltiples productos en una sola transacción atómica."""
    try:
        if request.content_type and 'multipart' in request.content_type:
            filas = json.loads(request.POST.get('filas', '[]'))
            fotos = {k: v for k, v in request.FILES.items() if k.startswith('foto_')}
        else:
            data = json.loads(request.body)
            filas = data.get('filas', [])
            fotos = {}
        if not filas:
            return JsonResponse({'status': 'error', 'message': 'No hay filas'}, status=400)

        resultados = []
        with transaction.atomic():
            for i, fila in enumerate(filas):
                precio_raw = fila.get('precio', '')
                if not precio_raw or not fila.get('categoria') or not fila.get('color'):
                    resultados.append({'fila': i + 1, 'status': 'skip', 'msg': 'Fila vacía, omitida'})
                    continue
                precio = safe_decimal(precio_raw)
                if precio <= 0:
                    resultados.append({'fila': i + 1, 'status': 'error', 'msg': 'Precio inválido'})
                    continue
                categoria, _ = Categoria.objects.get_or_create(nombre=fila['categoria'].strip())
                color, _ = Color.objects.get_or_create(
                    nombre=fila['color'].strip(),
                    defaults={'codigo_hex': '#CCCCCC', 'activo': True}
                )
                rasgo1_val = fila.get('rasgo1', '').strip()
                rasgo1_prefix = rasgo1_val[:20] if rasgo1_val else ''
                posible_duplicado = None
                if rasgo1_prefix:
                    dup_candidate = Producto.objects.filter(
                        categoria__nombre=fila['categoria'].strip(),
                        color__nombre=fila['color'].strip(),
                        rasgo1__icontains=rasgo1_prefix,
                    ).exclude(rasgo1='').first()
                    if dup_candidate:
                        posible_duplicado = {'sku': dup_candidate.sku, 'id': dup_candidate.id}
                producto, created = Producto.objects.get_or_create(
                    categoria=categoria,
                    color=color,
                    talla=fila.get('talla', 'U').strip(),
                    rasgo1=rasgo1_val,
                    rasgo2=fila.get('rasgo2', '').strip(),
                    defaults={'precio_venta': precio, 'cantidad_actual': 0, 'estado': 'TIENDA'}
                )
                # If get_or_create matched exactly, the posible_duplicado IS the same product — clear it
                if posible_duplicado and not created and posible_duplicado['id'] == producto.id:
                    posible_duplicado = None
                producto.cantidad_actual += 1
                if created:
                    producto.precio_venta = precio
                foto_file = fotos.get(f'foto_{i}')
                if foto_file and not producto.foto:
                    producto.foto = foto_file
                producto.save(update_fields=['cantidad_actual', 'precio_venta', 'foto'])
                # Refresh from DB so foto field holds the Cloudinary URL written
                # by the storage backend, not the raw in-memory file object.
                if producto.foto:
                    producto.refresh_from_db(fields=['foto'])
                resultados.append({
                    'fila': i + 1,
                    'status': 'nuevo' if created else 'existente',
                    'sku': producto.sku,
                    'id': producto.id,
                    'desc': str(producto),
                    'msg': 'Creado' if created else f'Ya existía — stock +1 (total: {producto.cantidad_actual})',
                    'tiene_foto': bool(foto_file),
                    'foto_url': producto.foto.url if producto.foto else None,
                    'posible_duplicado': posible_duplicado,
                })

        ids_nuevos = [r['id'] for r in resultados if r['status'] in ('nuevo', 'existente')]
        fotos_guardadas = [r['id'] for r in resultados if r.get('tiene_foto')]
        return JsonResponse({'status': 'ok', 'resultados': resultados, 'ids_nuevos': ids_nuevos})
    except Exception as e:
        logger.exception("Error en api_subida_bloque")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


@require_POST
@login_required
@profile_permission_required(['Admin', 'CEO', 'Inventario', 'Vendedor'])
def api_foto_producto(request, pk):
    """Sube o reemplaza la foto de un producto existente."""
    producto = get_object_or_404(Producto, pk=pk)
    foto = request.FILES.get('foto')
    if not foto:
        return JsonResponse({'status': 'error', 'message': 'No se recibió foto'}, status=400)
    if producto.foto:
        try:
            producto.foto.delete(save=False)
        except Exception:
            pass
    producto.foto = foto
    producto.save(update_fields=['foto'])
    # Refresh from DB so the field holds the Cloudinary public ID/URL written
    # by the storage backend, not the in-memory InMemoryUploadedFile object.
    producto.refresh_from_db(fields=['foto'])
    return JsonResponse({'status': 'ok', 'foto_url': producto.foto.url})


# ============================================================
# CATÁLOGOS CONTROLADOS: Talla, Modelo
# ============================================================

@require_POST
@login_required
@profile_permission_required(['Admin', 'CEO', 'Inventario', 'Vendedor'])
def api_crear_talla(request):
    """Crea una nueva talla controlada con validación de duplicados."""
    data = json.loads(request.body)
    nombre = data.get('nombre', '').strip()
    if not nombre:
        return JsonResponse({'status': 'error', 'message': 'El nombre es requerido'}, status=400)

    # Case-insensitive dedup
    if Talla.objects.filter(nombre__iexact=nombre).exists():
        return JsonResponse({'status': 'blocked', 'message': f'Ya existe una talla "{nombre}"'}, status=400)

    # Check alias collision
    existing = Talla.buscar_por_alias(nombre)
    if existing:
        return JsonResponse({
            'status': 'blocked',
            'message': f'"{nombre}" es un alias de la talla existente "{existing.nombre}"',
        }, status=400)

    talla = Talla.objects.create(
        nombre=nombre,
        aliases_json=data.get('aliases', []),
        orden=data.get('orden', 999),
        activa=True,
    )
    return JsonResponse({'status': 'ok', 'id': talla.id, 'nombre': talla.nombre})


@login_required
@profile_permission_required(['Admin', 'CEO', 'Inventario', 'Vendedor'])
def api_listar_tallas(request):
    """Lista tallas activas del catálogo."""
    tallas = list(
        Talla.objects.filter(activa=True)
        .order_by('orden', 'nombre')
        .values('id', 'nombre', 'aliases_json', 'orden')
    )
    return JsonResponse({'status': 'ok', 'tallas': tallas})


@require_POST
@login_required
@profile_permission_required(['Admin', 'CEO', 'Inventario', 'Vendedor'])
def api_crear_modelo_catalogo(request):
    """Crea un nuevo modelo en el catálogo con validación de duplicados."""
    data = json.loads(request.body)
    nombre = data.get('nombre', '').strip()
    if not nombre:
        return JsonResponse({'status': 'error', 'message': 'El nombre es requerido'}, status=400)

    nombre_norm = normalizar_nombre(nombre)

    # Accent-insensitive dedup
    if Modelo.objects.filter(nombre__iexact=nombre_norm).exists():
        return JsonResponse({'status': 'blocked', 'message': f'Ya existe un modelo "{nombre_norm}"'}, status=400)

    # AI similarity check (optional, silent on failure)
    ai_warning = None
    similares = Modelo.objects.filter(
        nombre__icontains=nombre_norm.split()[0] if nombre_norm else ''
    ).values_list('nombre', flat=True)[:10]
    if similares:
        try:
            from .ai_utils import get_gemini_client, GEMINI_MODEL
            client = get_gemini_client()
            if client:
                prompt = f"""¿El modelo "{nombre_norm}" es igual o muy similar a alguno de estos modelos?
Modelos existentes: {', '.join(similares)}
Responde SOLO con "IGUAL: [nombre]", "SIMILAR: [nombre]" o "DIFERENTE"."""
                response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
                ai_resp = response.text.strip()
                if 'IGUAL' in ai_resp.upper():
                    return JsonResponse({'status': 'blocked', 'message': f'Parece igual a uno existente. {ai_resp}'}, status=400)
                elif 'SIMILAR' in ai_resp.upper():
                    ai_warning = ai_resp
        except Exception:
            pass

    categoria = None
    if data.get('categoria_id'):
        categoria = Categoria.objects.filter(pk=data['categoria_id']).first()

    modelo = Modelo.objects.create(
        nombre=nombre_norm,
        descripcion=data.get('descripcion', ''),
        referencia=data.get('referencia', ''),
        categoria=categoria,
        es_especial=data.get('es_especial', False),
        combinacion_telas=data.get('combinacion_telas', ''),
        notas_confeccion=data.get('notas_confeccion', ''),
        codigo_especial=data.get('codigo_especial', ''),
    )
    res = {'status': 'ok', 'id': modelo.id, 'nombre': modelo.nombre, 'message': f'Modelo "{modelo.nombre}" creado'}
    if ai_warning:
        res['warning'] = ai_warning
    return JsonResponse(res)


@login_required
@profile_permission_required(['Admin', 'CEO', 'Inventario', 'Vendedor'])
def api_listar_modelos(request):
    """Lista modelos con búsqueda opcional."""
    q = request.GET.get('q', '')
    qs = Modelo.objects.all()
    if q:
        qs = qs.filter(nombre__icontains=q)
    modelos = list(qs.order_by('nombre').values('id', 'nombre', 'referencia', 'es_especial', 'categoria_id')[:100])
    return JsonResponse({'status': 'ok', 'modelos': modelos})
