from django.contrib.auth.models import User, Group
from boutique.models import Novia, Dama, Pedido, Categoria, Color, Modelo, Tela, ConfiguracionTienda
from decimal import Decimal
import datetime

# Setup basic data
admin = User.objects.get(username='admin')

# Add to group Admin
group, _ = Group.objects.get_or_create(name='Admin')
admin.groups.add(group)

ConfiguracionTienda.get_solo()

cat, _ = Categoria.objects.get_or_create(nombre='Vestidos')
col, _ = Color.objects.get_or_create(nombre='Blanco', codigo_hex='#FFFFFF')
mod, _ = Modelo.objects.get_or_create(nombre='Princesa')
tela, _ = Tela.objects.get_or_create(nombre='Seda')

novia = Novia.objects.create(
    nombre='Novia de Prueba',
    fecha_boda=datetime.date.today() + datetime.timedelta(days=30),
    creado_por=admin
)

Pedido.objects.create(
    novia=novia,
    es_vestido_novia=True,
    precio=Decimal('5000.00'),
    modelo=mod,
    color=col,
    tela=tela,
    talla='M'
)
