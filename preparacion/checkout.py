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
from .models import PiezaEtiqueta, VariantePreparada


@login_required
@profile_permission_required('Vendedor')
def buscar(request):
    raw = request.GET.get('q', '').strip()
    code = raw.upper()
    piece = (PiezaEtiqueta.objects.select_related('variante__producto')
             .filter(codigo=code).first()) if code.isdigit() else None
    if piece and piece.contada and not piece.vendida and piece.variante.confirmada:
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
def vender(request):
    try:
        data = json.loads(request.body)
        items = data.get('items', [])
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
                   not by_code[code].contada for code in codes):
                return JsonResponse({'status': 'error', 'message': 'Una etiqueta ya se vendió o no fue contada.'}, status=409)
            for item in items:
                if item['id'] in prepared_ids and any(
                    by_code[code].variante.producto_id != item['id']
                    for code in item['unit_codes']
                ):
                    return JsonResponse({'status': 'error', 'message': 'La etiqueta no corresponde a este vestido.'}, status=400)
            response = original.api_registrar_venta(request)
            if response.status_code == 200 and json.loads(response.content).get('status') == 'ok':
                PiezaEtiqueta.objects.filter(pk__in=[piece.pk for piece in pieces]).update(vendida=timezone.now())
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
