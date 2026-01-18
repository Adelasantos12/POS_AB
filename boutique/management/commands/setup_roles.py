from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from boutique.models import Producto, Venta, Pedido, Cliente

class Command(BaseCommand):
    help = 'Configura los grupos de usuarios y sus permisos'

    def handle(self, *args, **options):
        # 1. Grupo Administrador de Tienda
        admin_group, created = Group.objects.get_or_create(name='Administrador')
        # El administrador puede hacer todo en la app boutique
        boutique_content_types = ContentType.objects.filter(app_label='boutique')
        admin_permissions = Permission.objects.filter(content_type__in=boutique_content_types)
        admin_group.permissions.set(admin_permissions)
        self.stdout.write(self.style.SUCCESS('Grupo Administrador configurado.'))

        # 2. Grupo Vendedor
        vendedor_group, created = Group.objects.get_or_create(name='Vendedor')
        # El vendedor solo puede ver productos, y gestionar ventas, pedidos y clientes
        from boutique.models import ItemVenta
        vendedor_models = [Venta, ItemVenta, Pedido, Cliente]
        vendedor_permissions = []

        for model in vendedor_models:
            ct = ContentType.objects.get_for_model(model)
            vendedor_permissions.extend(Permission.objects.filter(content_type=ct))

        # También permiso de ver productos
        prod_ct = ContentType.objects.get_for_model(Producto)
        vendedor_permissions.extend(Permission.objects.filter(content_type=prod_ct, codename__startswith='view_'))

        vendedor_group.permissions.set(vendedor_permissions)
        self.stdout.write(self.style.SUCCESS('Grupo Vendedor configurado.'))
