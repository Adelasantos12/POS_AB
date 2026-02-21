from django.utils import timezone
from datetime import time
from ..models import CitaAgenda, Pedido, Apartado, Novia

def sync_delivery_with_agenda(entity):
    """
    Sincroniza la fecha de entrega de un Pedido, Apartado o Novia con la Agenda.
    Crea o actualiza una cita de tipo 'ENTREGA'.
    """
    delivery_date = getattr(entity, 'fecha_entrega_estimada', None)
    if not delivery_date and isinstance(entity, Novia):
        delivery_date = getattr(entity, 'fecha_entrega', None)

    notes = getattr(entity, 'notas_entrega', '')

    if not delivery_date:
        # Si no hay fecha, no hacemos nada automáticamente por ahora (el UI debe manejar el borrado si se desea)
        return None

    # Determinar el folio y cliente
    folio = getattr(entity, 'numero_ticket', getattr(entity, 'folio', 'S/N'))
    customer = "Cliente"

    if isinstance(entity, Novia):
        customer = entity.nombre
    elif isinstance(entity, Pedido):
        if entity.dama:
            customer = entity.dama.nombre
        elif entity.novia:
            customer = entity.novia.nombre
        elif entity.cliente:
            customer = entity.cliente.nombre
    elif isinstance(entity, Apartado):
        customer = entity.cliente_nombre or "Cliente"

    # Determinar saldo
    saldo = 0
    if hasattr(entity, 'saldo_pendiente'):
        saldo = entity.saldo_pendiente
    elif hasattr(entity, 'saldo'):
        saldo = entity.saldo
    elif isinstance(entity, Novia):
        saldo = entity.total_pendiente

    tipo_str = entity.__class__.__name__
    title = f"ENTREGA: {folio} - {customer} (${saldo})"
    description = f"Tipo: {tipo_str}\nFolio: {folio}\nCliente: {customer}\nSaldo: ${saldo}\nNotas: {notes}"

    # Buscar evento existente vinculado
    event = entity.agenda_evento

    if event:
        # Actualizar existente
        event.fecha = delivery_date
        event.titulo = title
        event.notas = description
        event.save()
    else:
        # Crear nuevo
        # Hora por defecto 11:00 AM para entregas si no se especifica
        event = CitaAgenda.objects.create(
            titulo=title,
            tipo='ENTREGA',
            fecha=delivery_date,
            hora_inicio=time(11, 0),
            notas=description,
            creado_por=getattr(entity, 'creado_por', None)
        )

        # Vincular back-references en CitaAgenda
        if isinstance(entity, Novia): event.novia = entity
        elif isinstance(entity, Pedido):
            event.pedido = entity
            event.novia = entity.novia # También vincular a novia si existe para visibilidad
        elif isinstance(entity, Apartado):
            event.apartado = entity
            event.novia = entity.novia # También vincular a novia si existe

        event.save()

        # Vincular evento a la entidad
        entity.agenda_evento = event
        # Usamos save(update_fields) para evitar recursion si llamamos esto desde save()
        entity.save(update_fields=['agenda_evento'])

    return event
