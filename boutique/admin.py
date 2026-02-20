from django.contrib import admin
from .models import Proveedor, Categoria, Modelo, Tela, Color, Producto

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
    list_select_related = ('modelo', 'tela', 'tela__proveedor', 'color')
    list_filter = ('categoria', 'modelo', 'tela', 'color', 'vendible_sin_stock')
    search_fields = ('sku', 'modelo__nombre', 'tela__nombre', 'color__nombre')
    readonly_fields = ('sku', 'fecha_creacion', 'fecha_actualizacion')
    list_editable = ('precio_venta', 'cantidad_actual', 'vendible_sin_stock')
