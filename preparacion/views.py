"""A deliberately small, separate path for preparing a one-time stocktake."""

from decimal import Decimal, InvalidOperation
from io import BytesIO

import barcode
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.db.models import Count
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from boutique.middleware import profile_permission_required
from boutique.models import (Categoria, Color, Modelo, MovimientoInventario,
                             Producto, Talla, Tela)
from boutique.utils import normalizar_nombre
from .models import JornadaConteo, PiezaEtiqueta, VariantePreparada


def _pagina(request, error=None):
    jornada = JornadaConteo.objects.filter(abierta=True).first()
    cerrada = JornadaConteo.objects.filter(abierta=False).first()
    return render(request, 'preparacion/inicio.html', {
        'hay_variantes': VariantePreparada.objects.exists(),
        'jornada': jornada, 'cerrada': cerrada,
        'error': error, 'modelos': Modelo.objects.order_by('nombre')[:200],
        'categorias': Categoria.objects.order_by('nombre'),
        'colores': Color.objects.filter(activo=True).order_by('nombre'),
        'telas': Tela.objects.filter(activa=True).order_by('nombre'),
        'tallas': Talla.objects.filter(activa=True),
        'total_etiquetas': PiezaEtiqueta.objects.count(),
        'total_contadas': PiezaEtiqueta.objects.filter(jornada__isnull=False,
                                                       contada__isnull=False).count(),
        'selected_model_id': request.GET.get('modelo', ''),
    })


@login_required
@profile_permission_required(['Inventario', 'Vendedor'])
def inicio(request):
    return _pagina(request)


@login_required
@profile_permission_required(['Inventario', 'Vendedor'])
def nueva_variante(request, producto_id):
    base = get_object_or_404(Producto.objects.select_related('modelo', 'categoria'), pk=producto_id)
    return render(request, 'preparacion/nueva_variante.html', {
        'base': base, 'colores': Color.objects.filter(activo=True).order_by('nombre'),
        'telas': Tela.objects.filter(activa=True).order_by('nombre'),
        'tallas': Talla.objects.filter(activa=True),
    })


@require_POST
@login_required
@profile_permission_required(['Inventario', 'Vendedor'])
def verificar_etiqueta(request):
    codigo = request.POST.get('codigo', '').strip()
    pieza = (PiezaEtiqueta.objects.select_related(
        'variante__producto__modelo', 'variante__producto__color',
        'variante__producto__tela')
        .filter(codigo=codigo).first())
    if not pieza:
        return JsonResponse({'ok': False, 'message':
                             'Este código no existe en la app. Revisa la etiqueta antes de imprimir más.'}, status=404)
    producto = pieza.variante.producto
    cierre = JornadaConteo.objects.filter(abierta=False).first()
    if pieza.vendida:
        estado = 'Vendida'
    elif pieza.contada and pieza.variante.confirmada:
        estado = 'Lista para vender'
    elif pieza.contada:
        estado = 'Contada; falta cerrar el inventario inicial'
    elif cierre and pieza.emitida <= cierre.cerrada:
        estado = 'No fue contada al cerrar el inventario; revisar antes de usar'
    else:
        estado = 'Creada; pendiente de conteo. Aún no se puede vender'
    detalles = ' · '.join(filter(None, [producto.modelo.nombre if producto.modelo else '',
                                      producto.color.nombre if producto.color else '',
                                      producto.talla,
                                      producto.tela.nombre if producto.tela else '']))
    return JsonResponse({'ok': True, 'codigo': pieza.codigo, 'sku': producto.sku,
                         'estado': estado,
                         'message': f'{pieza.codigo} → {producto.sku} · {detalles}. {estado}.'})


