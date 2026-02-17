from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db import transaction
from .models import Apartado, ApartadoItem, Ticket, Producto, ConfiguracionTienda
from .middleware import profile_permission_required
from .utils import safe_decimal
import json
from decimal import Decimal
from django.utils import timezone

@login_required
@profile_permission_required(['Vendedor', 'Caja', 'Admin', 'CEO'])
def lista_apartados(request):
    """Vista de lista de apartados independientes"""
    q = request.GET.get('q', '')
    apartados = Apartado.objects.all().order_by('-fecha_creacion')
    if q:
        from django.db.models import Q
        apartados = apartados.filter(
            Q(cliente_nombre__icontains=q) |
            Q(folio__icontains=q) |
            Q(cliente_telefono__icontains=q)
        )

    context = {
        'apartados': apartados,
        'q': q,
        'today': timezone.now().date()
    }
    return render(request, 'boutique/apartados_list.html', context)

@require_POST
@login_required
@profile_permission_required(['Vendedor', 'Caja'])
def api_crear_apartado(request):
    """API para crear un apartado desde el POS o módulo independiente"""
    try:
        data = json.loads(request.body)
        items = data.get('items', [])
        cliente_nombre = data.get('cliente_nombre', 'Cliente General')
        cliente_telefono = data.get('cliente_telefono', '')
        anticipo = safe_decimal(data.get('anticipo', 0))
        total = safe_decimal(data.get('total', 0))
        notas = data.get('notas', '')

        from .services.cash_service import registrar_cobro, get_caja_activa
        metodo = data.get('metodo', 'EFECTIVO')

        with transaction.atomic():
            apartado = Apartado.objects.create(
                cliente_nombre=cliente_nombre,
                cliente_telefono=cliente_telefono,
                total=total,
                anticipo=0, # Se registra vía registrar_cobro
                notas=notas
            )

            for it in items:
                prod = Producto.objects.get(id=it['id'])
                ApartadoItem.objects.create(
                    apartado=apartado,
                    producto=prod,
                    descripcion=str(prod),
                    modelo=prod.modelo.nombre if prod.modelo else '',
                    color=prod.color.nombre if prod.color else '',
                    talla=prod.talla,
                    cantidad=it['cantidad'],
                    precio_unitario=prod.precio_venta,
                    subtotal=it['cantidad'] * prod.precio_venta
                )

                # Opcional: Marcar producto como apartado si es único
                if prod.cantidad_actual > 0:
                    prod.estado = 'APARTADO'
                    prod.save()

            # Emitir Ticket / Registrar Cobro
            ticket = None
            if anticipo > 0:
                ticket = registrar_cobro(
                    origen_tipo='apartado',
                    origen_obj=apartado,
                    monto=anticipo,
                    metodo=metodo,
                    usuario=request.active_profile,
                    notas='Anticipo inicial apartado'
                )
            else:
                caja = get_caja_activa()
                ticket = Ticket.objects.create(
                    tipo='APARTADO',
                    apartado=apartado,
                    cliente_nombre=cliente_nombre,
                    cliente_telefono=cliente_telefono,
                    total=total,
                    total_pagado=0,
                    cajero_nombre=request.active_profile.username,
                    caja=caja
                )
                ticket.populate_from_obj(apartado)

        return JsonResponse({'status': 'ok', 'id': apartado.id, 'folio': ticket.folio})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

@require_POST
@login_required
@profile_permission_required(['Vendedor', 'Caja', 'Admin', 'CEO'])
def api_apartado_editar(request, pk):
    """API para editar datos básicos de un apartado"""
    apartado = get_object_or_404(Apartado, pk=pk)
    try:
        data = json.loads(request.body)
        apartado.cliente_nombre = data.get('cliente_nombre', apartado.cliente_nombre)
        apartado.cliente_telefono = data.get('cliente_telefono', apartado.cliente_telefono)
        apartado.notas = data.get('notas', apartado.notas)
        if data.get('fecha_vencimiento'):
            apartado.fecha_vencimiento = data.get('fecha_vencimiento')
        apartado.save()
        return JsonResponse({'status': 'ok'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

@login_required
def detalle_apartado(request, pk):
    apartado = get_object_or_404(Apartado, pk=pk)
    return render(request, 'boutique/apartado_detalle.html', {'apartado': apartado})
