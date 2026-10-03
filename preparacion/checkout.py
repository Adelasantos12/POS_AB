"""Resolve per-piece barcodes at checkout without changing existing sales code."""

import json
from collections import Counter

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST

from boutique import views as original
from boutique.middleware import profile_permission_required
from boutique.models import Producto
from .models import PiezaEtiqueta, VariantePreparada, MovimientoPieza, CodigoFabricante
from .fabricante import disponibles


@login_required
@profile_permission_required('Vendedor')
def buscar(request):
    raw = request.GET.get('q', '').strip()
    code = raw.upper()
    mapping = CodigoFabricante.objects.filter(codigo=raw).first()
    if mapping:
        results = []
        for product in mapping.productos.select_related('modelo', 'color').order_by('color__nombre', 'talla'):
            stock = disponibles(product.pk).count()
            results.append({'type':'PRODUCTO', 'id':product.pk, 'sku':product.sku,
                'text':f'{product.modelo or product.rasgo1} · {product.color} · {product.talla}',
                'precio':float(product.precio_venta), 'stock':stock, 'manufacturer_code':raw,
                'foto_url':product.foto.url if product.foto else None})
        return JsonResponse({'results':results, 'choose_variant':True,
            'message':'Selecciona el color y la talla que vendes.'})
    piece = (PiezaEtiqueta.objects.select_related('variante__producto')
             .filter(codigo=code).first()) if code.isdigit() else None
    if piece and piece.disponible_caja:
        product = piece.variante.producto
        return JsonResponse({'results': [{
            'type': 'PRODUCTO', 'id': product.pk, 'sku': product.sku,
            'text': str(product), 'precio': float(product.precio_venta),
            'stock': product.cantidad_actual, 'folio': product.sku,
            'foto_url': product.foto.url if product.foto else None,
            'unit_code': piece.codigo,
        }]})
    if piece:
        sku = piece.variante.producto.sku
        if piece.vendida:
            message = f'La etiqueta {piece.codigo} corresponde a {sku}, pero ya se vendió. Revisa el vestido antes de cobrar.'
        elif piece.contada and piece.variante.confirmada:
            message = f'Esta prenda está en {piece.get_ubicacion_display()} · {piece.get_estado_display()}. Registra su regreso a Boutique y disponibilidad antes de venderla.'
        elif piece.contada:
            message = f'La etiqueta {piece.codigo} corresponde a {sku}. Ya se contó, pero el inventario inicial sigue abierto. Cierra el conteo cuando terminen toda la tienda.'
        else:
            message = f'La etiqueta {piece.codigo} corresponde a {sku}, pero aún no se contó ni se recibió. Preparar o imprimir no suma inventario.'
        return JsonResponse({'results': [], 'message': message})
    # An unknown serial must never fall through to an unrelated product.
    if code.isdigit() and code.startswith('8') and len(code) == 12:
        return JsonResponse({'results': [], 'message': 'No existe esta etiqueta individual. Revisa el número.'})

    # Some HID scanner/Spanish-Mac combinations type the hyphen as an apostrophe.
    normalized = code.replace("'", '-')
    if normalized != code:
        product = Producto.objects.filter(sku=normalized, activo=True).first()
        if product and not VariantePreparada.objects.filter(producto=product).exists():
            return JsonResponse({'results': [{
                'type': 'PRODUCTO', 'id': product.pk, 'sku': product.sku,
                'text': str(product), 'precio': float(product.precio_venta),
                'stock': product.cantidad_actual, 'folio': product.sku,
                'foto_url': product.foto.url if product.foto else None,
            }]})
    response = original.api_search_global(request)
    if response.status_code != 200:
        return response
    data = json.loads(response.content)
    product_ids = [item['id'] for item in data.get('results', []) if item['type'] == 'PRODUCTO']
    prepared_ids = set(VariantePreparada.objects.filter(
        producto_id__in=product_ids
    ).values_list('producto_id', flat=True))
    data['results'] = [item for item in data.get('results', [])
                       if item['type'] != 'PRODUCTO' or item['id'] not in prepared_ids]
    return JsonResponse(data)


