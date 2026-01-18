from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # La ruta '/admin/' seguirá mostrando el panel de administración de Django.
    path('admin/', admin.site.urls),
    
    # La ruta raíz ('/') ahora será gestionada por el archivo urls.py de nuestra app 'boutique'.
    # Esto hace que nuestra app sea la página principal del sitio.
    path('', include('boutique.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
