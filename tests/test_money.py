import pytest

from app.money import format_rub, parse_amount


@pytest.mark.parametrize(
    "text, kop",
    [("1250", 125000), ("1 250,50", 125050), ("99.9", 9990), ("0,01", 1)],
)
def test_parse_amount(text, kop):
    assert parse_amount(text) == kop


@pytest.mark.parametrize("text", ["", "abc", "0", "-5", "1,234"])
def test_parse_amount_rejects_garbage(text):
    with pytest.raises(ValueError):
        parse_amount(text)


def test_format_rub():
    assert format_rub(125050) == "1 250,50 ₽"
    assert format_rub(6200) == "62 ₽"
