from decimal import Decimal
from ..utils import safe_decimal
from django.db import transaction
from django.db.models import F
from django.utils import timezone
from ..models import (
    CorteCaja, MovimientoCaja, PagoPedido, PagoApartado,
    Ticket, Venta, Pago, MovimientoInventario
)

METODOS_VALIDOS = ('EFECTIVO', 'TARJETA', 'TRANSFERENCIA')

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

    monto = safe_decimal(monto)
    if monto <= 0:
        raise ValueError("El monto debe ser mayor a cero.")

    if metodo not in METODOS_VALIDOS:
        raise ValueError(f"Método de pago inválido: {metodo}")

    with transaction.atomic():
        # 1. Registrar en el modelo operativo y determinar tipo
        ticket_tipo = 'VENTA'
        mov_tipo = 'VENTA'
        cliente_nombre = 'Cliente General'
        cliente_telefono = ''

        if origen_tipo == 'pedido':
            PagoPedido.objects.create(
                pedido=origen_obj, monto=monto, metodo=metodo,
                referencia=referencia, registrado_por=usuario, notas=notas
            )
            ticket_tipo = 'PEDIDO'
            mov_tipo = 'ABONO_PEDIDO'
            if origen_obj.dama:
                cliente_nombre = origen_obj.dama.nombre
                cliente_telefono = origen_obj.dama.telefono or ''
            elif origen_obj.novia:
                cliente_nombre = origen_obj.novia.nombre
                cliente_telefono = origen_obj.novia.telefono or ''
            elif origen_obj.cliente:
                cliente_nombre = origen_obj.cliente.nombre
                cliente_telefono = origen_obj.cliente.telefono or ''

        elif origen_tipo == 'apartado':
            PagoApartado.objects.create(
                apartado=origen_obj, monto=monto, metodo=metodo,
                referencia=referencia, registrado_por=usuario, notas=notas
            )
            ticket_tipo = 'APARTADO'
            mov_tipo = 'ABONO_APARTADO'
            cliente_nombre = origen_obj.cliente_nombre
            cliente_telefono = origen_obj.cliente_telefono or ''

        elif origen_tipo == 'venta':
            Pago.objects.create(
                venta=origen_obj, monto=monto, metodo=metodo,
                registrado_por=usuario
            )
            mov_tipo = 'VENTA'
            if origen_obj.cliente:
                cliente_nombre = origen_obj.cliente.nombre
                cliente_telefono = origen_obj.cliente.telefono or ''

        else:
            raise ValueError(f"Origen de cobro no soportado: {origen_tipo}")

        # 2. Movimiento de caja (FK incluidos en create para persistirlos)
        mov_kwargs = dict(
            caja=caja, tipo=mov_tipo, metodo_pago=metodo,
            monto=monto, referencia=referencia, registrado_por=usuario
        )
        if origen_tipo == 'pedido':   mov_kwargs['pedido']   = origen_obj
        if origen_tipo == 'apartado': mov_kwargs['apartado'] = origen_obj
        if origen_tipo == 'venta':    mov_kwargs['venta']    = origen_obj
        mov = MovimientoCaja.objects.create(**mov_kwargs)

        # 3. Ticket
        origen_obj.refresh_from_db()
        origen_obj._metodo_pago_snapshot = metodo
        ticket = Ticket(
            tipo=ticket_tipo,
            cliente_nombre=cliente_nombre,
            cliente_telefono=cliente_telefono,
            total=getattr(origen_obj, 'precio', getattr(origen_obj, 'total', 0)),
            total_pagado=monto,
            cajero_nombre=usuario.username,
            caja=caja,
        )
        if origen_tipo == 'pedido':
            ticket.pedido = origen_obj
            ticket.novia  = origen_obj.novia
        elif origen_tipo == 'apartado':
            ticket.apartado = origen_obj
        elif origen_tipo == 'venta':
            ticket.venta = origen_obj
        ticket.save()
        ticket.populate_from_obj(origen_obj)

        mov.ticket_folio = ticket.folio
        mov.save(update_fields=['ticket_folio'])

        # 4. Actualizar totales de caja usando F() para evitar race condition
        if metodo == 'EFECTIVO':
            CorteCaja.objects.filter(pk=caja.pk).update(efectivo_esperado=F('efectivo_esperado') + monto)
        elif metodo == 'TARJETA':
            CorteCaja.objects.filter(pk=caja.pk).update(tarjeta_esperada=F('tarjeta_esperada') + monto)
        elif metodo == 'TRANSFERENCIA':
            CorteCaja.objects.filter(pk=caja.pk).update(transferencia_esperada=F('transferencia_esperada') + monto)

        return ticket
