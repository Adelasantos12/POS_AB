from django.conf import settings
from ..models import Ticket, ConfiguracionTienda
import json
import logging
from decimal import Decimal
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
import qrcode

logger = logging.getLogger(__name__)


def _assert_items_match_total(ticket, items):
    """
    Invariant: Σ(líneas impresas) == ticket.total.
    Raises AssertionError in DEBUG so the discrepancy surfaces immediately.
    In production it logs a warning and continues.
    """
    if not items:
        return
    items_sum = sum(Decimal(str(item.get('subtotal', 0))) for item in items)
    t_total = Decimal(str(ticket.total))
    if abs(items_sum - t_total) > Decimal('0.05'):
        msg = (
            f"[Ticket {ticket.folio}] Σ(items)={items_sum} ≠ ticket.total={t_total}. "
            "A service or line is printed but not summed into the total."
        )
        if settings.DEBUG:
            raise AssertionError(msg)
        logger.warning(msg)


def _get_live_financial_data(ticket):
    """
    Return (total_acum, saldo, abonos) from live DB records.
    Falls back to snapshot_json if the linked object has been deleted.
    """
    from ..models import Apartado, Pedido, Servicio

    snapshot = ticket.snapshot_json or {}
    total_acum = None
    saldo = None
    abonos_live = None

    try:
        if ticket.apartado_id:
            ap = Apartado.objects.get(pk=ticket.apartado_id)
            total_acum = float(ap.anticipo)
            # Derive saldo from ticket.total (includes bundled services) not ap.saldo
            # (ap.total only reflects the product, not services appended to the ticket).
            saldo = max(0.0, float(ticket.total) - total_acum)
            abonos_live = [
                {'fecha': p.fecha.isoformat(), 'monto': float(p.monto), 'metodo': p.metodo}
                for p in ap.pagos_apartado.order_by('fecha', 'id')
            ]
        elif ticket.pedido_id:
            ped = Pedido.objects.get(pk=ticket.pedido_id)
            total_acum = float(ped.total_pagado)
            saldo = float(ped.saldo_pendiente)
            abonos_live = [
                {'fecha': p.fecha.isoformat(), 'monto': float(p.monto), 'metodo': p.metodo}
                for p in ped.pagos_pedido.order_by('fecha', 'id')
            ]
        elif ticket.servicio_id:
            srv = Servicio.objects.get(pk=ticket.servicio_id)
            total_acum = float(srv.total_pagado)
            saldo = float(srv.saldo_pendiente)
            abonos_live = [
                {'fecha': p.fecha.isoformat(), 'monto': float(p.monto), 'metodo': p.metodo}
                for p in srv.pagos_servicio.order_by('fecha', 'id')
            ]
    except Exception:
        pass  # object deleted — fall back to snapshot

    if total_acum is None:
        total_acum = snapshot.get('total_pagado_acumulado', float(ticket.total_pagado))
    if saldo is None:
        saldo = snapshot.get('saldo_pendiente', float(ticket.total - ticket.total_pagado))
    if abonos_live is None:
        abonos_live = snapshot.get('abonos', [])

    return total_acum, saldo, abonos_live


