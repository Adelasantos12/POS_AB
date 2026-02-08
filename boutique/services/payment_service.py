from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from ..models import PagoPedido, Ticket, Venta, Pago, MovimientoInventario, PagoApartado

def registrar_pago_pedido(pedido, monto, metodo, usuario, notas='', referencia=''):
    """
    Registra un pago para un Pedido y genera un ticket snapshot.
    """
    with transaction.atomic():
        pago = PagoPedido.objects.create(
            pedido=pedido,
            monto=monto,
            metodo=metodo,
            referencia=referencia,
            registrado_por=usuario,
            notas=notas
        )

        # Recargar pedido para ver saldo actualizado
        pedido.refresh_from_db()

        # Generar Ticket persistente
        ticket = Ticket.objects.create(
            tipo='PEDIDO',
            pedido=pedido,
            cliente_nombre=pedido.dama.nombre if pedido.dama else pedido.novia.nombre,
            total=pedido.precio,
            total_pagado=monto,
            cajero_nombre=usuario.username
        )

        # Snapshot para el ticket
        items_data = []
        desc = f"ABONO Pedido: {pedido.numero_ticket}"
        if pedido.producto:
            desc += f" - {str(pedido.producto)}"
        elif pedido.modelo:
            desc += f" - {pedido.modelo.nombre}"

        items_data.append({
            'descripcion': desc,
            'cantidad': 1,
            'precio_unitario': float(pedido.precio),
            'subtotal': float(monto)
        })

        snapshot = {
            'folio': ticket.folio,
            'fecha': ticket.fecha_hora.isoformat(),
            'cliente': ticket.cliente_nombre,
            'total': float(pedido.precio),
            'monto_abono': float(monto),
            'total_pagado': float(pedido.total_pagado),
            'saldo_pendiente': float(pedido.saldo_pendiente),
            'metodo_pago': metodo,
            'items': items_data
        }
        ticket.snapshot_json = snapshot
        ticket.save()

        return ticket

def registrar_pago_apartado(apartado, monto, metodo, usuario, notas='', referencia=''):
    """
    Registra un pago para un Apartado y genera un ticket snapshot.
    """
    with transaction.atomic():
        pago = PagoApartado.objects.create(
            apartado=apartado,
            monto=monto,
            metodo=metodo,
            referencia=referencia,
            registrado_por=usuario,
            notas=notas
        )

        # Recargar para ver saldo actualizado
        apartado.refresh_from_db()

        # Generar Ticket
        ticket = Ticket.objects.create(
            tipo='APARTADO',
            apartado=apartado,
            cliente_nombre=apartado.cliente_nombre,
            total=apartado.total,
            total_pagado=monto,
            cajero_nombre=usuario.username
        )

        items_data = []
        for item in apartado.items.all():
            items_data.append({
                'descripcion': item.descripcion,
                'cantidad': item.cantidad,
                'precio_unitario': float(item.precio_unitario),
                'subtotal': float(item.subtotal)
            })

        snapshot = {
            'folio': ticket.folio,
            'fecha': ticket.fecha_hora.isoformat(),
            'cliente': ticket.cliente_nombre,
            'total': float(apartado.total),
            'monto_abono': float(monto),
            'total_pagado': float(apartado.anticipo),
            'saldo_pendiente': float(apartado.saldo),
            'metodo_pago': metodo,
            'items': items_data
        }
        ticket.snapshot_json = snapshot
        ticket.save()

        return ticket
