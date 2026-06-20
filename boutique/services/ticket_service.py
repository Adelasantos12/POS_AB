from django.conf import settings
from ..models import Ticket, ConfiguracionTienda
import json
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
import qrcode


def generate_pdf_ticket(ticket_id):
    """Genera un PDF de respaldo para el ticket con formato térmico 80mm"""
    ticket = Ticket.objects.get(id=ticket_id)
    config = ConfiguracionTienda.get_solo()
    buffer = BytesIO()

    width = 3.15 * inch
    height = 15 * inch

    p = canvas.Canvas(buffer, pagesize=(width, height))

    y = height - 0.5 * inch

    # ── Encabezado ──────────────────────────────────────────
    p.setFont("Helvetica-Bold", 10)
    p.drawCentredString(width / 2, y, config.nombre_comercial)
    y -= 0.2 * inch
    p.setFont("Helvetica", 8)
    if config.razon_social:
        p.drawCentredString(width / 2, y, config.razon_social)
        y -= 0.15 * inch
    p.drawCentredString(width / 2, y, config.direccion)
    y -= 0.15 * inch
    p.drawCentredString(width / 2, y, f"Tel/WhatsApp: {config.telefono_whatsapp}")
    y -= 0.15 * inch
    if config.horarios:
        for line in config.horarios.split('\n')[:2]:
            if line.strip():
                p.drawCentredString(width / 2, y, line.strip()[:50])
                y -= 0.13 * inch
    y -= 0.1 * inch

    # ── Identificación ───────────────────────────────────────
    p.setFont("Helvetica-Bold", 12)
    p.drawCentredString(width / 2, y, f"FOLIO: {ticket.folio}")
    y -= 0.2 * inch
    p.setFont("Helvetica", 8)
    p.drawCentredString(width / 2, y, f"TIPO: {ticket.get_tipo_display()}")
    y -= 0.15 * inch
    p.drawCentredString(width / 2, y, f"Fecha: {ticket.fecha_hora.strftime('%d/%m/%Y %H:%M')}")
    y -= 0.25 * inch

    p.line(0.2 * inch, y, width - 0.2 * inch, y)
    y -= 0.2 * inch

    # ── Cliente ──────────────────────────────────────────────
    snapshot = ticket.snapshot_json or {}
    if ticket.cliente_nombre:
        p.drawString(0.2 * inch, y, f"Cliente: {ticket.cliente_nombre}")
        y -= 0.15 * inch
    if ticket.cliente_telefono:
        p.drawString(0.2 * inch, y, f"Tel: {ticket.cliente_telefono}")
        y -= 0.15 * inch
    if ticket.novia:
        p.drawString(0.2 * inch, y, f"Grupo: {ticket.novia.nombre}")
        y -= 0.15 * inch

    metodo = snapshot.get('metodo_pago', '')
    if metodo:
        p.drawString(0.2 * inch, y, f"Método de pago: {metodo}")
        y -= 0.15 * inch

    fecha_entrega = snapshot.get('fecha_entrega_estimada', '')
    if fecha_entrega:
        p.drawString(0.2 * inch, y, f"Fecha de entrega: {fecha_entrega}")
        y -= 0.15 * inch

    notas_entrega = snapshot.get('notas_entrega', '')
    if notas_entrega:
        p.drawString(0.2 * inch, y, f"Notas: {notas_entrega[:50]}")
        y -= 0.15 * inch

    # ── Medidas ──────────────────────────────────────────────
    if ticket.pedido:
        try:
            m = ticket.pedido.medidas
            p.setFont("Helvetica-Bold", 8)
            p.drawString(0.2 * inch, y, "Medidas:")
            y -= 0.15 * inch
            p.setFont("Helvetica", 7)
            med1 = f"Busto:{m.busto or '-'}  Cintura:{m.cintura or '-'}  Cadera:{m.cadera or '-'}  Largo:{m.largo_aproximado or '-'}"
            p.drawString(0.2 * inch, y, med1[:55])
            y -= 0.13 * inch
            secondary = [m.bajo_busto, m.largo_talle, m.hombro_pezon, m.hombro_bajo_busto]
            if any(secondary):
                med2 = f"Bajo-B:{m.bajo_busto or '-'}  L-Talle:{m.largo_talle or '-'}  H-Pez:{m.hombro_pezon or '-'}  H-BB:{m.hombro_bajo_busto or '-'}"
                p.drawString(0.2 * inch, y, med2[:55])
                y -= 0.13 * inch
        except Exception:
            pass

    y -= 0.05 * inch
    p.line(0.2 * inch, y, width - 0.2 * inch, y)
    y -= 0.15 * inch

    # ── Ítems ────────────────────────────────────────────────
    p.setFont("Helvetica-Bold", 8)
    p.drawString(0.2 * inch, y, "Cant")
    p.drawString(0.6 * inch, y, "Descripción")
    p.drawRightString(width - 0.2 * inch, y, "Total")
    y -= 0.1 * inch
    p.line(0.2 * inch, y, width - 0.2 * inch, y)
    y -= 0.18 * inch

    items = snapshot.get('items', [])
    p.setFont("Helvetica", 8)
    for item in items:
        desc = item['descripcion']
        if item.get('color') or item.get('talla'):
            desc += f" ({item.get('color', '')}/{item.get('talla', '')})"
        p.drawString(0.2 * inch, y, str(item['cantidad']))
        p.drawString(0.6 * inch, y, desc[:28])
        p.drawRightString(width - 0.2 * inch, y, f"${item['subtotal']:.2f}")
        y -= 0.15 * inch
        if len(desc) > 28:
            p.drawString(0.6 * inch, y, desc[28:56])
            y -= 0.15 * inch
        qty = item.get('cantidad', 1)
        if item.get('precio_unitario') and qty > 1:
            p.setFont("Helvetica", 7)
            p.drawString(0.6 * inch, y, f"  ${item['precio_unitario']:.2f} c/u")
            p.setFont("Helvetica", 8)
            y -= 0.13 * inch

    y -= 0.1 * inch
    p.line(0.2 * inch, y, width - 0.2 * inch, y)
    y -= 0.2 * inch

    # ── Totales ──────────────────────────────────────────────
    p.setFont("Helvetica-Bold", 10)
    p.drawString(0.6 * inch, y, "TOTAL:")
    p.drawRightString(width - 0.2 * inch, y, f"${ticket.total:.2f}")
    y -= 0.2 * inch

    p.setFont("Helvetica", 8)
    p.drawString(0.6 * inch, y, "Pagado en este ticket:")
    p.drawRightString(width - 0.2 * inch, y, f"${ticket.total_pagado:.2f}")
    y -= 0.15 * inch

    total_acum = snapshot.get('total_pagado_acumulado', float(ticket.total_pagado))
    saldo = snapshot.get('saldo_pendiente', float(ticket.total - ticket.total_pagado))

    p.drawString(0.6 * inch, y, "Total pagado acum.:")
    p.drawRightString(width - 0.2 * inch, y, f"${total_acum:.2f}")
    y -= 0.15 * inch

    if saldo > 0:
        p.setFont("Helvetica-Bold", 9)
        p.drawString(0.6 * inch, y, "SALDO PENDIENTE:")
        p.drawRightString(width - 0.2 * inch, y, f"${saldo:.2f}")
        y -= 0.2 * inch

    # ── Historial de pagos ───────────────────────────────────
    abonos = snapshot.get('abonos', [])
    if len(abonos) > 1:
        p.setFont("Helvetica-Bold", 7)
        p.drawString(0.2 * inch, y, "Historial de pagos:")
        y -= 0.13 * inch
        p.setFont("Helvetica", 7)
        for ab in abonos[-6:]:
            line = f"  {ab.get('fecha', '')[:10]}  {ab.get('metodo', '')}  ${ab.get('monto', 0):.2f}"
            p.drawString(0.2 * inch, y, line[:48])
            y -= 0.12 * inch
        y -= 0.05 * inch

    # ── QR ───────────────────────────────────────────────────
    try:
        qr = qrcode.QRCode(version=1, box_size=2, border=1)
        qr.add_data(ticket.folio)
        qr.make(fit=True)
        img_qr = qr.make_image(fill='black', back_color='white')
        qr_buf = BytesIO()
        img_qr.save(qr_buf, format='PNG')
        qr_buf.seek(0)
        from reportlab.lib.utils import ImageReader
        p.drawImage(ImageReader(qr_buf), (width - inch) / 2, y - inch, width=inch, height=inch)
        y -= 1.2 * inch
    except Exception as e:
        print(f"Error generando QR: {e}")

    # ── Política ─────────────────────────────────────────────
    p.setFont("Helvetica-Bold", 8)
    p.drawCentredString(width / 2, y, "NO CAMBIOS NI DEVOLUCIONES")
    y -= 0.18 * inch

    p.setFont("Helvetica-Oblique", 7)
    politicas = config.politica_apartados if ticket.tipo == 'APARTADO' else config.politica_cambios
    for line in politicas.split('\n'):
        if line.strip():
            p.drawCentredString(width / 2, y, line.strip()[:50])
            y -= 0.12 * inch

    p.showPage()
    p.save()
    buffer.seek(0)
    return buffer


