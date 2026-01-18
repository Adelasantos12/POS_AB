from django.urls import path
from . import views

# Este es el router a nivel de app.
# Define las rutas específicas para la app 'boutique'.
urlpatterns = [
    # La ruta raíz de esta app ('/') apuntará a la vista 'index'.
    path('', views.index, name='index'),
    path('signup/', views.signup, name='signup'),

    # POS y Caja
    path('pos/', views.pos_dashboard, name='pos_dashboard'),
    path('api/producto-rapido/', views.api_crear_producto_rapido, name='api_crear_producto_rapido'),
    path('api/check-duplicados/', views.api_check_duplicados, name='api_check_duplicados'),
    path('api/search-productos/', views.api_search_productos, name='api_search_productos'),
    path('api/registrar-venta/', views.api_registrar_venta, name='api_registrar_venta'),

    # Agenda
    path('agenda/', views.agenda_view, name='agenda_view'),
]