@require_POST
@login_required
@profile_permission_required('Vendedor')
@transaction.atomic
def vender(request):
    try:
        data = json.loads(request.body)
        items = data.get('items', [])
        external = [item for item in items if item.get('manufacturer_code')]
        if external:
            # Serialize allocation with receiving/checkout and lock in stable order.
            list(Producto.objects.select_for_update().filter(pk__in=[i['id'] for i in external]).order_by('pk'))
            if data.get('idempotency_key'):
                from boutique.models import IdempotencyLog
                previous = IdempotencyLog.objects.select_for_update().filter(key=data['idempotency_key'], status='DONE').first()
                if previous:
                    return JsonResponse(previous.response_json)
            allocated = {code for i in items for code in i.get('unit_codes', [])}
            for item in external:
                quantity = int(item['cantidad'])
                if quantity < 1 or quantity > 500 or item.get('unit_codes'):
                    raise ValueError()
                if not CodigoFabricante.objects.filter(codigo=item['manufacturer_code'], productos__pk=item['id']).exists():
                    raise ValueError()
                pieces = list(disponibles(item['id']).select_for_update().exclude(codigo__in=allocated).order_by('contada', 'pk')[:quantity])
                if len(pieces) != quantity:
                    return JsonResponse({'status':'error', 'message':'No hay suficientes piezas de ese color y talla disponibles en Boutique.'}, status=409)
                item['unit_codes'] = [p.codigo for p in pieces]
                allocated.update(item['unit_codes'])
            request._body = json.dumps(data).encode()
        prepared_ids = set(VariantePreparada.objects.filter(
            producto_id__in=[item['id'] for item in items]
        ).values_list('producto_id', flat=True))
        if not prepared_ids:
            return original.api_registrar_venta(request)
        if VariantePreparada.objects.filter(producto_id__in=prepared_ids,
                                            confirmada__isnull=True).exists():
            return JsonResponse({'status': 'error', 'message': 'Este vestido aún no fue contado.'}, status=409)

        codes = []
        for item in items:
            if item['id'] in prepared_ids:
                item_codes = item.get('unit_codes', [])
                if len(item_codes) != int(item['cantidad']):
                    return JsonResponse({'status': 'error', 'message': 'Escanea cada vestido etiquetado antes de cobrar.'}, status=400)
                codes.extend(item_codes)
        if len(codes) != len(set(codes)):
            return JsonResponse({'status': 'error', 'message': 'El mismo vestido aparece dos veces.'}, status=409)

        with transaction.atomic():
            pieces = list(PiezaEtiqueta.objects.select_for_update().filter(codigo__in=codes))
            by_code = {piece.codigo: piece for piece in pieces}
            stocks = {p.pk: p.cantidad_actual for p in Producto.objects.select_for_update()
                      .filter(pk__in=prepared_ids)}
            requested = Counter()
            for item in items:
                if item['id'] in prepared_ids:
                    requested[item['id']] += int(item['cantidad'])
            if any(stocks.get(pk, 0) < quantity for pk, quantity in requested.items()):
                return JsonResponse({'status': 'error', 'message': 'No hay suficientes vestidos disponibles.'}, status=409)
            if any(code not in by_code or by_code[code].vendida or
                   not by_code[code].disponible_caja for code in codes):
                return JsonResponse({'status': 'error', 'message': 'Una prenda no está disponible en Boutique, ya se vendió o no fue contada.'}, status=409)
            for item in items:
                if item['id'] in prepared_ids and any(
                    by_code[code].variante.producto_id != item['id']
                    for code in item['unit_codes']
                ):
                    return JsonResponse({'status': 'error', 'message': 'La etiqueta no corresponde a este vestido.'}, status=400)
            response = original.api_registrar_venta(request)
            if response.status_code == 200 and json.loads(response.content).get('status') == 'ok':
                result = json.loads(response.content)
                for piece in pieces:
                    anterior = piece.estado
                    piece.vendida = timezone.now()
                    piece.estado = 'APARTADA' if result.get('tipo') == 'apartado' else 'VENDIDA'
                    piece.ultima_venta_id = result.get('venta_id')
                    piece.revision += 1
                    piece.save(update_fields=['vendida', 'estado', 'ultima_venta', 'revision'])
                    sale_price = None
                    if piece.ultima_venta_id:
                        from boutique.models import Venta, ItemVenta
                        sale_record = Venta.objects.get(pk=piece.ultima_venta_id)
                        lines = list(ItemVenta.objects.filter(venta=sale_record))
                        # Mixed services/discounts need allocation; do not invent a margin.
                        if sum(line.precio_unitario * line.cantidad for line in lines) == sale_record.total:
                            matches = [line for line in lines if line.producto_id == piece.variante.producto_id]
                            if matches:
                                sale_price = matches[0].precio_unitario
                    MovimientoPieza.objects.create(costo_unitario=piece.costo_unitario, precio_unitario=sale_price, pieza=piece, responsable=request.active_profile,
                        accion=piece.estado, origen=piece.ubicacion, destino=piece.ubicacion,
                        estado_anterior=anterior, estado_nuevo=piece.estado, venta_id=piece.ultima_venta_id)

            return response
    except (ValueError, KeyError, TypeError):
        return JsonResponse({'status': 'error', 'message': 'Datos de venta inválidos.'}, status=400)


@require_POST
@login_required
@profile_permission_required('Vendedor')
def sincronizar(request):
    """Never reconcile serialised pieces from an unverified offline queue."""
    try:
        data = json.loads(request.body)
        ids = [item['id'] for op in data.get('operaciones', [])
               for item in (op.get('payload') or {}).get('items', [])]
    except (ValueError, KeyError, TypeError):
        return JsonResponse({'status': 'error', 'message': 'Datos de sincronización inválidos.'}, status=400)
    if VariantePreparada.objects.filter(producto_id__in=ids).exists():
        return JsonResponse({'status': 'error', 'message': 'Una venta de vestidos etiquetados requiere conexión y verificación individual.'}, status=409)
    return original.api_sync(request)
