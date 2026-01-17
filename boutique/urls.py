from django.urls import path
from . import views

# Este es el router a nivel de app.
# Define las rutas específicas para la app 'boutique'.
urlpatterns = [
    # La ruta raíz de esta app ('/') apuntará a la vista 'index'.
    path('', views.index, name='index'),
]