def generate_pdf_ticket(ticket_id):
    """Genera un PDF de respaldo para el ticket con formato térmico 80mm"""
    ticket = Ticket.objects.get(id=ticket_id)
    config = ConfiguracionTienda.get_solo()
    buffer = BytesIO()

    width = 3.15 * inch
    height = 15 * inch

    p = canvas.Canvas(buffer, pagesize=(width, height))
    y = height - 0.5 * inch

    # ── Logo ─────────────────────────────────────────────────
    if config.logo:
        try:
            from reportlab.lib.utils import ImageReader
            from PIL import Image as PILImage
            try:
                logo_reader = ImageReader(config.logo.path)
                pil_img = PILImage.open(config.logo.path)
            except (NotImplementedError, FileNotFoundError):
                import urllib.request
                raw = urllib.request.urlopen(config.logo.url, timeout=5).read()
                img_buf = BytesIO(raw)
                logo_reader = ImageReader(img_buf)
                img_buf.seek(0)
                pil_img = PILImage.open(img_buf)
            logo_w = min(2.4 * inch, width - 0.3 * inch)
            logo_h = logo_w * (pil_img.size[1] / pil_img.size[0])
            p.drawImage(logo_reader, (width - logo_w) / 2, y - logo_h,
                        width=logo_w, height=logo_h, preserveAspectRatio=True, mask='auto')
            y -= logo_h + 0.12 * inch
        except Exception as _logo_err:
            pass  # Si falla, continuar sin logo

    # ── Encabezado ──────────────────────────────────────────
    r, g, b = config.receipt_rgb
    p.setFillColorRGB(r, g, b)
    if not config.logo:
        p.setFont("Helvetica-Bold", 14)
        p.drawCentredString(width / 2, y, config.nombre_comercial)
        y -= 0.25 * inch
    p.setFillColorRGB(0, 0, 0)
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
    novia_obj = ticket.novia  # puede ser None si se desvinculó
    if novia_obj or novia_nombre:
        nombre_grupo = novia_obj.nombre if novia_obj else novia_nombre
        p.setFont("Helvetica-Bold", 8)
        p.drawString(0.2 * inch, y, f"Grupo novia: {nombre_grupo}")
        p.setFont("Helvetica", 8)
        y -= 0.15 * inch
        if novia_obj:
            if novia_obj.fecha_boda:
                p.drawString(0.2 * inch, y, f"Boda: {novia_obj.fecha_boda.strftime('%d/%m/%Y')}")
                y -= 0.14 * inch
            if novia_obj.fecha_prueba:
                p.drawString(0.2 * inch, y, f"Prueba: {novia_obj.fecha_prueba.strftime('%d/%m/%Y')}")
                y -= 0.14 * inch
            if novia_obj.fecha_entrega:
                p.drawString(0.2 * inch, y, f"Entrega: {novia_obj.fecha_entrega.strftime('%d/%m/%Y')}")
                y -= 0.14 * inch
    if dama_nombre:
        p.drawString(0.2 * inch, y, f"Para: {dama_nombre}")
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

    # ── Notas de operación (POS directo) ────────────────────
    notas_op = snapshot.get('notas_operacion', '')
    if notas_op:
        p.setFont("Helvetica-Bold", 8)
        p.drawString(0.2 * inch, y, "Notas:")
        y -= 0.13 * inch
        p.setFont("Helvetica", 7)
        for chunk in [notas_op[i:i+45] for i in range(0, min(len(notas_op), 180), 45)]:
            p.drawString(0.25 * inch, y, chunk)
            y -= 0.12 * inch
        p.setFont("Helvetica", 8)

    # ── Notas / Especificaciones de pedido ───────────────────
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
    largo_aprox = ''
    if ticket.pedido:
        try:
            m = ticket.pedido.medidas
            p.setFont("Helvetica-Bold", 8)
            p.drawString(0.2 * inch, y, "Medidas:")
            y -= 0.14 * inch
            p.setFont("Helvetica", 7)
            largo_aprox = str(m.largo_aproximado or '')
            med1 = f"B:{m.busto or '-'} Cin:{m.cintura or '-'} Cad:{m.cadera or '-'} Largo:{largo_aprox or '-'}"
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

    # Fallback: largo_aprox desde snapshot (ventas directas sin pedido)
    if not largo_aprox:
        largo_aprox = str(snapshot.get('largo_aprox', ''))

    # ── Largo aprox + aviso de bastilla ──────────────────────
    # Solo mostramos si se capturó el largo (implica venta de vestido)
    if largo_aprox:
        items = snapshot.get('items', [])
        tiene_bastilla = any(
            'bastilla' in (item.get('descripcion', '') + item.get('modelo', '')).lower()
            for item in items
        )
        y -= 0.03 * inch
        p.setFont("Helvetica-Bold", 7.5)
        p.drawString(0.2 * inch, y, f"Largo aprox: {largo_aprox} cm")
        y -= 0.13 * inch
        if not tiene_bastilla:
            p.setFont("Helvetica-Oblique", 7)
            p.drawString(0.2 * inch, y, "* Sin bastilla — se cotiza por separado")
            y -= 0.12 * inch
        p.setFont("Helvetica", 8)

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
    _assert_items_match_total(ticket, items)
    p.setFont("Helvetica", 8)
    for item in items:
        desc = item['descripcion']
        p.drawString(0.2 * inch, y, str(item['cantidad']))
        p.drawString(0.6 * inch, y, desc[:25])
        p.drawRightString(width - 0.2 * inch, y, f"${item['subtotal']:.2f}")
        y -= 0.15 * inch
        if len(desc) > 25:
            p.drawString(0.6 * inch, y, desc[25:55])
            y -= 0.15 * inch
        if len(desc) > 55:
            p.drawString(0.6 * inch, y, desc[55:85])
            y -= 0.15 * inch
        # Detail line: SKU + modelo + color + talla
        detail_parts = []
        if item.get('sku'):    detail_parts.append(item['sku'])
        if item.get('modelo'): detail_parts.append(item['modelo'])
        if item.get('color'):  detail_parts.append(item['color'])
        if item.get('talla'):  detail_parts.append(f"T:{item['talla']}")
        if detail_parts:
            p.setFont("Helvetica", 7)
            p.drawString(0.6 * inch, y, "  " + "  ".join(detail_parts)[:44])
            p.setFont("Helvetica", 8)
            y -= 0.13 * inch
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

    total_acum, saldo, abonos_live = _get_live_financial_data(ticket)

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
    abonos = abonos_live
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

    # ── QR: Instagram (cliente) + Uso interno (boutique) ────
    try:
        from reportlab.lib.utils import ImageReader

        _ig_url = "https://www.instagram.com/adele.boutique1?utm_source=qr"
        qr_ig = qrcode.QRCode(version=1, box_size=2, border=1)
        qr_ig.add_data(_ig_url)
        qr_ig.make(fit=True)
        buf_ig = BytesIO()
        qr_ig.make_image(fill='black', back_color='white').save(buf_ig, format='PNG')
        buf_ig.seek(0)

        _base = (config.site_url or '').rstrip('/')
        _qr_interno = f"{_base}/scan/{ticket.folio}/" if _base else ticket.folio
        qr_int = qrcode.QRCode(version=1, box_size=2, border=1)
        qr_int.add_data(_qr_interno)
        qr_int.make(fit=True)
        buf_int = BytesIO()
        qr_int.make_image(fill='black', back_color='white').save(buf_int, format='PNG')
        buf_int.seek(0)

        qr_size = 1.2 * inch
        gap = (width - 2 * qr_size) / 3
        x_ig  = gap
        x_int = gap * 2 + qr_size

        p.setFont("Helvetica", 5.5)
        p.drawCentredString(x_ig  + qr_size / 2, y, "Síguenos en IG")
        p.drawCentredString(x_int + qr_size / 2, y, "Uso interno boutique")
        y -= 0.1 * inch

        p.drawImage(ImageReader(buf_ig),  x_ig,  y - qr_size, width=qr_size, height=qr_size)
        p.drawImage(ImageReader(buf_int), x_int, y - qr_size, width=qr_size, height=qr_size)
        y -= qr_size + 0.08 * inch

        p.setFont("Helvetica-Oblique", 5.5)
        p.drawCentredString(x_ig  + qr_size / 2, y, "@adele.boutique1")
        p.drawCentredString(x_int + qr_size / 2, y, "Info del pedido")
        y -= 0.15 * inch
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
    d.set(align='center', bold=True, width=2, height=2)
    d.text(f"{config.nombre_comercial[:15]}\n")
    d.set(align='center', bold=False, width=1, height=1)
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

    # ── Notas de operación (POS directo) ────────────────────
    notas_op = snapshot.get('notas_operacion', '')
    if notas_op:
        d.set(bold=True)
        d.text("Notas:\n")
        d.set(bold=False)
        d.text(f"{notas_op[:200]}\n")

    # ── Notas / Especificaciones de pedido ───────────────────
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
    _assert_items_match_total(ticket, items)
    for item in items:
        desc = item['descripcion']
        d.text(f"{item['cantidad']} x {desc[:40]}\n")
        if len(desc) > 40:
            d.text(f"   {desc[40:80]}\n")
        # Detail line: SKU + modelo + color + talla
        detail_parts = []
        if item.get('sku'):    detail_parts.append(item['sku'])
        if item.get('modelo'): detail_parts.append(item['modelo'])
        if item.get('color'):  detail_parts.append(item['color'])
        if item.get('talla'):  detail_parts.append(f"T:{item['talla']}")
        if detail_parts:
            d.text(f"   {'  '.join(detail_parts)[:46]}\n")
        if item.get('cantidad', 1) > 1 and item.get('precio_unitario'):
            d.text(f"  ${item['precio_unitario']:.2f} c/u  ${item['subtotal']:>12.2f}\n")
        else:
            d.text(f"  ${item['subtotal']:>30.2f}\n")

    d.text("-" * 32 + "\n")

    # ── Totales ──────────────────────────────────────────────
    d.set(bold=True)
    d.text(f"TOTAL:        ${ticket.total:>18.2f}\n")
    d.set(bold=False)
    d.text(f"Pagado ahora: ${ticket.total_pagado:>18.2f}\n")

    total_acum, saldo, abonos_live = _get_live_financial_data(ticket)
    d.text(f"Total pagado: ${total_acum:>18.2f}\n")
    if saldo > 0:
        d.set(bold=True)
        d.text(f"SALDO PEND:   ${saldo:>18.2f}\n")
        d.set(bold=False)
        d.text("Liquida el saldo al recoger.\n")

    # ── Historial de pagos ───────────────────────────────────
    abonos = abonos_live
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

    # ── QR Instagram (cliente) ───────────────────────────────
    try:
        d.set(align='center', bold=False)
        d.text("- Siguenos en Instagram -\n")
        d.qr("https://www.instagram.com/adele.boutique1?utm_source=qr", size=6)
        d.text("@adele.boutique1\n")
    except Exception:
        pass

    # ── QR uso interno boutique ──────────────────────────────
    try:
        d.text("\n-- PARA USO INTERNO DE LA BOUTIQUE --\n")
        _base = (config.site_url or '').rstrip('/')
        _qr_interno = f"{_base}/scan/{ticket.folio}/" if _base else ticket.folio
        d.qr(_qr_interno, size=7)
        d.text("SKU · Pedido · Info interna\n")
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
