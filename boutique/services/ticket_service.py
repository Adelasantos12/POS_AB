from django.conf import settings
from ..models import Ticket, ConfiguracionTienda
import json
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
import qrcode

def generate_pdf_ticket(ticket_id):
    """Genera un PDF de respaldo para el ticket con formato térmico"""
    ticket = Ticket.objects.get(id=ticket_id)
    config = ConfiguracionTienda.get_solo()
    buffer = BytesIO()

    # Ancho típico de 80mm (aprox 3.15 pulgadas)
    width = 3.15 * inch
    # Altura dinámica o larga
    height = 12 * inch

    p = canvas.Canvas(buffer, pagesize=(width, height))
    p.setFont("Helvetica-Bold", 10)

    y = height - 0.5 * inch

    # Encabezado
    p.drawCentredString(width/2, y, config.nombre_comercial)
    y -= 0.2 * inch
    p.setFont("Helvetica", 8)
    if config.razon_social:
        p.drawCentredString(width/2, y, config.razon_social)
        y -= 0.15 * inch
    p.drawCentredString(width/2, y, config.direccion)
    y -= 0.15 * inch
    p.drawCentredString(width/2, y, f"Tel/WhatsApp: {config.telefono_whatsapp}")
    y -= 0.3 * inch

    # Identificación
    p.setFont("Helvetica-Bold", 12)
    p.drawCentredString(width/2, y, f"FOLIO: {ticket.folio}")
    y -= 0.2 * inch
    p.setFont("Helvetica", 8)
    p.drawCentredString(width/2, y, f"TIPO: {ticket.get_tipo_display()}")
    y -= 0.15 * inch
    p.drawCentredString(width/2, y, f"Fecha: {ticket.fecha_hora.strftime('%d/%m/%Y %H:%M')}")
    y -= 0.3 * inch

    # Cliente
    if ticket.cliente_nombre:
        p.drawString(0.2 * inch, y, f"Cliente: {ticket.cliente_nombre}")
        y -= 0.2 * inch

    # Detalle de Items
    p.setFont("Helvetica-Bold", 8)
    p.drawString(0.2 * inch, y, "Cant")
    p.drawString(0.6 * inch, y, "Descripción")
    p.drawRightString(width - 0.2 * inch, y, "Total")
    y -= 0.1 * inch
    p.line(0.2 * inch, y, width - 0.2 * inch, y)
    y -= 0.2 * inch

    snapshot = ticket.snapshot_json or {}
    items = snapshot.get('items', [])

    p.setFont("Helvetica", 8)
    for item in items:
        p.drawString(0.2 * inch, y, str(item['cantidad']))

        # Descripción multilínea si es necesario
        desc = item['descripcion']
        if item.get('color') or item.get('talla'):
            desc += f" ({item.get('color', '')} / {item.get('talla', '')})"

        p.drawString(0.6 * inch, y, desc[:30])
        p.drawRightString(width - 0.2 * inch, y, f"${item['subtotal']:.2f}")
        y -= 0.15 * inch
        if len(desc) > 30:
            p.drawString(0.6 * inch, y, desc[30:60])
            y -= 0.15 * inch

    y -= 0.1 * inch
    p.line(0.2 * inch, y, width - 0.2 * inch, y)
    y -= 0.2 * inch

    # Totales y Pagos
    p.setFont("Helvetica-Bold", 10)
    p.drawString(0.6 * inch, y, "TOTAL:")
    p.drawRightString(width - 0.2 * inch, y, f"${ticket.total:.2f}")
    y -= 0.2 * inch

    p.setFont("Helvetica", 8)
    p.drawString(0.6 * inch, y, "Pagado en este ticket:")
    p.drawRightString(width - 0.2 * inch, y, f"${ticket.total_pagado:.2f}")
    y -= 0.15 * inch

    total_acumulado = snapshot.get('total_pagado', ticket.total_pagado)
    saldo = snapshot.get('saldo_pendiente', ticket.total - ticket.total_pagado)

    p.drawString(0.6 * inch, y, "Total Pagado Acum.:")
    p.drawRightString(width - 0.2 * inch, y, f"${total_acumulado:.2f}")
    y -= 0.15 * inch

    if saldo > 0:
        p.setFont("Helvetica-Bold", 9)
        p.drawString(0.6 * inch, y, "SALDO PENDIENTE:")
        p.drawRightString(width - 0.2 * inch, y, f"${saldo:.2f}")
        y -= 0.2 * inch

    # QR Code
    try:
        qr = qrcode.QRCode(version=1, box_size=2, border=1)
        qr.add_data(ticket.folio)
        qr.make(fit=True)
        img_qr = qr.make_image(fill='black', back_color='white')

        qr_buffer = BytesIO()
        img_qr.save(qr_buffer, format='PNG')
        qr_buffer.seek(0)

        from reportlab.lib.utils import ImageReader
        p.drawImage(ImageReader(qr_buffer), (width - 1*inch)/2, y - 1*inch, width=1*inch, height=1*inch)
        y -= 1.2 * inch
    except Exception as e:
        print(f"Error generando QR: {e}")

    # Políticas
    p.setFont("Helvetica-Oblique", 7)
    politicas = config.politica_apartados if ticket.tipo == 'APARTADO' else config.politica_cambios
    lines = politicas.split('\n')
    for line in lines:
        if line.strip():
            p.drawCentredString(width/2, y, line.strip()[:50])
            y -= 0.12 * inch

    p.showPage()
    p.save()

    buffer.seek(0)
    return buffer

