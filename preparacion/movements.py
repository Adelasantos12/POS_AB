"""Physical custody and returns, independent from printing and cash refunds."""
import hashlib
import json
import uuid
from datetime import date
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST
from boutique.middleware import profile_permission_required
from boutique.models import Producto, MovimientoInventario
from boutique.views import es_admin
from .models import PiezaEtiqueta, MovimientoPieza, OperacionPrendas, JornadaConteo


def describir(p):
    product = p.variante.producto
    photo = product.foto or (product.modelo.foto_principal if product.modelo else None)
    return {'codigo': p.codigo, 'revision': p.revision,
            'modelo': product.modelo.nombre if product.modelo else product.rasgo1 or product.sku,
            'variante': f'{product.color or ""} · {product.talla} · {product.tela or ""}',
            'ubicacion': p.get_ubicacion_display(), 'estado': 'Vendida' if p.vendida else p.get_estado_display(),
            'encargado': p.encargado, 'regreso': str(p.regreso_previsto or ''),
            'foto': photo.url if photo else '', 'venta': p.ultima_venta_id,
            'ticket': p.ultima_venta.ticket.folio if p.ultima_venta and p.ultima_venta.ticket else ''}


def piezas_detalle():
    return PiezaEtiqueta.objects.select_related('variante__producto__modelo',
        'variante__producto__color', 'variante__producto__tela', 'ultima_venta__ticket')


@login_required
@profile_permission_required(['Inventario', 'Vendedor'])
def panel(request):
    propias = piezas_detalle().filter(contada__isnull=False, vendida__isnull=True)
    ubicacion = request.GET.get('ubicacion', '')
    q = request.GET.get('q', '').strip()
    listado = propias
    if ubicacion in dict(PiezaEtiqueta.UBICACIONES):
        listado = listado.filter(ubicacion=ubicacion)
    if q:
        listado = listado.filter(Q(codigo__icontains=q) | Q(variante__producto__modelo__nombre__icontains=q)
                                 | Q(variante__producto__rasgo1__icontains=q))
    from django.core.paginator import Paginator
    return render(request, 'preparacion/movimientos.html', {
        'ubicaciones': PiezaEtiqueta.UBICACIONES,
        'totales': list(propias.values('ubicacion').annotate(n=Count('pk'))),
        'total': propias.count(),
        'disponibles': propias.filter(estado='DISPONIBLE', ubicacion='BOUTIQUE', variante__confirmada__isnull=False).count(),
        'fuera': propias.exclude(ubicacion='BOUTIQUE').count(),
        'pendientes': propias.filter(regreso_previsto__isnull=False).count(),
        'piezas': Paginator(listado.order_by('ubicacion', 'codigo'), 40).get_page(request.GET.get('page')),
        'q': q, 'filtro': ubicacion, 'es_admin': es_admin(request.active_profile),
        'conteo_abierto': JornadaConteo.objects.filter(abierta=True).exists(),
        'devolucion': request.GET.get('accion') == 'DEVOLUCION',
    })


@login_required
@profile_permission_required(['Inventario', 'Vendedor'])
def consultar(request):
    p = piezas_detalle().filter(codigo=request.GET.get('codigo', '').strip()).first()
    if not p:
        return JsonResponse({'message': 'No encontré esa etiqueta. Revisa el código.'}, status=404)
    if not p.contada:
        return JsonResponse({'message': 'Esta prenda todavía no está registrada. Escanéala primero en Conteo o Recibir mercancía.'}, status=409)
    data = describir(p)
    data['historial'] = [{'fecha': m.fecha.isoformat(), 'accion': m.accion,
        'origen': dict(p.UBICACIONES).get(m.origen, m.origen),
        'destino': dict(p.UBICACIONES).get(m.destino, m.destino),
        'estado': dict(p.ESTADOS).get(m.estado_nuevo, m.estado_nuevo),
        'encargado': m.encargado, 'notas': m.notas,
        'responsable': m.responsable.get_full_name() or m.responsable.username}
        for m in p.historial.select_related('responsable').all()[:30]]
    return JsonResponse(data)


