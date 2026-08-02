import unicodedata
from decimal import Decimal, InvalidOperation


def quitar_acentos(s: str) -> str:
    """Remove combining accent marks from a string via NFD decomposition."""
    return ''.join(
        c for c in unicodedata.normalize('NFD', s)
        if unicodedata.category(c) != 'Mn'
    )


def normalizar_nombre(s: str) -> str:
    """Canonical form for catalog names: strip whitespace, remove accents, title-case."""
    if not s:
        return s
    return quitar_acentos(s.strip()).title()


def nombres_son_iguales(a: str, b: str) -> bool:
    """Case- and accent-insensitive equality check for catalog names."""
    return normalizar_nombre(a).lower() == normalizar_nombre(b).lower()


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
