from django.urls import path
from django.contrib.auth import views as auth_views
from . import views
from . import views_agenda
from . import views_apartados

urlpatterns = [
    # Rutas principales
    path('', views.index, name='index'),
    path('health/', views.health_check, name='health_check'),
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
    path('api/venta-rapida/', views.api_venta_rapida, name='api_venta_rapida'),
    path('api/producto-rapido/', views.api_crear_producto_rapido, name='api_crear_producto_rapido'),
    path('api/check-duplicados/', views.api_check_duplicados, name='api_check_duplicados'),
    path('api/validar-crear-producto/', views.api_validar_crear_producto, name='api_validar_crear_producto'),
    path('api/ai-extract-attributes/', views.api_ai_extract_attributes, name='api_ai_extract_attributes'),
    path('api/ai-analyze-image/', views.api_ai_analyze_image, name='api_ai_analyze_image'),
    path('api/search-productos/', views.api_search_productos, name='api_search_productos'),
    path('api/search-global/', views.api_search_global, name='api_search_global'),
    path('api/editar-entrega/<str:tipo>/<int:pk>/', views.api_editar_entrega, name='api_editar_entrega'),
    path('api/search-clientes/', views.api_search_clientes, name='api_search_clientes'),
    path('api/search-novias/', views_agenda.api_search_novias, name='api_search_novias'),
    path('api/novia/<int:novia_id>/damas/', views_agenda.api_get_damas_novia, name='api_get_damas_novia'),
    path('api/registrar-venta/', views.api_registrar_venta, name='api_registrar_venta'),
    path('api/sync/', views.api_sync, name='api_sync'),

    # Inventario
    path('inventario/', views.inventario_view, name='inventario_view'),
    path('inventario/pendientes/', views.pendientes_regularizacion, name='pendientes_regularizacion'),
    path('inventario/subida-bloque/', views.subida_bloque, name='subida_bloque'),
    path('api/subida-bloque/', views.api_subida_bloque, name='api_subida_bloque'),
    path('api/producto-editar/<int:pk>/', views.api_editar_producto, name='api_editar_producto'),
    path('api/producto-clonar-variante/<int:pk>/', views.api_clonar_variante, name='api_clonar_variante'),
    path('api/producto-variantes/<int:pk>/', views.api_get_variantes, name='api_get_variantes'),
    path('api/producto-regularizar/<int:pk>/', views.api_producto_regularizar, name='api_producto_regularizar'),
    path('api/producto-eliminar/<int:pk>/', views.api_eliminar_producto, name='api_eliminar_producto'),
    path('api/producto-foto/<int:pk>/', views.api_foto_producto, name='api_foto_producto'),
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
    path('api/color-editar/<int:pk>/', views_agenda.api_color_editar, name='api_color_editar'),
    path('api/color-eliminar/<int:pk>/', views_agenda.api_color_eliminar, name='api_color_eliminar'),
    path('api/crear-tela/', views_agenda.api_crear_tela, name='api_crear_tela'),
    path('api/tela-editar/<int:pk>/', views_agenda.api_tela_editar, name='api_tela_editar'),
    path('api/tela-eliminar/<int:pk>/', views_agenda.api_tela_eliminar, name='api_tela_eliminar'),
    
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
    path('api/novia/<int:pk>/editar/', views_agenda.api_editar_novia, name='api_editar_novia'),
    path('api/novia/<int:pk>/eliminar/', views_agenda.api_eliminar_novia, name='api_eliminar_novia'),
    path('api/crear-novia/', views_agenda.api_crear_novia, name='api_crear_novia'),
    path('api/novia/<int:novia_id>/agregar-dama/', views_agenda.api_agregar_dama, name='api_agregar_dama'),
    path('api/dama/<int:pk>/editar/', views_agenda.api_editar_dama, name='api_editar_dama'),
    path('api/dama/<int:pk>/eliminar/', views_agenda.api_eliminar_dama, name='api_eliminar_dama'),
    path('api/pedido/crear/', views_agenda.api_crear_pedido, name='api_crear_pedido'),
    path('api/pedido/crear-completo/', views_agenda.api_crear_pedido_completo, name='api_crear_pedido_completo'),
    path('api/pedido/<int:pk>/liquidar/', views.api_liquidar_pedido, name='api_liquidar_pedido'),
    path('api/cobrar/<str:tipo>/<int:pk>/', views.api_cobrar_item, name='api_cobrar_item'),
    path('api/pedido/<int:pedido_id>/medidas/', views.api_guardar_medidas, name='api_guardar_medidas'),
    path('api/pedido/<int:pedido_id>/medidas/reutilizar/', views.api_obtener_medidas_reutilizar, name='api_obtener_medidas_reutilizar'),
    path('api/entregar/<str:tipo>/<int:pk>/', views.api_entregar_item, name='api_entregar_item'),
    path('api/llego-a-tienda/<str:tipo>/<int:pk>/', views.api_llego_a_tienda, name='api_llego_a_tienda'),
    path('api/pedido/<int:pk>/estado/', views.api_cambiar_estado_pedido, name='api_cambiar_estado_pedido'),

    # Tickets e Impresión
    path('api/tickets/<str:folio>/detalle/', views.api_ticket_detalle, name='api_ticket_detalle'),
    path('api/tickets/<str:folio>/pdf/', views.print_ticket_pdf, name='print_ticket_pdf'),
    path('api/tickets/<str:folio>/escpos/', views.get_ticket_escpos, name='get_ticket_escpos'),

    # Apartados independientes
    path('apartados/', views_apartados.lista_apartados, name='lista_apartados'),
    path('apartados/<int:pk>/', views_apartados.detalle_apartado, name='detalle_apartado'),
    path('api/apartado/crear/', views_apartados.api_crear_apartado, name='api_crear_apartado'),
    path('api/apartado/editar/<int:pk>/', views_apartados.api_apartado_editar, name='api_apartado_editar'),
    
    # Servicios y ajustes
    path('servicios/', views.servicios_list, name='servicios_list'),
    path('api/servicio/crear/', views.api_crear_servicio, name='api_crear_servicio'),
    path('api/servicio/<int:pk>/cobrar/', views.api_cobrar_servicio, name='api_cobrar_servicio'),
    path('api/servicio/<int:pk>/estado/', views.api_cambiar_estado_servicio, name='api_cambiar_estado_servicio'),
    path('api/servicio/<int:pk>/eliminar/', views.api_eliminar_servicio, name='api_eliminar_servicio'),

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
    path('importar-excel/', views.importar_excel, name='importar_excel'),

    # Clientes
    path('clientes/<int:pk>/', views.cliente_detalle, name='cliente_detalle'),

    # Gestión de Usuarios
    path('usuarios/', views.gestion_usuarios, name='gestion_usuarios'),
    path('usuarios/editar/<int:pk>/', views.editar_usuario, name='editar_usuario'),
    path('usuarios/resetear-password/<int:pk>/', views.resetear_password, name='resetear_password'),
    path('usuarios/historial/<int:pk>/', views.historial_usuario, name='historial_usuario'),
]
