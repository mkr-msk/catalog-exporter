"""Тесты логики сбора данных (без сети, на фикстуре HTML)."""
from pathlib import Path

from collector import parse_price, parse_products, parse_rating

FIXTURE = Path(__file__).parent / "fixtures" / "sample.html"
PAGE_URL = "https://books.toscrape.com/catalogue/page-1.html"


def test_parse_price_currency_prefix():
    assert parse_price("£51.77") == (51.77, "£")


def test_parse_price_comma_decimal():
    assert parse_price("1 234,56") == (1234.56, "")


def test_parse_price_empty():
    assert parse_price("") == (None, "")
    assert parse_price(None) == (None, "")


def test_parse_products_count_and_fields():
    html = FIXTURE.read_text(encoding="utf-8")
    products = parse_products(html, PAGE_URL)
    assert len(products) == 2

    first = products[0]
    assert first.title == "A Light in the Attic"
    assert first.price == 51.77
    assert first.currency == "£"
    assert first.rating == 3
    assert first.url == "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html"


def test_parse_rating_unknown_is_zero():
    class Fake:
        def get(self, key, default=None):
            return ["star-rating"] if key == "class" else default

    assert parse_rating(Fake()) == 0
