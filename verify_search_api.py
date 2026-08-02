import os
import django
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'adele_pos.settings')
django.setup()

from django.test import RequestFactory
from django.contrib.auth.models import User
from boutique.views import api_search_global
from boutique.models import Pedido, Apartado, Novia, Categoria, Color, Modelo
from datetime import date

def verify_search():
    # Setup data
    user = User.objects.first()
    mod, _ = Modelo.objects.get_or_create(nombre="Modelo Search")
    col, _ = Color.objects.get_or_create(nombre="Red")
    cat, _ = Categoria.objects.get_or_create(nombre="Dress")

    novia = Novia.objects.create(nombre="Alice Search", fecha_boda=date(2026, 12, 12))

    pedido = Pedido.objects.create(
        novia=novia,
        modelo=mod,
        color=col,
        precio=5000,
        numero_ticket="PED-TEST-123"
    )

    apartado = Apartado.objects.create(
        cliente_nombre="Bob Search",
        cliente_telefono="1234567890",
        total=2000,
        anticipo=500,
        folio="AP-TEST-456"
    )

    factory = RequestFactory()

    # Search for "Alice" (Novia and Pedido should appear)
    print("Searching for 'Alice'...")
    request = factory.get('/api/search-global/?q=Alice')
    request.user = user
    response = api_search_global(request)
    data = json.loads(response.content)

    print(f"Results: {len(data['results'])}")
    for r in data['results']:
        print(f" - {r['type']}: {r.get('label', r.get('text'))} (Customer: {r.get('customer')})")

    # Search for folio "AP-TEST"
    print("\nSearching for 'AP-TEST'...")
    request = factory.get('/api/search-global/?q=AP-TEST')
    request.user = user
    response = api_search_global(request)
    data = json.loads(response.content)

    print(f"Results: {len(data['results'])}")
    for r in data['results']:
        print(f" - {r['type']}: {r['folio']} (Balance: {r['balance']})")

    # Clean up
    pedido.delete()
    apartado.delete()
    novia.delete()
    print("\nVerification successful!")

if __name__ == "__main__":
    verify_search()
