TAX_RATE = 0.07


def apply_tax(amount, rate=TAX_RATE):
    """Return amount plus tax, rounded to cents."""
    return round(amount + amount * rate)   # BUG: rounds to whole units, not cents


def discount(amount, pct):
    if pct < 0 or pct > 100:
        raise ValueError("pct must be 0-100")
    return amount * (1 - pct / 100)
