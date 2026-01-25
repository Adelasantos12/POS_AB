from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from boutique.models import (
    Producto, Venta, ItemVenta, Pago, Cliente, Pedido,
    Grupo, IntegranteGrupo, Categoria, Modelo, Tela, Color,
    Novia, Dama, CitaAgenda, PagoPedido, NotaPedido
)

class Command(BaseCommand):
    help = 'Configura los roles avanzados para la boutique (Caja, Inventario, Agenda, Superadmin)'

    def handle(self, *args, **options):
        # 1. Admin (Administrador con acceso a dashboards y edición)
        admin_group, _ = Group.objects.get_or_create(name='Admin')
        all_perms = Permission.objects.filter(content_type__app_label='boutique')
        admin_group.permissions.set(all_perms)
        self.stdout.write(self.style.SUCCESS('Grupo Admin configurado.'))

        # 1b. Vendedor (Acceso básico)
        vendedor_group, _ = Group.objects.get_or_create(name='Vendedor')
        self.stdout.write(self.style.SUCCESS('Grupo Vendedor configurado.'))

        # 2. Caja
        caja_group, _ = Group.objects.get_or_create(name='Caja')
        caja_models = [Venta, ItemVenta, Pago, Cliente]
        caja_perms = []
        for model in caja_models:
            ct = ContentType.objects.get_for_model(model)
            caja_perms.extend(Permission.objects.filter(content_type=ct))
        # Caja puede ver productos y añadir "producto rápido"
        prod_ct = ContentType.objects.get_for_model(Producto)
        caja_perms.extend(Permission.objects.filter(content_type=prod_ct, codename__in=['view_producto', 'add_producto']))
        caja_group.permissions.set(caja_perms)
        self.stdout.write(self.style.SUCCESS('Grupo Caja configurado.'))

        # 3. Inventario
        inv_group, _ = Group.objects.get_or_create(name='Inventario')
        inv_models = [Producto, Categoria, Modelo, Tela, Color]
        inv_perms = []
        for model in inv_models:
            ct = ContentType.objects.get_for_model(model)
            inv_perms.extend(Permission.objects.filter(content_type=ct))
        inv_group.permissions.set(inv_perms)
        self.stdout.write(self.style.SUCCESS('Grupo Inventario configurado.'))

        # 4. Agenda
        agenda_group, _ = Group.objects.get_or_create(name='Agenda')
        agenda_models = [Grupo, IntegranteGrupo, Pedido, Cliente, Novia, Dama, CitaAgenda, PagoPedido, NotaPedido]
        agenda_perms = []
        for model in agenda_models:
            ct = ContentType.objects.get_for_model(model)
            agenda_perms.extend(Permission.objects.filter(content_type=ct))
        agenda_group.permissions.set(agenda_perms)
        self.stdout.write(self.style.SUCCESS('Grupo Agenda configurado.'))
