from decimal import Decimal, InvalidOperation

def safe_decimal(value, default=Decimal("0")):
    """
    Convierte un valor a Decimal de forma segura.
    Maneja strings vacíos, None, comas como separadores y errores de sintaxis.
    """
    if value is None or value == "":
        return default

    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))

    # Normalizar string (quitar espacios, cambiar comas por puntos)
    val_str = str(value).strip().replace(",", ".")

    if not val_str:
        return default

    try:
        return Decimal(val_str)
    except (InvalidOperation, ValueError):
        return default
