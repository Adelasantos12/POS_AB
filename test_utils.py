from decimal import Decimal
from boutique.utils import safe_decimal

def test_safe_decimal():
    assert safe_decimal("10.5") == Decimal("10.5")
    assert safe_decimal("10,5") == Decimal("10.5")
    assert safe_decimal("") == Decimal("0")
    assert safe_decimal(None) == Decimal("0")
    assert safe_decimal("abc") == Decimal("0")
    assert safe_decimal(" 10.5 ") == Decimal("10.5")
    assert safe_decimal("10.5", default=None) == Decimal("10.5")
    assert safe_decimal("", default=None) is None
    # If someone sends 1.234,56 -> becomes 1.234.56 -> invalid -> 0
    assert safe_decimal("1.234,56") == Decimal("0")
    print("All safe_decimal tests passed!")

if __name__ == "__main__":
    test_safe_decimal()
