from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from . import views_agenda

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
    
    # Impresión Brother QL-800
    path('api/imprimir-etiqueta/<int:pk>/', views.api_imprimir_etiqueta, name='api_imprimir_etiqueta'),
    path('api/imprimir-etiquetas-lote/', views.api_imprimir_etiquetas_lote, name='api_imprimir_etiquetas_lote'),
    path('api/preview-etiqueta/<int:pk>/', views.api_preview_etiqueta, name='api_preview_etiqueta'),
    path('api/verificar-impresora/', views.api_verificar_impresora, name='api_verificar_impresora'),

    # ============================================================
    # CATÁLOGOS
    # ============================================================
    path('catalogos/colores/', views_agenda.catalogo_colores, name='catalogo_colores'),
    path('catalogos/telas/', views_agenda.catalogo_telas, name='catalogo_telas'),
    path('api/colores/', views_agenda.api_colores_list, name='api_colores_list'),
    path('api/telas/', views_agenda.api_telas_list, name='api_telas_list'),
    path('api/crear-color/', views_agenda.api_crear_color, name='api_crear_color'),
    path('api/crear-tela/', views_agenda.api_crear_tela, name='api_crear_tela'),
    
    # ============================================================
    # AGENDA Y CALENDARIO
    # ============================================================
    path('agenda/', views_agenda.agenda_calendario, name='agenda_view'),
    path('agenda/dia/<int:year>/<int:month>/<int:day>/', views_agenda.agenda_dia, name='agenda_dia'),
    path('api/citas/', views_agenda.api_citas_rango, name='api_citas_rango'),
    path('api/crear-cita/', views_agenda.api_crear_cita, name='api_crear_cita'),
    
    # ============================================================
    # NOVIAS Y PEDIDOS
    # ============================================================
    path('novias/', views_agenda.novias_list, name='novias_list'),
    path('novias/<int:pk>/', views_agenda.novia_detalle, name='novia_detalle'),
    path('api/crear-novia/', views_agenda.api_crear_novia, name='api_crear_novia'),
    path('api/novia/<int:novia_id>/agregar-dama/', views_agenda.api_agregar_dama, name='api_agregar_dama'),
    
    # Pedidos en puerta
    path('pedidos/', views_agenda.pedidos_en_puerta, name='pedidos_en_puerta'),
    path('resumen-nocturno/', views_agenda.resumen_nocturno, name='resumen_nocturno'),

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
