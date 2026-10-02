from django import template
from boutique.views import es_admin

register = template.Library()

@register.inclusion_tag('preparacion/inversion_resumen.html', takes_context=True)
def resumen_inversion(context):
    request = context['request']
    if not hasattr(request, 'active_profile') or not es_admin(request.active_profile):
        return {}
    from preparacion.inversion import resumen
    return {'inversion': resumen()}