@login_required
@profile_permission_required(['Inventario', 'Vendedor'])
def pagina_conteo(request):
    jornada = JornadaConteo.objects.filter(abierta=True).first()
    cerrada = JornadaConteo.objects.filter(abierta=False).first()
    cantidades = {}
    if jornada:
        cantidades = dict(PiezaEtiqueta.objects.filter(jornada=jornada, contada__isnull=False)
                          .values('variante_id').annotate(n=Count('pk'))
                          .values_list('variante_id', 'n'))
    elif cerrada:
        cantidades = dict(PiezaEtiqueta.objects.filter(contada__gte=cerrada.cerrada)
                          .values('variante_id').annotate(n=Count('pk'))
                          .values_list('variante_id', 'n'))
    variantes = list(VariantePreparada.objects.select_related(
        'producto__modelo', 'producto__color', 'producto__tela').order_by(
        'producto__modelo__nombre', 'producto__color__nombre', 'producto__talla'))
    for variante in variantes:
        variante.contadas = cantidades.get(variante.pk, 0)
    recientes = (PiezaEtiqueta.objects.filter(jornada=jornada, contada__isnull=False)
                .select_related('variante__producto__modelo', 'variante__producto__color')
                .order_by('-contada')[:10]) if jornada else (
                PiezaEtiqueta.objects.filter(contada__gte=cerrada.cerrada)
                .select_related('variante__producto__modelo', 'variante__producto__color')
                .order_by('-contada')[:10] if cerrada else [])
    return render(request, 'preparacion/conteo.html', {
        'jornada': jornada, 'cerrada': cerrada, 'variantes': variantes,
        'recientes': recientes, 'total': sum(cantidades.values()),
        'hay_etiquetas': PiezaEtiqueta.objects.exists(),
    })


@require_POST
@login_required
@profile_permission_required(['Inventario', 'Vendedor'])
def guardar_variante(request):
    try:
        estimada = int(request.POST.get('cantidad_estimada') or 0)
        if not 0 <= estimada <= 10000:
            raise ValueError('La cantidad estimada debe estar entre 0 y 10 000.')
        precio = Decimal(request.POST.get('precio', ''))
        if precio <= 0:
            raise ValueError('Indica un precio mayor que cero.')
        talla = request.POST.get('talla', '').strip().upper()
        if not talla:
            raise ValueError('Elige la talla.')
        if not request.POST.get('color_id') and not request.POST.get('color_nuevo', '').strip():
            raise ValueError('Elige o escribe un color.')
        with transaction.atomic():
            base_id = request.POST.get('base_producto_id')
            base = (get_object_or_404(Producto.objects.select_for_update(), pk=base_id)
                    if base_id else None)
            modelo_id = request.POST.get('modelo_id')
            if base:
                modelo = base.modelo
                categoria = base.categoria
            elif modelo_id:
                modelo = get_object_or_404(Modelo.objects.select_for_update(), pk=modelo_id)
                categoria = modelo.categoria or get_object_or_404(
                    Categoria, pk=request.POST.get('categoria_id'))
            else:
                nombre = normalizar_nombre(request.POST.get('modelo_nuevo', '').strip())
                if not nombre:
                    raise ValueError('Elige un modelo o escribe uno nuevo.')
                if Modelo.objects.filter(nombre__iexact=nombre).exists():
                    raise ValueError('Ese modelo ya existe. Elígelo en la lista para añadirle una variante.')
                categoria = get_object_or_404(Categoria, pk=request.POST.get('categoria_id'))
                modelo = Modelo.objects.create(nombre=nombre, categoria=categoria,
                                               foto_principal=request.FILES.get('foto'))
            color_id = request.POST.get('color_id')
            color = (get_object_or_404(Color, pk=color_id) if color_id else
                     Color.objects.get_or_create_normalizado(request.POST.get('color_nuevo', ''))[0])
            tela_id = request.POST.get('tela_id')
            tela_nombre = normalizar_nombre(request.POST.get('tela_nueva', '').strip())
            tela = get_object_or_404(Tela, pk=tela_id) if tela_id else None
            if not tela and tela_nombre:
                tela = Tela.objects.filter(nombre__iexact=tela_nombre).first()
                if not tela:
                    tela = Tela.objects.create(nombre=tela_nombre)
            talla_obj = Talla.buscar_por_alias(talla)
            family = (Producto.objects.filter(modelo=modelo) if modelo else
                      Producto.objects.filter(modelo__isnull=True, categoria=categoria,
                                             rasgo1=base.rasgo1 if base else ''))
            if family.filter(color=color, tela=tela, talla=talla).exists():
                raise ValueError('Esta combinación ya existe. Busca su tarjeta y agrega etiquetas ahí.')
            sku = ''
            if modelo:
                secuencia = max(1, family.count() + 1)
                while Producto.objects.filter(sku=f'M{modelo.pk:05d}-{secuencia:02d}').exists():
                    secuencia += 1
                sku = f'M{modelo.pk:05d}-{secuencia:02d}'
            producto = Producto.objects.create(
                sku=sku, modelo=modelo,
                categoria=categoria, color=color, tela=tela, talla=talla,
                talla_obj=talla_obj, rasgo1=base.rasgo1 if base else modelo.nombre,
                rasgo2=tela.nombre if tela else '', precio_venta=precio,
                cantidad_actual=0, stock_teorico=0, activo=False,
                foto=(base.foto.name if base and base.foto else
                      modelo.foto_principal.name if modelo and modelo.foto_principal else None),
            )
            VariantePreparada.objects.create(producto=producto, cantidad_estimada=estimada)
        if base:
            return redirect(f'{reverse("inventario_view")}?q={producto.sku}')
        return redirect(f'{reverse("inventario_view")}?q={producto.sku}')
    except (ValueError, InvalidOperation, IntegrityError) as exc:
        if request.POST.get('base_producto_id'):
            base = get_object_or_404(Producto.objects.select_related('modelo', 'categoria'),
                                     pk=request.POST['base_producto_id'])
            return render(request, 'preparacion/nueva_variante.html', {
                'base': base, 'error': str(exc),
                'colores': Color.objects.filter(activo=True).order_by('nombre'),
                'telas': Tela.objects.filter(activa=True).order_by('nombre'),
                'tallas': Talla.objects.filter(activa=True),
            })
        return _pagina(request, str(exc))


