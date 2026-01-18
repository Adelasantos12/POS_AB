from django.contrib import admin
from .models import Proveedor, Categoria, Modelo, Tela, Color, Producto, Cliente, Venta, ItemVenta, Pedido

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

@admin.register(Pedido)
class PedidoAdmin(admin.ModelAdmin):
    list_display = ('id', 'cliente', 'producto', 'cantidad', 'estado', 'fecha_pedido')
    list_filter = ('estado', 'fecha_pedido')
    search_fields = ('cliente__nombre', 'producto__modelo__nombre')

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
    list_display = ('nombre', 'proveedor', 'codigo_proveedor')
    list_filter = ('proveedor',)
    search_fields = ('nombre', 'codigo_proveedor')

@admin.register(Color)
class ColorAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'codigo_hex')
    search_fields = ('nombre',)

@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ('sku', 'modelo', 'tela', 'color', 'talla', 'precio_venta', 'cantidad_actual', 'vendible_sin_stock')
    list_filter = ('categoria', 'modelo', 'tela', 'color', 'vendible_sin_stock')
    search_fields = ('sku', 'modelo__nombre', 'tela__nombre', 'color__nombre')
    readonly_fields = ('sku', 'fecha_creacion', 'fecha_actualizacion')
    list_editable = ('precio_venta', 'cantidad_actual', 'vendible_sin_stock')
