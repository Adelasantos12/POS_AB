"""Vector labels for the Brother QL-800's 90 × 29 mm stock."""

import barcode
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from io import BytesIO

from boutique.models import Producto


LABEL_WIDTH = 90 * mm
LABEL_HEIGHT = 29 * mm
MODULE_WIDTH = 0.3 * mm
QUIET_ZONE = 3 * mm
BAR_HEIGHT = 15 * mm


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
        if symbol_width > 66 * mm:
            raise ValueError(f'El SKU {sku} no cabe en la etiqueta a 0.3 mm por módulo')

        # Price and variants occupy a fixed left column. The barcode, including
        # both quiet zones, is centred in the remaining 66 mm of the label.
        left_centre = 10 * mm
        pdf.setFillColorRGB(0, 0, 0)
        _fit_text(pdf, f'${product.precio_venta:,.0f}', left_centre, 17 * mm,
                  17 * mm, font='Helvetica-Bold', size=11)
        if product.talla:
            _fit_text(pdf, f'T: {product.talla}', left_centre, 11.5 * mm, 17 * mm)
        if product.color:
            _fit_text(pdf, product.color.nombre.upper(), left_centre, 8 * mm,
                      17 * mm, size=6.5)

        symbol_x = 22 * mm + (66 * mm - symbol_width) / 2
        bars_x = symbol_x + QUIET_ZONE
        run_start = None
        for index, bit in enumerate(modules + '0'):
            if bit == '1' and run_start is None:
                run_start = index
            elif bit == '0' and run_start is not None:
                pdf.rect(bars_x + run_start * MODULE_WIDTH, 8 * mm,
                         (index - run_start) * MODULE_WIDTH, BAR_HEIGHT,
                         fill=1, stroke=0)
                run_start = None
        _fit_text(pdf, sku, 55 * mm, 4.2 * mm, 60 * mm, size=7)
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
