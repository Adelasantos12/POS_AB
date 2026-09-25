"""Vector labels for the Brother QL-800's 90 × 29 mm stock."""

import barcode
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas


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
