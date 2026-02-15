from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from ..models import (
    CorteCaja, MovimientoCaja, PagoPedido, PagoApartado,
    Ticket, Venta, Pago, MovimientoInventario
)

def get_caja_activa():
    """Obtiene la caja abierta del día actual"""
    return CorteCaja.objects.filter(cerrado=False).first()

def registrar_cobro(origen_tipo, origen_obj, monto, metodo, usuario, referencia='', notas=''):
    """
    Función maestra para registrar cualquier cobro en el sistema.
    Asegura que impacte en el documento operativo, la contabilidad de caja y genere ticket.
    """
    caja = get_caja_activa()
    if not caja:
        raise ValueError("No hay una caja abierta. Debe abrir caja antes de cobrar.")

    with transaction.atomic():
        monto = Decimal(str(monto))

        # 1. Registrar en el modelo operativo
        ticket_tipo = 'VENTA'
        if origen_tipo == 'pedido':
            PagoPedido.objects.create(
                pedido=origen_obj, monto=monto, metodo=metodo,
                referencia=referencia, registrado_por=usuario, notas=notas
            )
            ticket_tipo = 'PEDIDO'
            cliente_nombre = 'Cliente Gral.'
            if origen_obj.dama:
                cliente_nombre = origen_obj.dama.nombre
            elif origen_obj.novia:
                cliente_nombre = origen_obj.novia.nombre
            elif origen_obj.cliente:
                cliente_nombre = origen_obj.cliente.nombre
        elif origen_tipo == 'apartado':
            PagoApartado.objects.create(
                apartado=origen_obj, monto=monto, metodo=metodo,
                referencia=referencia, registrado_por=usuario, notas=notas
            )
            ticket_tipo = 'APARTADO'
            cliente_nombre = origen_obj.cliente_nombre
        elif origen_tipo == 'venta':
            # Para ventas directas desde POS, el objeto Venta ya debe existir o crearse
            Pago.objects.create(
                venta=origen_obj, monto=monto, metodo=metodo,
                registrado_por=usuario
            )
            cliente_nombre = origen_obj.cliente.nombre if origen_obj.cliente else 'Cliente General'
        else:
            raise ValueError(f"Origen de cobro no soportado: {origen_tipo}")

        # 2. Generar Movimiento de Caja
        mov = MovimientoCaja.objects.create(
            caja=caja,
            tipo=ticket_tipo,
            metodo_pago=metodo,
            monto=monto,
            referencia=referencia,
            registrado_por=usuario
        )
        if origen_tipo == 'pedido': mov.pedido = origen_obj
        if origen_tipo == 'apartado': mov.apartado = origen_obj
        if origen_tipo == 'venta': mov.venta = origen_obj

        # 3. Generar Ticket
        ticket = Ticket.objects.create(
            tipo=ticket_tipo,
            cliente_nombre=cliente_nombre,
            total=getattr(origen_obj, 'precio', getattr(origen_obj, 'total', 0)),
            total_pagado=monto, # En este ticket
            cajero_nombre=usuario.username
        )
        if origen_tipo == 'pedido': ticket.pedido = origen_obj
        if origen_tipo == 'apartado': ticket.apartado = origen_obj
        if origen_tipo == 'venta': ticket.venta = origen_obj

        # Poblar snapshot
        origen_obj.refresh_from_db()
        ticket.populate_from_obj(origen_obj)

        # Guardar folio en movimiento
        mov.ticket_folio = ticket.folio
        mov.save()

        # 4. Actualizar totales de caja (opcional si usamos @property, pero mejor persistir esperados)
        if metodo == 'EFECTIVO':
            caja.efectivo_esperado += monto
        elif metodo == 'TARJETA':
            caja.tarjeta_esperada += monto
        elif metodo == 'TRANSFERENCIA':
            caja.transferencia_esperada += monto
        caja.save()

        return ticket
