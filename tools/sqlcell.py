#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SQL прямо в ячейке тетради — без промежуточных библиотек обработки данных.

Подключение к учебной базе и вывод результата таблицей. Достаточно один раз
выполнить в тетради:

    import sys; sys.path.append("..")
    from tools.sqlcell import setup
    setup()

После этого ячейка, начинающаяся со строки `%%sql`, содержит чистый SQL и
показывает результат таблицей. Для работы в коде есть функция `rows(sql)`.
"""
from __future__ import annotations

import os
from pathlib import Path

import psycopg2
import psycopg2.extras

ROOT = Path(__file__).resolve().parent.parent
_conn = None


def _load_env() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def connection():
    """Одно соединение на всю тетрадь."""
    global _conn
    if _conn is None or _conn.closed:
        _load_env()
        _conn = psycopg2.connect(
            host=os.environ.get("PGHOST", "localhost"),
            port=int(os.environ.get("PGPORT", "5433")),
            dbname=os.environ.get("PGDATABASE", "bank_training"),
            user=os.environ.get("PGUSER", "bank_user"),
            password=os.environ.get("PGPASSWORD", "bank_pass"),
        )
        _conn.autocommit = True
    return _conn


def rows(sql: str) -> list[dict]:
    """Выполнить запрос и вернуть строки списком словарей."""
    with connection().cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql)
        if cur.description is None:
            return []
        return [dict(r) for r in cur.fetchall()]


def execute(sql: str) -> str:
    """Выполнить запрос без результата (создание представления и подобное)."""
    with connection().cursor() as cur:
        cur.execute(sql)
        return cur.statusmessage or "выполнено"


def _fmt(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "да" if value else "нет"
    if isinstance(value, int):
        return f"{value:,}".replace(",", " ")
    if isinstance(value, float):
        text = f"{value:,.2f}".rstrip("0").rstrip(".")
        return text.replace(",", " ").replace(".", ",")
    text = str(value)
    try:                                   # Decimal и прочие числовые типы
        return _fmt(float(text)) if text.replace("-", "").replace(".", "").isdigit() else text
    except ValueError:
        return text


def table(data: list[dict], limit: int = 50):
    """Показать строки таблицей."""
    from IPython.display import HTML

    if not data:
        return HTML("<i>Запрос ничего не вернул.</i>")
    cols = list(data[0].keys())
    head = "".join(f"<th style='text-align:left;padding:4px 10px'>{c}</th>" for c in cols)
    body = ""
    for r in data[:limit]:
        cells = "".join(
            f"<td style='padding:3px 10px;text-align:"
            f"{'right' if isinstance(r[c], (int, float)) and not isinstance(r[c], bool) else 'left'}'>"
            f"{_fmt(r[c])}</td>"
            for c in cols
        )
        body += f"<tr>{cells}</tr>"
    tail = "" if len(data) <= limit else \
        f"<div style='color:#777;padding-top:6px'>показаны первые {limit} из {len(data)} строк</div>"
    return HTML(
        "<table style='border-collapse:collapse;font-size:13px;font-family:system-ui'>"
        f"<thead style='border-bottom:2px solid #444'><tr>{head}</tr></thead><tbody>{body}</tbody></table>{tail}"
    )


def setup() -> None:
    """Включить ячейки `%%sql` и проверить, что база отвечает."""
    from IPython import get_ipython
    from IPython.core.magic import register_cell_magic
    from IPython.display import display

    @register_cell_magic
    def sql(line, cell):                                    # noqa: ARG001
        text = cell.strip()
        first = text.split(None, 1)[0].lower() if text else ""
        if first in {"select", "with", "table", "explain", "show"}:
            display(table(rows(text)))
        else:
            print(execute(text))

    if get_ipython() is None:
        raise RuntimeError("Ячейки `%%sql` работают только внутри тетради.")
    version = rows("SELECT current_database() AS база, version() AS версия")[0]
    print(f"База «{version['база']}» на связи: {str(version['версия']).split(',')[0]}")
    display(table(rows("SELECT table_name AS объект, table_type AS тип "
                       "FROM information_schema.tables WHERE table_schema = 'public' "
                       "ORDER BY table_type DESC, table_name")))
