"""Vector labels for the Brother QL-800's 90 × 29 mm stock."""

import barcode
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from io import BytesIO

from boutique.models import Producto
from preparacion.models import VariantePreparada


LABEL_WIDTH = 90 * mm
LABEL_HEIGHT = 29 * mm
MODULE_WIDTH = 0.45 * mm
QUIET_ZONE = 5 * mm
BAR_HEIGHT = 15 * mm
INK_REDUCTION = 0.06 * mm


def _fit_text(pdf, text, x, y, width, font='Helvetica', size=7):
    pdf.setFont(font, size)
    while size > 5 and pdf.stringWidth(text, font, size) > width:
        size -= 0.5
        pdf.setFont(font, size)
    pdf.drawCentredString(x, y, text)


def render_labels(pdf_file, products):
    """Write one physical-size PDF page per product in the supplied sequence."""
    pdf = canvas.Canvas(pdf_file, pagesize=(LABEL_WIDTH, LABEL_HEIGHT), pageCompression=0)
    for product in products:
        sku = product.sku or ''
        modules = barcode.get_barcode_class('code128')(sku).build()[0]
        symbol_width = len(modules) * MODULE_WIDTH + 2 * QUIET_ZONE
        if symbol_width > 86 * mm:
            raise ValueError(f'El SKU {sku} no cabe en la etiqueta de 90 mm')

        # Use the full label width, as on the known-good reference label.
        # Put all human-readable information below the bars.
        pdf.setFillColorRGB(0, 0, 0)
        _fit_text(pdf, f'${product.precio_venta:,.0f}', 12 * mm, 5 * mm,
                  21 * mm, font='Helvetica-Bold', size=9)
        if product.talla:
            _fit_text(pdf, f'T: {product.talla}', 12 * mm, 2 * mm, 21 * mm, size=6)
        if product.color:
            _fit_text(pdf, product.color.nombre.upper(), 77 * mm, 3 * mm,
                      21 * mm, size=6)

        symbol_x = (LABEL_WIDTH - symbol_width) / 2
        bars_x = symbol_x + QUIET_ZONE
        run_start = None
        for index, bit in enumerate(modules + '0'):
            if bit == '1' and run_start is None:
                run_start = index
            elif bit == '0' and run_start is not None:
                pdf.rect(bars_x + run_start * MODULE_WIDTH + INK_REDUCTION / 2,
                         11 * mm,
                         (index - run_start) * MODULE_WIDTH - INK_REDUCTION, BAR_HEIGHT,
                         fill=1, stroke=0)
                run_start = None
        _fit_text(pdf, sku, 45 * mm, 4 * mm, 41 * mm, size=8)
        pdf.showPage()
    pdf.save()


@login_required
def imprimir_etiquetas_pdf(request):
    """Print-ready vector PDF; Safari's background setting does not affect it."""
    entries = []
    for item in request.GET.get('items', '').split(','):
        if not item:
            continue
        try:
            product_id, count = (int(value) for value in item.split(':'))
        except (ValueError, TypeError):
            return HttpResponse('Selección de etiquetas inválida', status=400)
        if product_id <= 0 or count < 1 or count > 50:
            return HttpResponse('Cantidad inválida (1 a 50)', status=400)
        entries.append((product_id, count))
    if not entries or sum(count for _, count in entries) > 200:
        return HttpResponse('Selecciona entre 1 y 200 etiquetas', status=400)

    products_by_id = Producto.objects.select_related('color').in_bulk(
        [product_id for product_id, _ in entries]
    )
    if len(products_by_id) != len(set(product_id for product_id, _ in entries)):
        return HttpResponse('Producto no encontrado', status=404)
    if VariantePreparada.objects.filter(producto_id__in=products_by_id).exists():
        return HttpResponse('Esta variante usa etiquetas individuales. Imprime desde su fila en Inventario.', status=409)

    output = BytesIO()
    try:
        render_labels(output, (
            products_by_id[product_id]
            for product_id, count in entries for _ in range(count)
        ))
    except ValueError as exc:
        return HttpResponse(str(exc), status=400)
    response = HttpResponse(output.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = 'inline; filename="etiquetas-90x29.pdf"'
    return response
