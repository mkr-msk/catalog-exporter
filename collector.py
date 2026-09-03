"""Сбор данных каталога: выборка карточек, нормализация, обход страниц.

Модуль не привязан к конкретному сайту: селекторы и шаблон URL страниц
объявлены константами — адаптация под целевой каталог сводится к их замене.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/151.0 Safari/537.36"
    ),
}

# Единственное место, которое правится под целевой каталог.
SELECTORS = {
    "card": "article.product_pod",
    "title": "h3 a",
    "price": "p.price_color",
    "rating": "p.star-rating",
}

RATING_ORDER = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}


class CatalogError(RuntimeError):
    """Ошибка сбора данных каталога (сетевые и структурные)."""


@dataclass
class Product:
    """Нормализованная запись о товаре каталога."""

    title: str
    price: float | None
    currency: str
    rating: int
    url: str

    def to_row(self) -> list:
        return [self.title, self.price, self.currency, self.rating, self.url]


def _make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    return session


def _apply_encoding(resp: requests.Response) -> None:
    """Если сервер не отдал charset в заголовке — определяем его по содержимому."""
    content_type = resp.headers.get("Content-Type", "").lower()
    if "charset" not in content_type:
        resp.encoding = resp.apparent_encoding or "utf-8"


def fetch_page(session: requests.Session, url: str, *, timeout: int = 15,
               retries: int = 3, backoff: float = 1.0) -> str:
    """Скачать страницу с повторами на временные ошибки.

    Возвращает HTML. Финальный 4xx/5xx или исчерпание попыток -> CatalogError.
    """
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            resp = session.get(url, timeout=timeout)
        except requests.RequestException as exc:
            last_error = exc
            logger.warning("Запрос %s: попытка %s/%s (%s)", url, attempt, retries, exc)
        else:
            if resp.status_code == 200:
                _apply_encoding(resp)
                return resp.text
            if resp.status_code in (429, 500, 502, 503, 504):
                last_error = CatalogError(f"HTTP {resp.status_code} на {url}")
                logger.warning("HTTP %s на %s, попытка %s/%s",
                               resp.status_code, url, attempt, retries)
            else:
                raise CatalogError(f"HTTP {resp.status_code} на {url}")
        if attempt < retries:
            time.sleep(backoff * attempt)
    raise CatalogError(f"Не удалось получить {url}: {last_error}")


def parse_price(raw: str | None) -> tuple[float | None, str]:
    """Разобрать цену вида '£51.77', '1 234,56 ₽' в (число, символ валюты)."""
    if not raw:
        return None, ""
    text = raw.strip()
    currency = re.sub(r"[0-9.,\s]", "", text)
    body = re.sub(r"[^\d.,]", "", text)  # только цифры, точка и запятая
    if "," in body and "." in body:
        # старший разделитель запятая -> европейский формат: точки-тысячи, запятая-десятичная
        if body.rfind(",") > body.rfind("."):
            body = body.replace(".", "").replace(",", ".")
        else:  # запятая — разделитель тысяч
            body = body.replace(",", "")
    elif "," in body:
        body = body.replace(",", ".")
    elif body.count(".") > 1:  # несколько точек -> разделители тысяч
        body = body.replace(".", "")
    try:
        return float(body), currency
    except ValueError:
        return None, currency


def parse_rating(element) -> int:
    """Класс 'star-rating Three' -> рейтинг 3 (0, если не распознан)."""
    if element is None:
        return 0
    classes = element.get("class") or []
    for token in classes:
        if token in RATING_ORDER:
            return RATING_ORDER[token]
    return 0


def _resolve_url(page_url: str, href: str) -> str:
    """Превратить href в абсолютный URL относительно страницы, на которой он найден."""
    if href.startswith("http"):
        return href
    return urljoin(page_url, href)


def parse_products(html: str, page_url: str) -> list[Product]:
    """Извлечь товары из HTML-страницы каталога.

    page_url — URL страницы, из которой взят HTML; нужен для разрешения ссылок.
    """
    soup = BeautifulSoup(html, "lxml")
    products: list[Product] = []
    for card in soup.select(SELECTORS["card"]):
        title_el = card.select_one(SELECTORS["title"])
        if title_el is None:
            continue
        title = " ".join((title_el.get("title") or title_el.get_text(" ", strip=True)).split())
        price_el = card.select_one(SELECTORS["price"])
        price, currency = parse_price(price_el.get_text(" ", strip=True) if price_el else None)
        rating = parse_rating(card.select_one(SELECTORS["rating"]))
        url = _resolve_url(page_url, title_el.get("href", ""))
        products.append(Product(title=title, price=price, currency=currency,
                                rating=rating, url=url))
    return products


def collect_catalog(session: requests.Session, page_url: str, pages: int, *,
                    delay: float = 0.6, timeout: int = 15) -> list[Product]:
    """Обойти страницы каталога и вернуть уникальные товары.

    page_url — шаблон с плейсхолдером {page} (нумерация с 1).
    """
    seen: dict[str, Product] = {}
    for page in range(1, pages + 1):
        url = page_url.format(page=page)
        html = fetch_page(session, url, timeout=timeout)
        found = parse_products(html, page_url=url)
        for product in found:
            seen.setdefault(product.url, product)
        logger.info("Страница %s/%s: найдено %s (всего уникальных %s)",
                    page, pages, len(found), len(seen))
        if page < pages:
            time.sleep(delay)
    return list(seen.values())
