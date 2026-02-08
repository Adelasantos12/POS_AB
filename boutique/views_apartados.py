from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db import transaction
from .models import Apartado, ApartadoItem, Ticket, Producto, ConfiguracionTienda
from .middleware import profile_permission_required
import json
from decimal import Decimal

@login_required
@profile_permission_required(['Vendedor', 'Caja'])
def lista_apartados(request):
    """Vista de lista de apartados independientes"""
    q = request.GET.get('q', '')
    apartados = Apartado.objects.all().order_by('-fecha_creacion')
    if q:
        apartados = apartados.filter(cliente_nombre__icontains=q)
    return render(request, 'boutique/apartados_list.html', {'apartados': apartados, 'q': q})

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
        anticipo = Decimal(str(data.get('anticipo', 0)))
        total = Decimal(str(data.get('total', 0)))
        notas = data.get('notas', '')

        with transaction.atomic():
            apartado = Apartado.objects.create(
                cliente_nombre=cliente_nombre,
                cliente_telefono=cliente_telefono,
                total=total,
                anticipo=anticipo,
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

            # Emitir Ticket
            ticket = Ticket.objects.create(
                tipo='APARTADO',
                apartado=apartado,
                cliente_nombre=cliente_nombre,
                cliente_telefono=cliente_telefono
            )
            ticket.populate_from_obj(apartado)

        return JsonResponse({'status': 'ok', 'id': apartado.id, 'folio': ticket.folio})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

@login_required
def detalle_apartado(request, pk):
    apartado = get_object_or_404(Apartado, pk=pk)
    return render(request, 'boutique/apartado_detalle.html', {'apartado': apartado})
