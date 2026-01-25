from django.contrib import admin
from .models import (
    Proveedor, Categoria, Modelo, Tela, Color, Producto, Cliente, 
    Venta, ItemVenta, Novia, Dama, Pedido, PagoPedido, CitaAgenda, NotaPedido
)

@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'email', 'telefono')
    search_fields = ('nombre', 'email')

class ItemVentaInline(admin.TabularInline):
    model = ItemVenta
    extra = 1

@admin.register(Venta)
class VentaAdmin(admin.ModelAdmin):
    list_display = ('id', 'fecha', 'vendedor', 'cliente', 'total')
    list_filter = ('fecha', 'vendedor')
    inlines = [ItemVentaInline]

@admin.register(Proveedor)
class ProveedorAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'contacto')
    search_fields = ('nombre',)

@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ('nombre',)
    search_fields = ('nombre',)

@admin.register(Modelo)
class ModeloAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'descripcion')
    search_fields = ('nombre',)

@admin.register(Tela)
class TelaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'proveedor', 'codigo_proveedor', 'es_predefinida', 'activa')
    list_filter = ('proveedor', 'es_predefinida', 'activa')
    search_fields = ('nombre', 'codigo_proveedor')

@admin.register(Color)
class ColorAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'codigo_hex', 'familia', 'es_predefinido', 'activo')
    list_filter = ('familia', 'es_predefinido', 'activo')
    search_fields = ('nombre', 'familia')

@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ('sku', 'modelo', 'tela', 'color', 'talla', 'precio_venta', 'cantidad_actual', 'vendible_sin_stock')
    list_filter = ('categoria', 'modelo', 'tela', 'color', 'vendible_sin_stock')
    search_fields = ('sku', 'modelo__nombre', 'tela__nombre', 'color__nombre')
    readonly_fields = ('sku', 'fecha_creacion', 'fecha_actualizacion')
    list_editable = ('precio_venta', 'cantidad_actual', 'vendible_sin_stock')


# ============================================================
# ADMIN PARA NOVIAS Y PEDIDOS
# ============================================================

class DamaInline(admin.TabularInline):
    model = Dama
    extra = 1

class PedidoInline(admin.TabularInline):
    model = Pedido
    extra = 0
    fields = ('numero_ticket', 'dama', 'es_vestido_novia', 'modelo', 'color', 'tela', 'talla', 'precio', 'estado', 'estado_pago')
    readonly_fields = ('numero_ticket',)

@admin.register(Novia)
class NoviaAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'fecha_boda', 'cantidad_damas', 'telefono', 'fecha_entrega')
    list_filter = ('fecha_boda',)
    search_fields = ('nombre', 'telefono', 'email')
    inlines = [DamaInline, PedidoInline]

class PagoPedidoInline(admin.TabularInline):
    model = PagoPedido
    extra = 0

class NotaPedidoInline(admin.TabularInline):
    model = NotaPedido
    extra = 0

@admin.register(Pedido)
class PedidoAdmin(admin.ModelAdmin):
    list_display = ('numero_ticket', 'novia', 'dama', 'modelo', 'color', 'talla', 'precio', 'estado', 'estado_pago', 'fecha_entrega_estimada')
    list_filter = ('estado', 'estado_pago', 'fecha_creacion')
    search_fields = ('numero_ticket', 'novia__nombre', 'dama__nombre')
    readonly_fields = ('numero_ticket', 'fecha_creacion', 'fecha_actualizacion')
    inlines = [PagoPedidoInline, NotaPedidoInline]

@admin.register(CitaAgenda)
class CitaAgendaAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'tipo', 'fecha', 'hora_inicio', 'novia', 'completada')
    list_filter = ('tipo', 'fecha', 'completada')
    search_fields = ('titulo', 'novia__nombre', 'nombre_cliente')
    date_hierarchy = 'fecha'
