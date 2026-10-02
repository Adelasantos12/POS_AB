from decimal import Decimal, InvalidOperation
from boutique.views import es_admin


def importe(raw, fallback=None):
    if raw is None or str(raw).strip() == '':
        return fallback
    try:
        value = Decimal(str(raw))
        if not value.is_finite() or value < 0 or value > Decimal('99999999.99') or value != value.quantize(Decimal('.01')):
            raise ValueError()
        return value
    except (InvalidOperation, ValueError):
        raise ValueError('Indica un costo válido en MXN, con hasta dos decimales; vacío significa pendiente.')


def costo_entrada(request, producto):
    # Seller-supplied values are ignored, even if sent outside the visible UI.
    return importe(request.POST.get('costo_unitario'), producto.costo_referencia) if es_admin(request.active_profile) else producto.costo_referencia
