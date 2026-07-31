from .models import ConfiguracionTienda


def tienda_globals(request):
    """
    Inyecta `tienda_config` (ConfiguracionTienda singleton) en todos los
    templates. Permite usar {{ tienda_config.nombre_comercial }},
    {{ tienda_config.color_primario }}, etc. desde cualquier template.
    """
    try:
        config = ConfiguracionTienda.get_solo()
    except Exception:
        from .brand_config import IDENTITY
        config = type('_FallbackConfig', (), {
            'nombre_comercial': IDENTITY['BRAND_NAME'],
            'tagline':          IDENTITY['BRAND_TAGLINE'],
            'color_primario':   IDENTITY['BRAND_PRIMARY'],
            'color_secundario': IDENTITY['BRAND_SECONDARY'],
        })()
    return {'tienda_config': config}
