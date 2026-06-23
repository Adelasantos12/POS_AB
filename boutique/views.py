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
    CorteCaja, Tienda, MovimientoInventario, Modelo, Tela,
    registrar_auditoria, Ticket, Pedido, Apartado, Novia, Dama
)
from .middleware import profile_permission_required
from .utils import safe_decimal
from django.utils import timezone
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

    # Calcular esperados desde Movimientos de Caja
    movs = corte.movimientos.all()

    efectivo_movs = sum(m.monto for m in movs if m.metodo_pago == 'EFECTIVO')
    tarjeta_movs = sum(m.monto for m in movs if m.metodo_pago == 'TARJETA')
    transf_movs = sum(m.monto for m in movs if m.metodo_pago == 'TRANSFERENCIA')

    corte.efectivo_esperado = safe_decimal(corte.monto_apertura) + safe_decimal(efectivo_movs)
    corte.tarjeta_esperada = tarjeta_movs
    corte.transferencia_esperada = transf_movs
    corte.save()

    # Resumen por tipo para la vista
    resumen_tipos = {}
    for m in movs:
        resumen_tipos[m.tipo] = resumen_tipos.get(m.tipo, 0) + m.monto

    return render(request, 'boutique/cierre_caja.html', {
        'corte': corte,
        'efectivo_movs': efectivo_movs,
        'tarjeta_movs': tarjeta_movs,
        'transf_movs': transf_movs,
        'resumen_tipos': resumen_tipos,
        'total_tickets': movs.filter(ticket_folio__isnull=False).count()
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


def _parse_servicios_bundled(servicios_json_str, cliente_obj, perfil, venta, ticket):
    """Crea servicios adicionales vinculados a una venta y los añade al snapshot del ticket."""
    from .models import Servicio
    try:
        servicios_data = json.loads(servicios_json_str or '[]')
    except Exception:
        return []
    creados = []
    for srv in servicios_data:
        costo = safe_decimal(srv.get('costo', 0))
        if costo <= 0:
            continue
        s = Servicio.objects.create(
            tipo=srv.get('tipo', 'AJUSTE'),
            descripcion=srv.get('descripcion') or srv.get('tipo', 'Servicio adicional'),
            cliente=cliente_obj,
            costo=costo,
            anticipo=costo,
            estado='RECIBIDO',
            creado_por=perfil.user if hasattr(perfil, 'user') else None,
            venta=venta,
        )
        creados.append(s)
    if creados and ticket:
        snapshot = ticket.snapshot_json or {}
        items = snapshot.get('items', [])
        for s in creados:
            items.append({
                'descripcion': f"{s.get_tipo_display()}: {s.descripcion[:40]}",
                'color': '', 'talla': '', 'cantidad': 1,
                'precio_unitario': float(s.costo),
                'subtotal': float(s.costo),
            })
        snapshot['items'] = items
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
        cliente_nombre = request.POST.get('cliente_nombre')
        cliente_notas = request.POST.get('cliente_notas')
        evento = request.POST.get('evento', '')
        fecha_entrega_est = request.POST.get('fecha_entrega_estimada')
        fecha_evento = request.POST.get('fecha_evento')

        # 1.5 Validaciones duras para Pedidos
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
                        cliente_nombre=cliente_nombre or f"Venta Rápida {producto.sku}",
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
    )[:15]
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

        with transaction.atomic():
            if es_apartado:
                # Nuevo flujo de Apartado Independiente
                apartado = Apartado.objects.create(
                    cliente_nombre=data.get('cliente_nombre', 'Cliente POS'),
                    cliente_telefono=data.get('cliente_telefono', ''),
                    total=total,
                    anticipo=0,
                    notas=f"Apartado POS - {len(items)} items"
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
                    notas='Anticipo POS'
                )

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
                venta = Venta.objects.create(
                    vendedor=request.active_profile,
                    total=total
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
    
    # Crear el producto
    try:
        cat_nombre = data.get('categoria', 'Sin definir')
        color_nombre = data.get('color', 'Sin definir')
        
        categoria = Categoria.objects.filter(nombre=cat_nombre).first()
        if not categoria:
            categoria, _ = Categoria.objects.get_or_create(nombre="Sin definir")

        color_obj = Color.objects.filter(nombre=color_nombre).first()
        if not color_obj:
            color_obj, _ = Color.objects.get_or_create(nombre="Sin definir")
        
        rasgo2 = data.get('rasgo2', '')
        tela_obj = Tela.objects.filter(nombre__iexact=rasgo2).first()

        # Usar get_or_create para prevenir duplicados a nivel BD
        producto, created = Producto.objects.get_or_create(
            categoria=categoria,
            color=color_obj,
            tela=tela_obj,
            rasgo1=data.get('rasgo1', ''),
            rasgo2=rasgo2,
            talla=data.get('talla', 'U'),
            defaults={
                'precio_venta': safe_decimal(data.get('precio', 0)),
                'estado': data.get('estado', 'TIENDA'),
                'cantidad_actual': int(data.get('stock', 1)),
                'foto': foto
            }
        )
        
        res = {
            'status': 'ok', 
            'sku': producto.sku, 
            'id': producto.id, 
            'text': str(producto),
            'message': '✅ Producto creado correctamente' if created else '✅ Producto existente reutilizado'
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
        'es_admin': es_admin(request.active_profile),
        'categorias': Categoria.objects.all().order_by('nombre'),
        'colores': Color.objects.filter(activo=True).order_by('nombre')
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
    producto_ids = data.get('productos', [])
    cantidad_cada = int(data.get('cantidad', 1))
    
    resultados = []
    exitosos = 0
    fallidos = 0
    
    for pid in producto_ids:
        try:
            producto = Producto.objects.get(pk=pid)
            resultado = imprimir_etiqueta_brother(producto, cantidad_cada)
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
    """Clona un producto base para crear una variante (mismo modelo/tela, diferente color/talla)"""
    try:
        producto_base = get_object_or_404(Producto, pk=pk)
        data = json.loads(request.body)

        color_nombre = data.get('color')
        talla = data.get('talla')
        stock_inicial = int(data.get('stock', 0))

        color_obj, _ = Color.objects.get_or_create(nombre=color_nombre)

        # Clonar el producto
        nueva_variante = Producto.objects.create(
            categoria=producto_base.categoria,
            modelo=producto_base.modelo,
            tela=producto_base.tela,
            color=color_obj,
            talla=talla,
            precio_venta=producto_base.precio_venta,
            rasgo1=producto_base.rasgo1,
            rasgo2=producto_base.rasgo2,
            cantidad_actual=stock_inicial,
            stock_teorico=stock_inicial,
            estado='TIENDA'
        )

        registrar_auditoria(
            usuario=request.active_profile,
            accion='MOVIMIENTO_INV',
            detalles=f'Variante creada para {producto_base.sku}: {nueva_variante.sku}',
            entidad=nueva_variante,
            request=request
        )

        return JsonResponse({
            'status': 'ok',
            'sku': nueva_variante.sku,
            'id': nueva_variante.id,
            'message': 'Variante agregada con éxito'
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

    return render(request, 'boutique/servicios_list.html', {
        'servicios': servicios,
        'q': q,
        'estado_filtro': estado,
        'clientes': list(clientes),
        'ESTADOS': Servicio.ESTADOS,
        'TIPOS': Servicio.TIPOS,
    })


@require_POST
@login_required
@profile_permission_required('Vendedor')
def api_crear_servicio(request):
    """Crea un nuevo servicio/ajuste"""
    from .models import Servicio, Cliente
    try:
        data = json.loads(request.body)
        cliente = None
        if data.get('cliente_id'):
            cliente = Cliente.objects.filter(pk=data['cliente_id']).first()
        elif data.get('cliente_nombre'):
            tel = data.get('cliente_telefono', '0000000000')
            cliente, _ = Cliente.objects.get_or_create(
                telefono=tel,
                defaults={'nombre': data['cliente_nombre']}
            )

        srv = Servicio.objects.create(
            tipo=data.get('tipo', 'AJUSTE'),
            descripcion=data.get('descripcion', ''),
            cliente=cliente,
            costo=safe_decimal(data.get('costo', 0)),
            anticipo=safe_decimal(data.get('anticipo', 0)),
            fecha_prometida=data.get('fecha_prometida') or None,
            notas=data.get('notas', ''),
            creado_por=request.active_profile,
        )
        return JsonResponse({'status': 'ok', 'id': srv.pk})
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

    # 2. Ingresos por día (Venta + Abonos) - últimos 30 días
    ventas_dia = MovimientoCaja.objects.annotate(dia=TruncDate('fecha')).values('dia').annotate(
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
    from .models import Ticket
    from .services.ticket_service import generate_pdf_ticket
    ticket = get_object_or_404(Ticket, folio=folio)

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
                producto, created = Producto.objects.get_or_create(
                    categoria=categoria,
                    color=color,
                    talla=fila.get('talla', 'U').strip(),
                    rasgo1=fila.get('rasgo1', '').strip(),
                    rasgo2=fila.get('rasgo2', '').strip(),
                    defaults={'precio_venta': precio, 'cantidad_actual': 0, 'estado': 'TIENDA'}
                )
                producto.cantidad_actual += 1
                if created:
                    producto.precio_venta = precio
                foto_file = fotos.get(f'foto_{i}')
                if foto_file and not producto.foto:
                    producto.foto = foto_file
                producto.save(update_fields=['cantidad_actual', 'precio_venta', 'foto'])
                resultados.append({
                    'fila': i + 1,
                    'status': 'nuevo' if created else 'existente',
                    'sku': producto.sku,
                    'id': producto.id,
                    'desc': str(producto),
                    'msg': 'Creado' if created else f'Ya existía — stock +1 (total: {producto.cantidad_actual})',
                    'tiene_foto': bool(foto_file),
                    'foto_url': producto.foto.url if producto.foto else None,
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
    return JsonResponse({'status': 'ok', 'foto_url': producto.foto.url})
