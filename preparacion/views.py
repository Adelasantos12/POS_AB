"""A deliberately small, separate path for preparing a one-time stocktake."""

from decimal import Decimal, InvalidOperation
from io import BytesIO

import barcode
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
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
    variantes = list(VariantePreparada.objects.select_related(
        'producto__modelo', 'producto__color', 'producto__tela', 'producto__categoria'
    ).order_by('producto__modelo__nombre', 'producto__talla', 'producto__color__nombre'))
    for variante in variantes:
        variante.emitidas = variante.piezas.count()
        variante.contadas = variante.piezas.filter(contada__isnull=False).count()
        variante.por_imprimir = max(1, min(20, variante.cantidad_estimada - variante.emitidas))
        variante.ultimas = list(variante.piezas.order_by('-pk')[:200])
    jornada = JornadaConteo.objects.filter(abierta=True).first()
    cerrada = JornadaConteo.objects.filter(abierta=False).first()
    return render(request, 'preparacion/inicio.html', {
        'variantes': variantes, 'jornada': jornada, 'cerrada': cerrada,
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
            modelo_id = request.POST.get('modelo_id')
            if modelo_id:
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
            if Producto.objects.filter(modelo=modelo, color=color, tela=tela, talla=talla).exists():
                raise ValueError('Esta combinación ya existe. Busca su tarjeta y agrega etiquetas ahí.')
            secuencia = 1
            while Producto.objects.filter(sku=f'M{modelo.pk:05d}-{secuencia:02d}').exists():
                secuencia += 1
            # Count across the family, including variants whose SKU came from older flows.
            secuencia = max(secuencia, Producto.objects.filter(modelo=modelo).count() + 1)
            while Producto.objects.filter(sku=f'M{modelo.pk:05d}-{secuencia:02d}').exists():
                secuencia += 1
            producto = Producto.objects.create(
                sku=f'M{modelo.pk:05d}-{secuencia:02d}', modelo=modelo,
                categoria=categoria, color=color, tela=tela, talla=talla,
                talla_obj=talla_obj, rasgo1=modelo.nombre,
                rasgo2=tela.nombre if tela else '', precio_venta=precio,
                cantidad_actual=0, stock_teorico=0, activo=False,
                foto=modelo.foto_principal.name if modelo.foto_principal else None,
            )
            VariantePreparada.objects.create(producto=producto, cantidad_estimada=estimada)
        return redirect(f'{reverse("preparacion:inicio")}?modelo={modelo.pk}#nuevo')
    except (ValueError, InvalidOperation, IntegrityError) as exc:
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


@login_required
@profile_permission_required(['Inventario', 'Vendedor'])
def reimprimir(request, pieza_id):
    pieza = get_object_or_404(PiezaEtiqueta.objects.select_related(
        'variante__producto__color'), pk=pieza_id)
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
    return redirect('preparacion:inicio')


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
                 .select_related('variante__producto').filter(codigo=codigo).first())
        if not pieza:
            return JsonResponse({'ok': False, 'message': 'Etiqueta desconocida. Aparta el vestido para revisarlo.'}, status=404)
        if pieza.contada:
            return JsonResponse({'ok': False, 'message': f'Ya contaste {codigo}. No se sumó otra vez.'}, status=409)
        pieza.contada = timezone.now()
        pieza.jornada = jornada
        pieza.save(update_fields=['contada', 'jornada'])
        n = PiezaEtiqueta.objects.filter(variante=pieza.variante, jornada=jornada).count()
    return JsonResponse({'ok': True, 'message': f'{pieza.variante.producto.sku}: {n} vestido(s) contado(s)',
                         'total': PiezaEtiqueta.objects.filter(jornada=jornada).count()})


@require_POST
@login_required
@profile_permission_required(['Inventario', 'Vendedor'])
def recibir(request):
    codigo = request.POST.get('codigo', '').strip()
    with transaction.atomic():
        if not JornadaConteo.objects.filter(abierta=False).exists():
            return JsonResponse({'ok': False, 'message': 'Primero termina el inventario inicial.'}, status=409)
        pieza = (PiezaEtiqueta.objects.select_for_update()
                 .select_related('variante__producto').filter(codigo=codigo).first())
        if not pieza:
            return JsonResponse({'ok': False, 'message': 'Etiqueta desconocida. Revisa el vestido.'}, status=404)
        if pieza.contada or pieza.vendida:
            return JsonResponse({'ok': False, 'message': 'Esta pieza ya se recibió o se vendió. No se sumó otra vez.'}, status=409)
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
    return JsonResponse({'ok': True, 'message': 'Una pieza recibida y agregada al inventario.'})


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
