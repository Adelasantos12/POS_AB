from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # Rutas principales
    path('', views.index, name='index'),
    path('signup/', views.signup, name='signup'),
    path('login/', auth_views.LoginView.as_view(template_name='boutique/login.html'), name='login'),
    path('logout/', views.logout_view, name='logout'),
    
    # Perfiles (estilo macOS)
    path('perfiles/', views.seleccionar_perfil, name='seleccionar_perfil'),
    path('perfiles/autenticar/', views.autenticar_perfil, name='autenticar_perfil'),
    path('perfiles/cambiar/', views.cambiar_perfil, name='cambiar_perfil'),

    # POS y Caja
    path('pos/', views.pos_dashboard, name='pos_dashboard'),
    path('caja/apertura/', views.apertura_caja, name='apertura_caja'),
    path('caja/cierre/', views.cierre_caja, name='cierre_caja'),
    
    # API de productos y ventas
    path('api/producto-rapido/', views.api_crear_producto_rapido, name='api_crear_producto_rapido'),
    path('api/check-duplicados/', views.api_check_duplicados, name='api_check_duplicados'),
    path('api/validar-crear-producto/', views.api_validar_crear_producto, name='api_validar_crear_producto'),
    path('api/search-productos/', views.api_search_productos, name='api_search_productos'),
    path('api/registrar-venta/', views.api_registrar_venta, name='api_registrar_venta'),

    # Inventario
    path('inventario/', views.inventario_view, name='inventario_view'),
    path('api/producto-editar/<int:pk>/', views.api_editar_producto, name='api_editar_producto'),
    path('api/producto-eliminar/<int:pk>/', views.api_eliminar_producto, name='api_eliminar_producto'),
    path('imprimir-etiquetas/', views.imprimir_etiquetas, name='imprimir_etiquetas'),

    # Agenda
    path('agenda/', views.agenda_view, name='agenda_view'),

    # Dashboards y Analítica
    path('dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('api/ai-strategy/', views.api_ai_strategy, name='api_ai_strategy'),
    
    # Exportaciones
    path('exportar/inventario/csv/', views.exportar_inventario_csv, name='exportar_inventario_csv'),
    path('exportar/inventario/excel/', views.exportar_inventario_excel, name='exportar_inventario_excel'),
    path('exportar/ventas/csv/', views.exportar_ventas_csv, name='exportar_ventas_csv'),
    path('exportar/ventas/pdf/', views.exportar_ventas_pdf, name='exportar_ventas_pdf'),

    # Gestión de Usuarios
    path('usuarios/', views.gestion_usuarios, name='gestion_usuarios'),
    path('usuarios/editar/<int:pk>/', views.editar_usuario, name='editar_usuario'),
    path('usuarios/resetear-password/<int:pk>/', views.resetear_password, name='resetear_password'),
    path('usuarios/historial/<int:pk>/', views.historial_usuario, name='historial_usuario'),
]
