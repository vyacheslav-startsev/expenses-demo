def parse_amount(text: str) -> int:
    """Сумма из формы в копейки: «1250», «1 250,50», «99.9»."""
    cleaned = text.replace(" ", "").replace(" ", "").replace(",", ".")
    if not cleaned:
        raise ValueError("Укажите сумму")
    try:
        rubles, _, kop = cleaned.partition(".")
        if len(kop) > 2 or not rubles.isdigit() or (kop and not kop.isdigit()):
            raise ValueError
        value = int(rubles) * 100 + int(kop.ljust(2, "0") or 0)
    except ValueError:
        raise ValueError(f"Не понимаю сумму: {text}") from None
    if value <= 0:
        raise ValueError("Сумма должна быть больше нуля")
    return value


def format_rub(kop: int) -> str:
    """Копейки в «1 250,50 ₽», без копеек если их нет."""
    rubles, rest = divmod(kop, 100)
    whole = f"{rubles:,}".replace(",", " ")
    return f"{whole},{rest:02d} ₽" if rest else f"{whole} ₽"
