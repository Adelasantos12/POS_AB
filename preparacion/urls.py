from django.urls import path
from . import views

app_name = 'preparacion'

urlpatterns = [
    path('', views.inicio, name='inicio'),
    path('variante/', views.guardar_variante, name='guardar_variante'),
    path('existente/', views.agregar_existente, name='agregar_existente'),
    path('etiquetas/<int:variante_id>/', views.emitir_etiquetas, name='emitir_etiquetas'),
    path('etiqueta/<int:pieza_id>/', views.reimprimir, name='reimprimir'),
    path('conteo/iniciar/', views.iniciar_conteo, name='iniciar_conteo'),
    path('conteo/escanear/', views.escanear, name='escanear'),
    path('recibir/', views.recibir, name='recibir'),
    path('conteo/cerrar/', views.cerrar_conteo, name='cerrar_conteo'),
]
