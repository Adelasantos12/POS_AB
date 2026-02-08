from django.conf import settings
from .models import Ticket, ConfiguracionTienda
import json
from io import BytesIO
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.units import inch

def generate_pdf_ticket(ticket_id):
    """Genera un PDF de respaldo para el ticket"""
    ticket = Ticket.objects.get(id=ticket_id)
    config = ConfiguracionTienda.get_solo()
    buffer = BytesIO()

    p = canvas.Canvas(buffer, pagesize=(3 * inch, 10 * inch)) # Tamaño aproximado de cinta térmica
    p.setFont("Helvetica-Bold", 10)

    y = 9.5 * inch
    p.drawCentredString(1.5 * inch, y, config.nombre_comercial)
    y -= 0.2 * inch
    p.setFont("Helvetica", 8)
    p.drawCentredString(1.5 * inch, y, config.direccion)
    y -= 0.15 * inch
    p.drawCentredString(1.5 * inch, y, f"Tel: {config.telefono_whatsapp}")
    y -= 0.3 * inch

    p.setFont("Helvetica-Bold", 12)
    p.drawCentredString(1.5 * inch, y, f"FOLIO: {ticket.folio}")
    y -= 0.2 * inch
    p.setFont("Helvetica", 8)
    p.drawCentredString(1.5 * inch, y, f"Fecha: {ticket.fecha_hora.strftime('%d/%m/%Y %H:%M')}")
    y -= 0.3 * inch

    # Items
    p.drawString(0.2 * inch, y, "Cant")
    p.drawString(0.6 * inch, y, "Descripción")
    p.drawRightString(2.8 * inch, y, "Total")
    y -= 0.15 * inch
    p.line(0.2 * inch, y, 2.8 * inch, y)
    y -= 0.2 * inch

    snapshot = ticket.snapshot_json or {}
    items = snapshot.get('items', [])

    for item in items:
        p.drawString(0.2 * inch, y, str(item['cantidad']))
        desc = item['descripcion'][:25]
        p.drawString(0.6 * inch, y, desc)
        p.drawRightString(2.8 * inch, y, f"${item['subtotal']:.2f}")
        y -= 0.15 * inch

    y -= 0.2 * inch
    p.line(0.2 * inch, y, 2.8 * inch, y)
    y -= 0.2 * inch

    p.setFont("Helvetica-Bold", 10)
    p.drawString(0.6 * inch, y, "TOTAL:")
    p.drawRightString(2.8 * inch, y, f"${ticket.total:.2f}")
    y -= 0.3 * inch

    # Políticas
    p.setFont("Helvetica-Oblique", 6)
    lines = config.politica_cambios.split('\n')
    for line in lines[:5]: # Mostrar solo primeras 5 líneas
        p.drawCentredString(1.5 * inch, y, line)
        y -= 0.1 * inch

    p.showPage()
    p.save()

    buffer.seek(0)
    return buffer

def generate_escpos_data(ticket_id):
    """Genera comandos binarios ESC/POS para la impresora"""
    # En un entorno real sin impresora física conectada al servidor web,
    # esto retornaría los comandos para que el cliente (POS) los imprima.
    ticket = Ticket.objects.get(id=ticket_id)
    config = ConfiguracionTienda.get_solo()

    # Simulación simple de comandos ESC/POS como texto o binario
    # Aquí podríamos usar la librería python-escpos para generar el buffer
    from escpos.printer import Dummy
    d = Dummy()

    d.set(align='center', bold=True)
    d.text(f"{config.nombre_comercial}\n")
    d.set(align='center', bold=False)
    d.text(f"{config.direccion}\n")
    d.text(f"Tel: {config.telefono_whatsapp}\n\n")

    d.set(align='center', bold=True, width=2, height=2)
    d.text(f"{ticket.folio}\n\n")
    d.set(align='center', bold=False, width=1, height=1)

    d.text(f"Fecha: {ticket.fecha_hora.strftime('%d/%m/%Y %H:%M')}\n")
    d.text("-" * 32 + "\n")

    snapshot = ticket.snapshot_json or {}
    items = snapshot.get('items', [])
    for item in items:
        d.text(f"{item['cantidad']} x {item['descripcion'][:20]}\n")
        d.text(f"      ${item['subtotal']:>22.2f}\n")

    d.text("-" * 32 + "\n")
    d.set(bold=True)
    d.text(f"TOTAL: ${ticket.total:>22.2f}\n\n")

    d.set(align='center', bold=False)
    d.text(f"{config.politica_cambios[:100]}...\n")
    d.cut()

    return d.output
