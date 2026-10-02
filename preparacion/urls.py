from django.urls import path
from . import views, movements, inversion, operaciones
from .deletion import eliminar_modelo
from .modelos import agregar_modelo, agregar_modelos_bloque

app_name = 'preparacion'

urlpatterns = [
    path('buscar/', operaciones.buscar, name='buscar_prendas'),
    path('entradas/', operaciones.operacion, {'tipo': 'ENTRADA'}, name='entradas'),
    path('salidas/', operaciones.operacion, {'tipo': 'SALIDA'}, name='salidas'),
    path('entradas/borrador/', operaciones.borrador, {'tipo': 'ENTRADA'}, name='borrador_entrada'),
    path('salidas/borrador/', operaciones.borrador, {'tipo': 'SALIDA'}, name='borrador_salida'),
    path('inversion/referencia/', inversion.costo_referencia, name='costo_referencia'),
    path('inversion/', inversion.dashboard, name='inversion'),
    path('inversion/costo/', inversion.guardar_costo, name='guardar_costo'),
    path('inversion/analizar/', inversion.analizar, name='analizar_inversion'),
    path('modelos/fotos/', agregar_modelos_bloque, name='agregar_modelos_bloque'),
    path('modelo/nuevo/', agregar_modelo, name='agregar_modelo'),
    path('movimientos/', movements.panel, name='movimientos'),
    path('movimientos/consultar/', movements.consultar, name='consultar_pieza'),
    path('movimientos/confirmar/', movements.confirmar, name='confirmar_movimiento'),
    path('modelo/eliminar/<int:producto_id>/', eliminar_modelo, name='eliminar_modelo'),
    path('', views.inicio, name='inicio'),
    path('verificar/', views.verificar_etiqueta, name='verificar_etiqueta'),
    path('conteo/', views.pagina_conteo, name='conteo'),
    path('variante/nueva/<int:producto_id>/', views.nueva_variante, name='nueva_variante'),
    path('imprimir/<int:producto_id>/', views.imprimir_producto, name='imprimir_producto'),
    path('reimprimir/<int:producto_id>/', views.reimprimir_codigo, name='reimprimir_codigo'),
    path('variante/', views.guardar_variante, name='guardar_variante'),
    path('existente/', views.agregar_existente, name='agregar_existente'),
    path('etiquetas/<int:variante_id>/', views.emitir_etiquetas, name='emitir_etiquetas'),
    path('etiqueta/<int:pieza_id>/', views.reimprimir, name='reimprimir'),
    path('conteo/iniciar/', views.iniciar_conteo, name='iniciar_conteo'),
    path('conteo/escanear/', views.escanear, name='escanear'),
    path('recibir/', views.recibir, name='recibir'),
    path('conteo/cerrar/', views.cerrar_conteo, name='cerrar_conteo'),
]