def generate_escpos_data(ticket_id):
    """Genera comandos binarios ESC/POS para la impresora"""
    ticket = Ticket.objects.get(id=ticket_id)
    config = ConfiguracionTienda.get_solo()

    from escpos.printer import Dummy
    d = Dummy()

    d.set(align='center', bold=True)
    d.text(f"{config.nombre_comercial}\n")
    d.set(align='center', bold=False)
    if config.razon_social:
        d.text(f"{config.razon_social}\n")
    d.text(f"{config.direccion}\n")
    d.text(f"Tel/WhatsApp: {config.telefono_whatsapp}\n\n")

    d.set(align='center', bold=True, width=2, height=2)
    d.text(f"{ticket.folio}\n")
    d.set(align='center', bold=False, width=1, height=1)
    d.text(f"TIPO: {ticket.get_tipo_display()}\n")
    d.text(f"Fecha: {ticket.fecha_hora.strftime('%d/%m/%Y %H:%M')}\n")
    d.text("-" * 32 + "\n")

    if ticket.cliente_nombre:
        d.text(f"Cliente: {ticket.cliente_nombre}\n")

    snapshot = ticket.snapshot_json or {}
    items = snapshot.get('items', [])
    for item in items:
        desc = item['descripcion']
        if item.get('color') or item.get('talla'):
            desc += f" ({item.get('color', '')}/{item.get('talla', '')})"

        d.text(f"{item['cantidad']} x {desc[:25]}\n")
        d.text(f"      ${item['subtotal']:>22.2f}\n")

    d.text("-" * 32 + "\n")
    d.set(bold=True)
    d.text(f"TOTAL: ${ticket.total:>22.2f}\n")
    d.set(bold=False)
    d.text(f"Pagado ahora: ${ticket.total_pagado:>18.2f}\n")

    total_acum = snapshot.get('total_pagado', ticket.total_pagado)
    saldo = snapshot.get('saldo_pendiente', ticket.total - ticket.total_pagado)

    d.text(f"Total pagado: ${total_acum:>18.2f}\n")
    if saldo > 0:
        d.set(bold=True)
        d.text(f"SALDO PEND:   ${saldo:>18.2f}\n")
        d.set(bold=False)

    d.text("\n")
    d.qr(ticket.folio, size=8)
    d.text("\n")

    politicas = config.politica_apartados if ticket.tipo == 'APARTADO' else config.politica_cambios
    d.text(f"{politicas[:200]}...\n")
    d.cut()

    return d.output