@require_POST
@login_required
@profile_permission_required(['Inventario', 'Vendedor'])
def agregar_existente(request):
    sku = request.POST.get('sku', '').strip().upper().replace("'", '-')
    producto = Producto.objects.filter(sku__iexact=sku).first()
    if not producto:
        return _pagina(request, 'No se encontró ese SKU. Revisa el código impreso.')
    if VariantePreparada.objects.filter(producto=producto).exists():
        return _pagina(request, 'Ese vestido ya está en preparación; usa su tarjeta para imprimir etiquetas.')
    variante = VariantePreparada.objects.create(
        producto=producto, cantidad_estimada=producto.cantidad_actual)
    return redirect(f'{reverse("preparacion:inicio")}#variante-{variante.pk}')


def _etiquetas_pdf(piezas):
    output = BytesIO()
    pdf = canvas.Canvas(output, pagesize=(90 * mm, 29 * mm), pageCompression=0)
    for pieza in piezas:
        producto = pieza.variante.producto
        modules = barcode.get_barcode_class('code128')(pieza.codigo).build()[0]
        width = (len(modules) * 0.45 + 10) * mm
        if width > 86 * mm:
            raise ValueError('El código de esta pieza no cabe en la etiqueta.')
        x = (90 * mm - width) / 2 + 5 * mm
        pdf.setFillColorRGB(0, 0, 0)
        pdf.setFont('Helvetica-Bold', 11)
        pdf.drawCentredString(12 * mm, 5 * mm, f'${producto.precio_venta:,.0f}')
        pdf.setFont('Helvetica', 6.5)
        pdf.drawCentredString(12 * mm, 2 * mm, f'T: {producto.talla}')
        pdf.drawCentredString(77 * mm, 3 * mm, producto.color.nombre.upper()[:14])
        start = None
        for i, bit in enumerate(modules + '0'):
            if bit == '1' and start is None:
                start = i
            elif bit == '0' and start is not None:
                pdf.rect(x + start * 0.45 * mm + 0.03 * mm, 11 * mm,
                         (i-start) * 0.45 * mm - 0.06 * mm,
                         15 * mm, stroke=0, fill=1)
                start = None
        pdf.setFont('Helvetica', 7)
        pdf.drawCentredString(45 * mm, 4.5 * mm, pieza.codigo)
        pdf.drawCentredString(45 * mm, 1.7 * mm, producto.sku)
        pdf.showPage()
    pdf.save()
    response = HttpResponse(output.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = 'inline; filename="etiquetas-piezas.pdf"'
    return response


@require_POST
@login_required
@profile_permission_required(['Inventario', 'Vendedor'])
def emitir_etiquetas(request, variante_id):
    variante = get_object_or_404(VariantePreparada, pk=variante_id)
    try:
        cantidad = int(request.POST.get('cantidad', '1'))
    except ValueError:
        cantidad = 0
    if not 1 <= cantidad <= 20:
        return HttpResponse('Imprime entre 1 y 20 etiquetas a la vez.', status=400)
    with transaction.atomic():
        piezas = [PiezaEtiqueta.objects.create(variante=variante)
                  for _ in range(cantidad)]
    return _etiquetas_pdf(piezas)


@require_POST
@login_required
@profile_permission_required(['Inventario', 'Vendedor'])
def imprimir_producto(request, producto_id):
    producto = get_object_or_404(Producto, pk=producto_id)
    try:
        cantidad = int(request.POST.get('cantidad', '1'))
    except ValueError:
        cantidad = 0
    if not 1 <= cantidad <= 20:
        return HttpResponse('Imprime entre 1 y 20 etiquetas a la vez.', status=400)
    with transaction.atomic():
        variante, _ = VariantePreparada.objects.get_or_create(
            producto=producto, defaults={'cantidad_estimada': producto.cantidad_actual})
        piezas = [PiezaEtiqueta.objects.create(variante=variante)
                  for _ in range(cantidad)]
    return _etiquetas_pdf(piezas)


@login_required
@profile_permission_required(['Inventario', 'Vendedor'])
def reimprimir(request, pieza_id):
    pieza = get_object_or_404(PiezaEtiqueta.objects.select_related(
        'variante__producto__color'), pk=pieza_id)
    return _etiquetas_pdf([pieza])


@require_POST
@login_required
@profile_permission_required(['Inventario', 'Vendedor'])
def reimprimir_codigo(request, producto_id):
    codigo = request.POST.get('codigo', '').strip()
    pieza = get_object_or_404(PiezaEtiqueta.objects.select_related('variante__producto__color'),
                              codigo=codigo, variante__producto_id=producto_id)
    return _etiquetas_pdf([pieza])


@require_POST
@login_required
@profile_permission_required(['Inventario', 'Vendedor'])
def iniciar_conteo(request):
    if JornadaConteo.objects.filter(abierta=False).exists():
        return HttpResponse('El inventario inicial ya se cerró.', status=409)
    if not PiezaEtiqueta.objects.exists():
        return _pagina(request, 'Primero imprime y pega algunas etiquetas.')
    try:
        JornadaConteo.objects.get_or_create(abierta=True,
                                            defaults={'responsable': request.active_profile})
    except IntegrityError:
        pass
    return redirect('preparacion:conteo')


@require_POST
@login_required
@profile_permission_required(['Inventario', 'Vendedor'])
def escanear(request):
    codigo = request.POST.get('codigo', '').strip().upper()
    with transaction.atomic():
        jornada = JornadaConteo.objects.select_for_update().filter(abierta=True).first()
        if not jornada:
            return JsonResponse({'ok': False, 'message': 'Inicia el conteo primero.'}, status=409)
        pieza = (PiezaEtiqueta.objects.select_for_update()
                 .select_related('variante__producto__modelo', 'variante__producto__color',
                                 'variante__producto__tela').filter(codigo=codigo).first())
        if not pieza:
            return JsonResponse({'ok': False, 'message': 'Etiqueta desconocida. Aparta el vestido para revisarlo.'}, status=404)
        if pieza.contada:
            return JsonResponse({'ok': False, 'message': f'Ya contaste {codigo}. No se sumó otra vez.'}, status=409)
        pieza.contada = timezone.now()
        pieza.jornada = jornada
        pieza.save(update_fields=['contada', 'jornada'])
        n = PiezaEtiqueta.objects.filter(variante=pieza.variante, jornada=jornada).count()
    producto = pieza.variante.producto
    return JsonResponse({'ok': True, 'message': f'{producto.sku}: {n} vestido(s) contado(s)',
                         'codigo': pieza.codigo, 'variante_id': pieza.variante_id,
                         'sku': producto.sku,
                         'modelo': producto.modelo.nombre if producto.modelo else producto.rasgo1,
                         'color': producto.color.nombre if producto.color else '',
                         'talla': producto.talla, 'cantidad_variante': n,
                         'total': PiezaEtiqueta.objects.filter(jornada=jornada).count()})


@require_POST
@login_required
@profile_permission_required(['Inventario', 'Vendedor'])
def recibir(request):
    codigo = request.POST.get('codigo', '').strip()
    with transaction.atomic():
        cierre = JornadaConteo.objects.filter(abierta=False).first()
        if not cierre:
            return JsonResponse({'ok': False, 'message': 'Primero termina el inventario inicial.'}, status=409)
        pieza = (PiezaEtiqueta.objects.select_for_update()
                 .select_related('variante__producto__modelo', 'variante__producto__color')
                 .filter(codigo=codigo).first())
        if not pieza:
            return JsonResponse({'ok': False, 'message': 'Etiqueta desconocida. Revisa el vestido.'}, status=404)
        if pieza.contada or pieza.vendida:
            return JsonResponse({'ok': False, 'message': 'Esta pieza ya se recibió o se vendió. No se sumó otra vez.'}, status=409)
        if pieza.emitida <= cierre.cerrada:
            return JsonResponse({'ok': False, 'message': 'Esta etiqueta sobró del conteo inicial y ya no sirve para recibir mercancía. Crea una nueva etiqueta para el vestido que acaba de llegar.'}, status=409)
        producto = Producto.objects.select_for_update().get(pk=pieza.variante.producto_id)
        pieza.contada = timezone.now()
        pieza.save(update_fields=['contada'])
        variante = pieza.variante
        if not variante.confirmada:
            variante.confirmada = timezone.now()
            variante.save(update_fields=['confirmada'])
        MovimientoInventario.objects.create(
            producto=producto, tipo='ENTRADA', cantidad=1, motivo='COMPRA',
            notas=f'Recepción por etiqueta {codigo}', perfil_activo=request.active_profile,
            stock_resultante=0)
        if not producto.activo:
            Producto.objects.filter(pk=producto.pk).update(activo=True)
    producto.refresh_from_db()
    return JsonResponse({'ok': True, 'message': 'Una pieza recibida y agregada al inventario.',
                         'codigo': pieza.codigo, 'sku': producto.sku,
                         'modelo': producto.modelo.nombre if producto.modelo else producto.rasgo1,
                         'color': producto.color.nombre if producto.color else '',
                         'talla': producto.talla, 'variante_id': pieza.variante_id,
                         'cantidad_variante': producto.cantidad_actual})


@require_POST
@login_required
@profile_permission_required(['Admin', 'CEO', 'Inventario'])
def cerrar_conteo(request):
    if request.POST.get('confirmar') != 'SI':
        return _pagina(request, 'Revisa los resultados y confirma el cierre.')
    with transaction.atomic():
        jornada = JornadaConteo.objects.select_for_update().filter(abierta=True).first()
        if not jornada:
            return HttpResponse('No hay conteo abierto.', status=409)
        for preparada in VariantePreparada.objects.select_related('producto').select_for_update():
            producto = Producto.objects.select_for_update().get(pk=preparada.producto_id)
            cantidad = PiezaEtiqueta.objects.filter(variante=preparada, jornada=jornada).count()
            diferencia = cantidad - producto.stock_teorico
            if diferencia:
                MovimientoInventario.objects.create(
                    producto=producto, tipo='AJUSTE', cantidad=diferencia,
                    motivo='AJUSTE_INVENTARIO', notas='Conteo inicial de piezas etiquetadas',
                    perfil_activo=request.active_profile, stock_resultante=0)
            producto.cantidad_actual = cantidad
            producto.activo = True
            producto.save(update_fields=['cantidad_actual', 'activo'])
            preparada.confirmada = timezone.now()
            preparada.save(update_fields=['confirmada'])
        jornada.abierta = False
        jornada.cerrada = timezone.now()
        jornada.save(update_fields=['abierta', 'cerrada'])
    return redirect('preparacion:inicio')
