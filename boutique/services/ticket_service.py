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
    p.setFont("Helvetica-Bold", 11)
    p.drawCentredString(width / 2, y, config.nombre_comercial)
    y -= 0.2 * inch
    p.setFont("Helvetica", 8)
    if config.razon_social:
        p.drawCentredString(width / 2, y, config.razon_social)
        y -= 0.15 * inch
    if config.direccion:
        p.drawCentredString(width / 2, y, config.direccion)
        y -= 0.15 * inch
    if config.telefono_whatsapp:
        tel_line = f"Tel: {config.telefono_whatsapp}"
        if config.telefono2:
            tel_line += f"  /  {config.telefono2}"
        p.drawCentredString(width / 2, y, tel_line)
        y -= 0.15 * inch
    if config.horarios:
        for line in config.horarios.split('\n')[:2]:
            if line.strip():
                p.drawCentredString(width / 2, y, line.strip()[:55])
                y -= 0.13 * inch
    y -= 0.08 * inch
    p.line(0.2 * inch, y, width - 0.2 * inch, y)
    y -= 0.15 * inch

    # ── Folio / Tipo / Fecha ─────────────────────────────────
    p.setFont("Helvetica-Bold", 12)
    p.drawCentredString(width / 2, y, f"FOLIO: {ticket.folio}")
    y -= 0.2 * inch
    p.setFont("Helvetica", 8)
    p.drawCentredString(width / 2, y, f"{ticket.get_tipo_display()}  —  {ticket.fecha_hora.strftime('%d/%m/%Y %H:%M')}")
    y -= 0.2 * inch
    p.line(0.2 * inch, y, width - 0.2 * inch, y)
    y -= 0.15 * inch

    # ── Cliente ──────────────────────────────────────────────
    snapshot = ticket.snapshot_json or {}
    if ticket.cliente_nombre:
        p.setFont("Helvetica-Bold", 8)
        p.drawString(0.2 * inch, y, f"Cliente: {ticket.cliente_nombre}")
        p.setFont("Helvetica", 8)
        y -= 0.15 * inch
    if ticket.cliente_telefono:
        p.drawString(0.2 * inch, y, f"Tel: {ticket.cliente_telefono}")
        y -= 0.15 * inch
    novia_nombre = snapshot.get('novia_nombre', '')
    dama_nombre = snapshot.get('dama_nombre', '')
    if ticket.novia or novia_nombre:
        nombre_grupo = ticket.novia.nombre if ticket.novia else novia_nombre
        p.drawString(0.2 * inch, y, f"Grupo: {nombre_grupo}")
        y -= 0.15 * inch
    if dama_nombre:
        p.drawString(0.2 * inch, y, f"Dama: {dama_nombre}")
        y -= 0.15 * inch

    metodo = snapshot.get('metodo_pago', '')
    if metodo:
        p.drawString(0.2 * inch, y, f"Pago: {metodo}")
        y -= 0.15 * inch

    # ── FECHA DE ENTREGA (prominente) ────────────────────────
    fecha_entrega = snapshot.get('fecha_entrega_estimada', '')
    if fecha_entrega:
        y -= 0.05 * inch
        p.setFont("Helvetica-Bold", 9)
        p.drawString(0.2 * inch, y, f"ENTREGA ESTIMADA: {fecha_entrega}")
        p.setFont("Helvetica", 8)
        y -= 0.18 * inch

    # ── Notas / Especificaciones ─────────────────────────────
    notas_entrega = snapshot.get('notas_entrega', '')
    if notas_entrega:
        p.setFont("Helvetica-Bold", 8)
        p.drawString(0.2 * inch, y, "Notas del pedido:")
        y -= 0.13 * inch
        p.setFont("Helvetica", 7)
        for chunk in [notas_entrega[i:i+45] for i in range(0, min(len(notas_entrega), 135), 45)]:
            p.drawString(0.25 * inch, y, chunk)
            y -= 0.12 * inch
        p.setFont("Helvetica", 8)

    # ── Medidas ──────────────────────────────────────────────
    if ticket.pedido:
        try:
            m = ticket.pedido.medidas
            p.setFont("Helvetica-Bold", 8)
            p.drawString(0.2 * inch, y, "Medidas:")
            y -= 0.14 * inch
            p.setFont("Helvetica", 7)
            med1 = f"B:{m.busto or '-'} Cin:{m.cintura or '-'} Cad:{m.cadera or '-'} Largo:{m.largo_aproximado or '-'}"
            p.drawString(0.2 * inch, y, med1[:55])
            y -= 0.12 * inch
            extras = []
            if m.bajo_busto:   extras.append(f"BB:{m.bajo_busto}")
            if m.largo_talle:  extras.append(f"LT:{m.largo_talle}")
            if m.hombro_pezon: extras.append(f"HP:{m.hombro_pezon}")
            if m.hombro_bajo_busto: extras.append(f"HBB:{m.hombro_bajo_busto}")
            if m.hombro:       extras.append(f"Hom:{m.hombro}")
            if m.brazo:        extras.append(f"Bra:{m.brazo}")
            if m.espalda:      extras.append(f"Esp:{m.espalda}")
            if extras:
                line = "  ".join(extras)
                p.drawString(0.2 * inch, y, line[:55])
                y -= 0.12 * inch
            if m.observaciones:
                p.drawString(0.2 * inch, y, f"Obs: {m.observaciones[:45]}")
                y -= 0.12 * inch
            p.setFont("Helvetica", 8)
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
    y -= 0.15 * inch

    items = snapshot.get('items', [])
    p.setFont("Helvetica", 8)
    for item in items:
        desc = item['descripcion']
        detail = []
        if item.get('color'): detail.append(item['color'])
        if item.get('talla'): detail.append(f"T:{item['talla']}")
        if detail:
            desc += f" ({'/'.join(detail)})"
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

    y -= 0.08 * inch
    p.line(0.2 * inch, y, width - 0.2 * inch, y)
    y -= 0.18 * inch

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
        p.setFillColorRGB(0.8, 0, 0)
        p.drawString(0.6 * inch, y, "SALDO PENDIENTE:")
        p.drawRightString(width - 0.2 * inch, y, f"${saldo:.2f}")
        p.setFillColorRGB(0, 0, 0)
        y -= 0.2 * inch
        p.setFont("Helvetica", 7)
        p.drawCentredString(width / 2, y, "Liquida el saldo al recoger tu pedido.")
        y -= 0.15 * inch

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

    y -= 0.05 * inch
    p.line(0.2 * inch, y, width - 0.2 * inch, y)
    y -= 0.15 * inch

    # ── Aviso importante ─────────────────────────────────────
    p.setFont("Helvetica-Bold", 8)
    p.drawCentredString(width / 2, y, "⚠  PRESENTA ESTE TICKET AL RECOGER")
    y -= 0.15 * inch
    p.setFont("Helvetica", 7)
    p.drawCentredString(width / 2, y, "Sin ticket no se entrega el pedido.")
    y -= 0.18 * inch

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
        y -= 1.15 * inch
    except Exception as e:
        print(f"Error generando QR: {e}")

    # ── Política ─────────────────────────────────────────────
    p.setFont("Helvetica-Bold", 8)
    p.drawCentredString(width / 2, y, "NO CAMBIOS NI DEVOLUCIONES")
    y -= 0.15 * inch
    p.setFont("Helvetica-Oblique", 7)
    politicas = config.politica_apartados if ticket.tipo == 'APARTADO' else config.politica_cambios
    for line in politicas.split('\n'):
        if line.strip():
            p.drawCentredString(width / 2, y, line.strip()[:55])
            y -= 0.12 * inch

    y -= 0.1 * inch
    p.setFont("Helvetica", 7)
    tel_pie = config.telefono_whatsapp
    if config.telefono2:
        tel_pie += f"  /  {config.telefono2}"
    p.drawCentredString(width / 2, y, tel_pie)
    y -= 0.12 * inch
    if config.horarios:
        p.drawCentredString(width / 2, y, config.horarios.split('\n')[0].strip()[:55])

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

    # ── Encabezado ──────────────────────────────────────────
    d.set(align='center', bold=True)
    d.text(f"{config.nombre_comercial}\n")
    d.set(align='center', bold=False)
    if config.razon_social:
        d.text(f"{config.razon_social}\n")
    if config.direccion:
        d.text(f"{config.direccion}\n")
    tel_line = config.telefono_whatsapp
    if config.telefono2:
        tel_line += f" / {config.telefono2}"
    if tel_line:
        d.text(f"Tel: {tel_line}\n")
    if config.horarios:
        d.text(f"{config.horarios.split(chr(10))[0].strip()[:48]}\n")
    d.text("-" * 32 + "\n")

    # ── Folio ────────────────────────────────────────────────
    d.set(align='center', bold=True, width=2, height=2)
    d.text(f"{ticket.folio}\n")
    d.set(align='center', bold=False, width=1, height=1)
    d.text(f"{ticket.get_tipo_display()}  —  {ticket.fecha_hora.strftime('%d/%m/%Y %H:%M')}\n")
    d.text("-" * 32 + "\n")

    snapshot = ticket.snapshot_json or {}

    # ── Cliente ──────────────────────────────────────────────
    d.set(align='left')
    if ticket.cliente_nombre:
        d.set(bold=True)
        d.text(f"Cliente: {ticket.cliente_nombre}\n")
        d.set(bold=False)
    if ticket.cliente_telefono:
        d.text(f"Tel: {ticket.cliente_telefono}\n")
    novia_nombre = snapshot.get('novia_nombre', '')
    dama_nombre = snapshot.get('dama_nombre', '')
    if ticket.novia or novia_nombre:
        d.text(f"Grupo: {ticket.novia.nombre if ticket.novia else novia_nombre}\n")
    if dama_nombre:
        d.text(f"Dama: {dama_nombre}\n")

    metodo = snapshot.get('metodo_pago', '')
    if metodo:
        d.text(f"Pago: {metodo}\n")

    # ── FECHA DE ENTREGA ─────────────────────────────────────
    fecha_entrega = snapshot.get('fecha_entrega_estimada', '')
    if fecha_entrega:
        d.set(bold=True)
        d.text(f"ENTREGA ESTIMADA: {fecha_entrega}\n")
        d.set(bold=False)

    # ── Notas / Especificaciones ─────────────────────────────
    notas_entrega = snapshot.get('notas_entrega', '')
    if notas_entrega:
        d.set(bold=True)
        d.text("Notas del pedido:\n")
        d.set(bold=False)
        d.text(f"{notas_entrega[:200]}\n")

    # ── Medidas ──────────────────────────────────────────────
    if ticket.pedido:
        try:
            m = ticket.pedido.medidas
            d.set(bold=True)
            d.text("Medidas:\n")
            d.set(bold=False)
            d.text(f"B:{m.busto or '-'} Cin:{m.cintura or '-'} Cad:{m.cadera or '-'} L:{m.largo_aproximado or '-'}\n")
            extras = []
            if m.bajo_busto:        extras.append(f"BB:{m.bajo_busto}")
            if m.largo_talle:       extras.append(f"LT:{m.largo_talle}")
            if m.hombro_pezon:      extras.append(f"HP:{m.hombro_pezon}")
            if m.hombro_bajo_busto: extras.append(f"HBB:{m.hombro_bajo_busto}")
            if m.hombro:            extras.append(f"Hom:{m.hombro}")
            if m.brazo:             extras.append(f"Bra:{m.brazo}")
            if m.espalda:           extras.append(f"Esp:{m.espalda}")
            if extras:
                d.text("  ".join(extras)[:48] + "\n")
            if m.observaciones:
                d.text(f"Obs: {m.observaciones[:48]}\n")
        except Exception:
            pass

    d.text("-" * 32 + "\n")

    # ── Ítems ────────────────────────────────────────────────
    items = snapshot.get('items', [])
    for item in items:
        desc = item['descripcion']
        detail = []
        if item.get('color'): detail.append(item['color'])
        if item.get('talla'): detail.append(f"T:{item['talla']}")
        if detail:
            desc += f" ({'/'.join(detail)})"
        d.text(f"{item['cantidad']} x {desc[:28]}\n")
        if item.get('precio_unitario') and item.get('cantidad', 1) > 1:
            d.text(f"  ${item['precio_unitario']:.2f} c/u\n")
        d.text(f"      ${item['subtotal']:>22.2f}\n")

    d.text("-" * 32 + "\n")

    # ── Totales ──────────────────────────────────────────────
    d.set(bold=True)
    d.text(f"TOTAL:        ${ticket.total:>18.2f}\n")
    d.set(bold=False)
    d.text(f"Pagado ahora: ${ticket.total_pagado:>18.2f}\n")

    total_acum = snapshot.get('total_pagado_acumulado', float(ticket.total_pagado))
    saldo = snapshot.get('saldo_pendiente', float(ticket.total - ticket.total_pagado))
    d.text(f"Total pagado: ${total_acum:>18.2f}\n")
    if saldo > 0:
        d.set(bold=True)
        d.text(f"SALDO PEND:   ${saldo:>18.2f}\n")
        d.set(bold=False)
        d.text("Liquida el saldo al recoger.\n")

    # ── Historial de pagos ───────────────────────────────────
    abonos = snapshot.get('abonos', [])
    if len(abonos) > 1:
        d.text("Pagos anteriores:\n")
        for ab in abonos[-6:]:
            d.text(f"  {ab.get('fecha','')[:10]} {ab.get('metodo','')} ${ab.get('monto',0):.2f}\n")

    d.text("-" * 32 + "\n")

    # ── Aviso ────────────────────────────────────────────────
    d.set(align='center', bold=True)
    d.text("PRESENTA ESTE TICKET AL RECOGER\n")
    d.set(bold=False)
    d.text("Sin ticket no se entrega el pedido.\n\n")

    try:
        d.qr(ticket.folio, size=8)
    except Exception:
        pass
    d.text("\n")

    # ── Política ─────────────────────────────────────────────
    d.set(bold=True)
    d.text("NO CAMBIOS NI DEVOLUCIONES\n")
    d.set(bold=False)
    politicas = config.politica_apartados if ticket.tipo == 'APARTADO' else config.politica_cambios
    d.text(f"{politicas[:200]}\n")

    # ── Teléfonos al pie ─────────────────────────────────────
    tel_pie = config.telefono_whatsapp
    if config.telefono2:
        tel_pie += f" / {config.telefono2}"
    d.text(f"{tel_pie}\n")
    if config.horarios:
        d.text(f"{config.horarios.split(chr(10))[0].strip()[:48]}\n")

    d.cut()
    return d.output
