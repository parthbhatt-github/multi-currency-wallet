from decimal import Decimal, ROUND_HALF_UP


CURRENCY_MINOR_UNITS = {
    "JPY": 0,
    "USD": 2,
    "EUR": 2,
    "GBP": 2,
    "INR": 2,
}


def normalize_currency(currency: str) -> str:
    return currency.strip().upper()


def to_minor(amount: Decimal, currency: str) -> int:
    decimals = CURRENCY_MINOR_UNITS.get(currency, 2)
    multiplier = Decimal(10) ** decimals
    return int((amount * multiplier).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def from_minor(amount_minor: int, currency: str) -> Decimal:
    decimals = CURRENCY_MINOR_UNITS.get(currency, 2)
    divisor = Decimal(10) ** decimals
    return (Decimal(amount_minor) / divisor).quantize(Decimal(1) / divisor)


def convert_minor(amount_minor: int, source_currency: str, target_currency: str, rate: Decimal) -> int:
    amount = from_minor(amount_minor, source_currency)
    return to_minor(amount * rate, target_currency)