@require_POST
@login_required
@profile_permission_required(['Inventario', 'Vendedor'])
def confirmar(request):
    try:
        data = json.loads(request.body)
        clave = uuid.UUID(data['clave'])
        accion = data['accion']
        destino = data['destino']
        estado = data['estado']
        encarg = str(data.get('encargado', '')).strip()
        notas = str(data.get('notas', '')).strip()
        regreso = date.fromisoformat(data['regreso']) if data.get('regreso') else None
        seleccion = data['piezas']
        codes = [p['codigo'] for p in seleccion]
        revisions = {p['codigo']: int(p['revision']) for p in seleccion}
        if not 1 <= len(codes) <= 100 or len(set(codes)) != len(codes):
            raise ValueError('Escanea entre 1 y 100 prendas distintas.')
        if accion not in ['MOVER', 'REGRESO', 'DEVOLUCION']:
            raise ValueError('Selecciona un movimiento válido.')
        if accion == 'DEVOLUCION' and not es_admin(request.active_profile):
            return JsonResponse({'message': 'Una devolución requiere un perfil Admin.'}, status=403)
        destinos = {}
        for item in seleccion:
            override = item.get('individual') or {}
            d = override.get('destino', destino)
            e = override.get('estado', estado)
            c = str(override.get('encargado', encarg)).strip()
            r = date.fromisoformat(override['regreso']) if override.get('regreso') else (None if 'regreso' in override else regreso)
            if d not in dict(PiezaEtiqueta.UBICACIONES) or e not in ['DISPONIBLE', 'ARREGLO', 'MUESTRA', 'REVISION']:
                raise ValueError('Selecciona un destino y estado válidos para cada prenda.')
            if len(c) > 150 or len(notas) > 500:
                raise ValueError('Acorta el nombre o las notas.')
            if d in ['TALLER', 'OTRO_LOCAL'] and not c:
                raise ValueError(f"{item['codigo']}: indica con quién o en qué local quedará.")
            if d == 'TALLER' and e == 'DISPONIBLE':
                raise ValueError('En taller, indica arreglo, réplica o revisión.')
            if accion == 'REGRESO' and d not in ['BOUTIQUE', 'BODEGA']:
                raise ValueError('Selecciona Boutique o Bodega para recibir el regreso.')
            if accion == 'DEVOLUCION' and (d not in ['BOUTIQUE', 'BODEGA'] or e not in ['DISPONIBLE', 'REVISION'] or not notas):
                raise ValueError('Indica el motivo y recibe en Boutique o Bodega, disponible o en revisión.')
            destinos[item['codigo']] = (d, e, c, r)
        huella = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
        with transaction.atomic():
            # Serialize against initial count/closure; piece locks serialize against checkout.
            list(JornadaConteo.objects.select_for_update().filter(abierta=True))
            op, created = OperacionPrendas.objects.get_or_create(clave=clave,
                defaults={'responsable': request.active_profile, 'huella': huella})
            if not created:
                if op.huella != huella or op.responsable_id != request.active_profile.pk:
                    raise ValueError('La confirmación cambió. Recarga y revisa la selección.')
                return JsonResponse({'ok': True, 'cantidad': op.cantidad, 'message': 'Este movimiento ya estaba registrado. No se duplicó.'})
            piezas = list(piezas_detalle().select_for_update(of=('self',)).filter(codigo__in=codes).order_by('pk'))
            if len(piezas) != len(codes):
                raise ValueError('Una etiqueta ya no existe. No se registró ningún movimiento.')
            for p in piezas:
                destino, estado, encarg, regreso = destinos[p.codigo]
                if not p.contada or p.revision != revisions[p.codigo]:
                    raise ValueError(f'{p.codigo} cambió desde el escaneo. Vuelve a escanear; no se modificó ninguna prenda.')
                if accion == 'DEVOLUCION':
                    if not p.vendida or not p.ultima_venta_id:
                        raise ValueError(f'{p.codigo} no tiene una venta vinculada para devolver. Requiere revisión de Admin.')
                elif p.vendida or p.estado in ['APARTADA', 'VENDIDA']:
                    raise ValueError(f'{p.codigo} ya se vendió o está apartada. No se puede trasladar por este flujo.')
                elif accion == 'REGRESO' and p.ubicacion == destino and p.estado == estado:
                    raise ValueError(f'{p.codigo} ya está en ese destino y estado. No se volvió a recibir.')
                elif p.ubicacion == destino and p.estado == estado and p.encargado == encarg and p.regreso_previsto == regreso:
                    raise ValueError(f'{p.codigo} ya está registrada así.')
            productos = {p.pk: p for p in Producto.objects.select_for_update().filter(
                pk__in=[p.variante.producto_id for p in piezas]).order_by('pk')}
            for p in piezas:
                destino, estado, encarg, regreso = destinos[p.codigo]
                MovimientoPieza.objects.create(pieza=p, responsable=request.active_profile, accion=accion,
                    origen=p.ubicacion, destino=destino, estado_anterior=p.estado, estado_nuevo=estado,
                    encargado=encarg, regreso_previsto=regreso, notas=notas, operacion=op,
                    venta=p.ultima_venta if accion == 'DEVOLUCION' else None)
                if accion == 'DEVOLUCION':
                    MovimientoInventario.objects.create(producto=productos[p.variante.producto_id],
                        tipo='DEVOLUCION', cantidad=1, motivo='DEVOLUCION_CLIENTE',
                        perfil_activo=request.active_profile, venta=p.ultima_venta, stock_resultante=0,
                        notas=f'Recepción física {p.codigo}. {notas}. Reembolso no realizado por esta operación.')
                    p.vendida = None
                p.ubicacion, p.estado = destino, estado
                p.encargado, p.regreso_previsto = encarg, regreso
                p.revision += 1
                p.save(update_fields=['ubicacion', 'estado', 'encargado', 'regreso_previsto', 'revision', 'vendida'])
            op.cantidad = len(piezas)
            op.save(update_fields=['cantidad'])
        return JsonResponse({'ok': True, 'cantidad': len(piezas), 'message': 'Movimiento registrado.' +
            (' La devolución física actualizó el inventario. No se realizó un reembolso.' if accion == 'DEVOLUCION' else '')})
    except (ValueError, KeyError, TypeError) as exc:
        return JsonResponse({'message': str(exc) or 'Revisa los datos.'}, status=409)
