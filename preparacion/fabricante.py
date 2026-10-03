"""Shared external labels; internal units retain costing and sale history."""
import uuid
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import render, redirect
from django.utils import timezone
from boutique.middleware import profile_permission_required
from boutique.models import Producto, MovimientoInventario
from boutique.views import es_admin
from .models import CodigoFabricante, EntradaFabricante, CorreccionFabricante, PiezaEtiqueta, VariantePreparada, JornadaConteo, MovimientoPieza
from .costing import costo_entrada


def disponibles(producto_id):
    return PiezaEtiqueta.objects.filter(variante__producto_id=producto_id,
        variante__confirmada__isnull=False, contada__isnull=False,
        vendida__isnull=True, estado='DISPONIBLE', ubicacion='BOUTIQUE')


@login_required
@profile_permission_required(['Inventario', 'Vendedor'])
def panel(request):
    error = None
    if request.method == 'POST':
        try:
            with transaction.atomic():
                if request.POST.get('accion') == 'vincular':
                    if not es_admin(request.active_profile):
                        raise ValueError('Solo Administración puede vincular códigos.')
                    code = request.POST.get('codigo', '').strip()
                    if not code or len(code) > 80 or not code.isascii() or not code.isalnum():
                        raise ValueError('Usa un código de 1 a 80 letras o números, sin espacios.')
                    if (code.startswith('8') and len(code) == 12) or Producto.objects.filter(sku__iexact=code).exists():
                        raise ValueError('Este código está reservado para las etiquetas internas.')
                    ids = request.POST.getlist('productos')
                    products = list(Producto.objects.select_for_update().filter(pk__in=ids))
                    if not products or len(products) != len(set(ids)):
                        raise ValueError('Selecciona las variantes de este código.')
                    if len({p.modelo_id for p in products}) > 1:
                        raise ValueError('Un código debe corresponder a variantes del mismo modelo.')
                    if any(not p.modelo_id for p in products) and len(products) > 1:
                        raise ValueError('Asigna primero el mismo modelo a las variantes.')
                    mapping, _ = CodigoFabricante.objects.get_or_create(codigo=code)
                    old = set(mapping.productos.values_list('modelo_id', flat=True))
                    if old and old != {products[0].modelo_id}:
                        raise ValueError('Ese código ya pertenece a otro modelo.')
                    # Additive mapping: never silently unlink existing colours or sizes.
                    mapping.productos.add(*products)
                elif request.POST.get('accion') == 'corregir':
                    if not es_admin(request.active_profile):
                        raise ValueError('Solo Administración puede corregir color y talla.')
                    source_id, target_id = int(request.POST['origen']), int(request.POST['destino'])
                    locked = {p.pk:p for p in Producto.objects.select_for_update().filter(pk__in=[source_id,target_id]).order_by('pk')}
                    source, target = locked[source_id], locked[target_id]
                    quantity = int(request.POST.get('cantidad', '0'))
                    location = request.POST.get('ubicacion')
                    reason = request.POST.get('motivo', '').strip()
                    common = CodigoFabricante.objects.filter(pk__in=source.codigos_fabricante.values('pk'), productos=target).exists()
                    if source_id == target_id or not common or not 1 <= quantity <= 500 or not reason or len(reason)>300 or location not in ('BOUTIQUE','BODEGA'):
                        raise ValueError('Elige dos variantes distintas con el mismo código, cantidad, ubicación y motivo.')
                    correction, created = CorreccionFabricante.objects.get_or_create(clave=uuid.UUID(request.POST.get('clave','')), defaults={
                        'origen':source,'destino':target,'cantidad':quantity,'ubicacion':location,'motivo':reason,'responsable':request.active_profile})
                    if not created and (correction.origen_id,correction.destino_id,correction.cantidad,correction.ubicacion,correction.motivo)!=(source_id,target_id,quantity,location,reason):
                        raise ValueError('Esta confirmación ya se usó para otra corrección.')
                    if created:
                        pieces = list(PiezaEtiqueta.objects.select_for_update().filter(variante__producto=source,
                            contada__isnull=False,vendida__isnull=True,estado='DISPONIBLE',ubicacion=location,
                            ultima_venta__isnull=True).order_by('pk')[:quantity])
                        if len(pieces)!=quantity:
                            raise ValueError('No hay suficientes piezas corregibles en esa ubicación; no se cambió nada.')
                        variant, new = VariantePreparada.objects.get_or_create(producto=target)
                        if new and target.cantidad_actual:
                            raise ValueError('La variante destino tiene existencias anteriores sin identificar.')
                        variant.confirmada = variant.confirmada or timezone.now()
                        variant.save(update_fields=['confirmada'])
                        for piece in pieces:
                            piece.variante = variant
                            piece.revision += 1
                            piece.save(update_fields=['variante','revision'])
                            MovimientoPieza.objects.create(pieza=piece,responsable=request.active_profile,
                                accion='CORRECCION',origen=location,destino=location,estado_anterior=piece.estado,
                                estado_nuevo=piece.estado,costo_unitario=piece.costo_unitario,
                                notas=f'{source.sku} ({source.color}, {source.talla}) → {target.sku} ({target.color}, {target.talla}): {reason}'[:500])
                        for product, kind in [(source,'SALIDA'),(target,'ENTRADA')]:
                            MovimientoInventario.objects.create(producto=product,tipo=kind,cantidad=(-quantity if kind == 'SALIDA' else quantity),motivo='AJUSTE_INVENTARIO',
                                notas=f'Corrección color/talla {correction.pk}: {reason}',perfil_activo=request.active_profile,stock_resultante=0)
                        Producto.objects.filter(pk=target.pk).update(activo=True)
                elif request.POST.get('accion') == 'entrada':
                    key = uuid.UUID(request.POST.get('clave', ''))
                    product = Producto.objects.select_for_update().get(pk=request.POST.get('producto'))
                    quantity = int(request.POST.get('cantidad', '0'))
                    location = request.POST.get('ubicacion')
                    if not 1 <= quantity <= 500 or location not in ('BOUTIQUE', 'BODEGA'):
                        raise ValueError('Indica de 1 a 500 piezas y Boutique o Bodega.')
                    if not product.codigos_fabricante.exists():
                        raise ValueError('Primero vincula el código del fabricante.')
                    if JornadaConteo.objects.filter(abierta=True).exists():
                        raise ValueError('Termina el conteo inicial antes de registrar estas entradas por cantidad.')
                    receipt, created = EntradaFabricante.objects.get_or_create(clave=key, defaults={
                        'producto':product, 'cantidad':quantity, 'ubicacion':location,
                        'responsable':request.active_profile})
                    if not created:
                        if (receipt.producto_id, receipt.cantidad, receipt.ubicacion) != (product.pk, quantity, location):
                            raise ValueError('Esta confirmación ya se utilizó para otra entrada.')
                    else:
                        variant, new = VariantePreparada.objects.get_or_create(producto=product)
                        if new and product.cantidad_actual:
                            raise ValueError('Este producto tiene existencias anteriores sin identificar. No se convierten automáticamente; revisa el inventario antes de recibir más.')
                        variant.confirmada = variant.confirmada or timezone.now()
                        variant.save(update_fields=['confirmada'])
                        cost = costo_entrada(request, product)
                        for _ in range(quantity):
                            piece = PiezaEtiqueta.objects.create(variante=variant, contada=timezone.now(),
                                ubicacion=location, costo_unitario=cost)
                            MovimientoPieza.objects.create(pieza=piece, responsable=request.active_profile,
                                accion='ENTRADA', origen='', destino=location, estado_anterior='',
                                estado_nuevo='DISPONIBLE', costo_unitario=cost,
                                notas=f'Entrada por cantidad / fabricante {receipt.pk}')
                        MovimientoInventario.objects.create(producto=product, tipo='ENTRADA', cantidad=quantity,
                            motivo='COMPRA', notas=f'Entrada fabricante {receipt.pk}',
                            perfil_activo=request.active_profile, stock_resultante=0)
                        Producto.objects.filter(pk=product.pk).update(activo=True)
                else:
                    raise ValueError('Operación desconocida.')
            from django.urls import reverse
            return redirect(reverse('preparacion:fabricante') + '?guardado=1')
        except (ValueError, KeyError, Producto.DoesNotExist) as exc:
            error = str(exc)
    return render(request, 'preparacion/fabricante.html', {
        'error':error, 'es_admin':es_admin(request.active_profile), 'clave':str(uuid.uuid4()),
        'productos':Producto.objects.select_related('modelo', 'color').order_by('modelo__nombre', 'color__nombre', 'talla'),
        'vinculados':Producto.objects.filter(codigos_fabricante__isnull=False).distinct().select_related('modelo','color'),
        'codigos':CodigoFabricante.objects.prefetch_related('productos__color', 'productos__modelo'),
        'ventas':MovimientoPieza.objects.filter(pieza__variante__producto__codigos_fabricante__isnull=False, accion__in=['VENDIDA','DEVOLUCION']).values(
            'pieza__variante__producto__modelo__nombre','pieza__variante__producto__color__nombre','pieza__variante__producto__talla').annotate(
            vendidas=Count('pk',filter=Q(accion='VENDIDA'),distinct=True), devueltas=Count('pk',filter=Q(accion='DEVOLUCION'),distinct=True)),
        'resumen':PiezaEtiqueta.objects.filter(variante__producto__codigos_fabricante__isnull=False,
            contada__isnull=False, vendida__isnull=True).values('variante__producto__sku',
            'variante__producto__modelo__nombre', 'variante__producto__color__nombre',
            'variante__producto__talla', 'ubicacion').annotate(total=Count('pk', distinct=True)),
    })
