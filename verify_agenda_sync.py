import os
import django
from datetime import date, time

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'adele_pos.settings')
django.setup()

from boutique.models import Pedido, Novia, CitaAgenda, Color, Modelo
from boutique.services.agenda_service import sync_delivery_with_agenda
from django.contrib.auth.models import User

def verify_sync():
    # Setup data
    user = User.objects.first()
    mod, _ = Modelo.objects.get_or_create(nombre="Modelo Test")
    col, _ = Color.objects.get_or_create(nombre="Test")

    novia = Novia.objects.create(nombre="Novia Test", fecha_boda=date(2026, 12, 12))

    pedido = Pedido.objects.create(
        novia=novia,
        modelo=mod,
        color=col,
        precio=1000,
        fecha_entrega_estimada=date(2026, 11, 20),
        notas_entrega="Nota inicial"
    )

    # Verify creation
    print("Syncing initial delivery date...")
    event = sync_delivery_with_agenda(pedido)
    assert event is not None
    assert event.fecha == date(2026, 11, 20)
    assert "ENTREGA" in event.titulo
    assert "PED-" in event.titulo
    assert "Novia Test" in event.titulo
    assert "Nota inicial" in event.notas
    print(f"Created event: {event.titulo} on {event.fecha}")

    # Verify update
    print("Updating delivery date...")
    pedido.fecha_entrega_estimada = date(2026, 11, 25)
    pedido.notas_entrega = "Nota actualizada"
    event2 = sync_delivery_with_agenda(pedido)

    assert event2.id == event.id
    assert event2.fecha == date(2026, 11, 25)
    assert "Nota actualizada" in event2.notas
    print(f"Updated event: {event2.titulo} on {event2.fecha}")

    # Clean up
    pedido.delete()
    novia.delete()
    if event: event.delete()
    print("Verification successful!")

if __name__ == "__main__":
    verify_sync()
