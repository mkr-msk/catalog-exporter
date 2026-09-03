"""CLI: сбор каталога и выгрузка в Excel.

Пример:
    python main.py --pages 3 --output data/result.xlsx --delay 0.6
"""
from __future__ import annotations

import argparse
import logging
import sys

from collector import _make_session, collect_catalog
from exporter import write_report

PAGE_TEMPLATE = "https://books.toscrape.com/catalogue/page-{page}.html"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Сбор каталога в Excel-отчёт")
    parser.add_argument("--pages", type=int, default=3,
                        help="сколько страниц каталога обойти (по умолчанию 3)")
    parser.add_argument("--output", default="data/result.xlsx",
                        help="путь к итоговому Excel-файлу")
    parser.add_argument("--delay", type=float, default=0.6,
                        help="пауза между запросами, сек (вежливость к сайту)")
    parser.add_argument("--verbose", action="store_true", help="подробные логи")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    session = _make_session()
    products = collect_catalog(
        session,
        page_url=PAGE_TEMPLATE,
        pages=args.pages,
        delay=args.delay,
    )

    if not products:
        print("Товаров не собрано — проверьте сеть или селекторы.")
        return 1

    path = write_report([p.to_row() for p in products], args.output)
    print(f"Собрано товаров: {len(products)}")
    print(f"Отчёт сохранён: {path}")
    print("Пример записи:", products[0].title, "|", products[0].price, products[0].currency)
    return 0


if __name__ == "__main__":
    sys.exit(main())