def generate_escpos_data(ticket_id):
    """Genera comandos binarios ESC/POS para impresora térmica"""
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
    d.text(f"Tel/WhatsApp: {config.telefono_whatsapp}\n")
    if config.horarios:
        d.text(f"{config.horarios.split(chr(10))[0][:48]}\n")
    d.text("\n")

    d.set(align='center', bold=True, width=2, height=2)
    d.text(f"{ticket.folio}\n")
    d.set(align='center', bold=False, width=1, height=1)
    d.text(f"TIPO: {ticket.get_tipo_display()}\n")
    d.text(f"Fecha: {ticket.fecha_hora.strftime('%d/%m/%Y %H:%M')}\n")
    d.text("-" * 32 + "\n")

    snapshot = ticket.snapshot_json or {}

    if ticket.cliente_nombre:
        d.text(f"Cliente: {ticket.cliente_nombre}\n")
    if ticket.cliente_telefono:
        d.text(f"Tel: {ticket.cliente_telefono}\n")
    if ticket.novia:
        d.text(f"Grupo: {ticket.novia.nombre}\n")

    metodo = snapshot.get('metodo_pago', '')
    if metodo:
        d.text(f"Metodo: {metodo}\n")

    fecha_entrega = snapshot.get('fecha_entrega_estimada', '')
    if fecha_entrega:
        d.text(f"Entrega: {fecha_entrega}\n")

    notas_entrega = snapshot.get('notas_entrega', '')
    if notas_entrega:
        d.text(f"Notas: {notas_entrega[:48]}\n")

    if ticket.pedido:
        try:
            m = ticket.pedido.medidas
            d.text(f"Medidas: B:{m.busto or '-'} C:{m.cintura or '-'} Ca:{m.cadera or '-'} L:{m.largo_aproximado or '-'}\n")
            if any([m.bajo_busto, m.largo_talle, m.hombro_pezon, m.hombro_bajo_busto]):
                d.text(f"  BB:{m.bajo_busto or '-'} LT:{m.largo_talle or '-'} HP:{m.hombro_pezon or '-'} HBB:{m.hombro_bajo_busto or '-'}\n")
        except Exception:
            pass

    d.text("-" * 32 + "\n")

    items = snapshot.get('items', [])
    for item in items:
        desc = item['descripcion']
        if item.get('color') or item.get('talla'):
            desc += f" ({item.get('color', '')}/{item.get('talla', '')})"
        d.text(f"{item['cantidad']} x {desc[:25]}\n")
        if item.get('precio_unitario') and item.get('cantidad', 1) > 1:
            d.text(f"  ${item['precio_unitario']:.2f} c/u\n")
        d.text(f"      ${item['subtotal']:>22.2f}\n")

    d.text("-" * 32 + "\n")
    d.set(bold=True)
    d.text(f"TOTAL: ${ticket.total:>22.2f}\n")
    d.set(bold=False)
    d.text(f"Pagado ahora: ${ticket.total_pagado:>18.2f}\n")

    total_acum = snapshot.get('total_pagado_acumulado', float(ticket.total_pagado))
    saldo = snapshot.get('saldo_pendiente', float(ticket.total - ticket.total_pagado))

    d.text(f"Total pagado: ${total_acum:>18.2f}\n")
    if saldo > 0:
        d.set(bold=True)
        d.text(f"SALDO PEND:   ${saldo:>18.2f}\n")
        d.set(bold=False)

    abonos = snapshot.get('abonos', [])
    if len(abonos) > 1:
        d.text("Pagos anteriores:\n")
        for ab in abonos[-6:]:
            d.text(f"  {ab.get('fecha', '')[:10]} {ab.get('metodo', '')} ${ab.get('monto', 0):.2f}\n")

    d.text("\n")
    try:
        d.qr(ticket.folio, size=8)
    except Exception:
        pass
    d.text("\n")

    d.set(bold=True)
    d.text("NO CAMBIOS NI DEVOLUCIONES\n")
    d.set(bold=False)

    politicas = config.politica_apartados if ticket.tipo == 'APARTADO' else config.politica_cambios
    d.text(f"{politicas[:200]}\n")
    d.cut()

    return d.output
