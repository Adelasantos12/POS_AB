from django import template

register = template.Library()

@register.filter
def get_item(dictionary, key):
    """Obtener item de diccionario por clave"""
    if dictionary is None:
        return None
    return dictionary.get(key)

@register.filter
def mul(value, arg):
    """Multiplicar valor por argumento"""
    try:
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0
