#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Две реализации одной операции рядом: запрос к базе и то же самое в pandas.

Памятка держится на одном обещании: обе колонки дают одинаковый результат.
Проверять это глазами бессмысленно — числа длинные, строк много, — поэтому
сравнение выполняется кодом и печатает вердикт.

Из тетради:

    import sys; sys.path.append("..")
    from tools.compare import запрос, сверить
"""
from __future__ import annotations

import pandas as pd

from tools import sqlcell


def запрос(sql: str) -> pd.DataFrame:
    """Результат SQL-запроса таблицей pandas — чтобы было с чем сравнивать."""
    return pd.DataFrame(sqlcell.rows(sql))


def таблица(имя: str = "raw_applications") -> pd.DataFrame:
    """Выгрузка целиком в память: так работают, когда данных немного.

    Числовые столбцы базы приезжают в Python объектами Decimal — точными,
    но неудобными: `round()` по такому столбцу молча ничего не делает.
    Приводим их к обычным числам, как это сделал бы `read_csv`.
    """
    df = запрос(f"SELECT * FROM {имя}")
    for c in df.columns:
        if df[c].dtype == "object":
            числа = pd.to_numeric(df[c], errors="coerce")
            if числа.notna().sum() and числа.isna().sum() == df[c].isna().sum():
                df[c] = числа.astype(float)
    return df


def _привести(df: pd.DataFrame) -> pd.DataFrame:
    """Сводим к сравнимому виду: имена столбцов не важны, важны значения.

    Числа приводим к float и округляем: база считает в numeric, pandas —
    в double, и в последнем знаке они законно расходятся.
    """
    out = df.reset_index(drop=True).copy()
    out.columns = [f"c{i}" for i in range(len(out.columns))]
    for c in out.columns:
        колонка = pd.to_numeric(out[c], errors="coerce")
        if колонка.notna().all():
            out[c] = колонка.astype(float).round(3)
        else:
            out[c] = out[c].astype(str).str.strip()
    return out


def сверить(слева: pd.DataFrame, справа: pd.DataFrame, подпись: str = "") -> bool:
    """Показать оба результата рядом и сказать, совпали ли они."""
    слева = pd.DataFrame(слева).reset_index(drop=True)
    справа = pd.DataFrame(справа).reset_index(drop=True)

    a, b = _привести(слева), _привести(справа)
    одинаково = a.shape == b.shape and a.equals(b)

    try:                                        # в тетради — две таблицы рядом
        from IPython.display import HTML, display
        стиль = ("display:flex;gap:18px;flex-wrap:wrap;align-items:flex-start;"
                 "font-size:13px")
        заголовок = ("font:700 12px system-ui;letter-spacing:.08em;"
                     "text-transform:uppercase;color:#5b6572;margin:0 0 6px")
        display(HTML(
            f'<div style="{стиль}">'
            f'<div><p style="{заголовок}">SQL</p>{слева.to_html(index=False)}</div>'
            f'<div><p style="{заголовок}">pandas</p>{справа.to_html(index=False)}</div>'
            f'</div>'))
    except ImportError:
        print(слева.to_string(index=False))
        print(справа.to_string(index=False))

    if одинаково:
        строк, столбцов = слева.shape
        print(f"✓ совпадает {подпись}: {строк} строк × {столбцов} столбцов")
        return True

    print(f"✗ расходится {подпись}: SQL {слева.shape}, pandas {справа.shape}")
    if a.shape == b.shape:
        разница = a.compare(b)
        if not разница.empty:
            print(разница.head(10).to_string())
    return False
