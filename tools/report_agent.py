#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Агент, который отвечает на запрос отчётом: таблицы, графики, короткий вывод.

Агент не придумывает числа: он ходит в базу инструментом `выполнить_sql`
и рисует ровно то, что вернула база. Всё, что он показал, воспроизводится
запросом — это и есть проверяемость.

Запуск из тетради:

    from tools.report_agent import отчёт
    отчёт("Сравни инициативы по окупаемости")

Запуск из командной строки (для проверки):

    python3 tools/report_agent.py "Сравни инициативы по окупаемости"
"""
from __future__ import annotations

import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import matplotlib                                            # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt                              # noqa: E402
import matplotlib.ticker as mticker                          # noqa: E402

from tools import sqlcell                                    # noqa: E402
from tools.llm import Assistant                              # noqa: E402

CHARTS = Path(__file__).resolve().parent.parent / "charts"

СХЕМА = """Учебная база банка (PostgreSQL). Доступные объекты:

Портфель инициатив:
- initiative_passport(initiative_id, name, direction, start_month, cost_rub,
  months_to_profit, months_to_payback) — паспорт инициативы: месяц старта,
  расходы, месяцев до выхода на прибыльность, месяцев до окупаемости.
- v_initiative_plan(initiative_id, name, direction, start_month, cost_rub,
  months_to_profit, months_to_payback, monthly_cost_rub, monthly_profit_rub)
- v_initiative_npv(initiative_id, name, direction, month_index, cash_flow_rub,
  discounted_rub, cum_npv_rub) — кривая NPV каждой инициативы по месяцам 0..36.
- v_portfolio_npv(month_index, cash_flow_rub, discounted_rub, cum_npv_rub) —
  сумма кривых всех инициатив, кривая портфеля.
- v_initiative_fact_vs_plan(initiative_id, name, direction, month_index,
  actual_cost_rub, actual_profit_rub, plan_cost_rub, plan_profit_rub).

Кредитный конвейер:
- v_applications_clean(application_id, client_id, product, channel, region,
  amount_requested, submitted_at, source_system)
- v_stage_events_clean(event_id, application_id, stage, entered_at, left_at, hours)
- raw_decisions(application_id, decision, decided_at, reason)

Все суммы в рублях. Месяцы — целые числа от начала портфеля."""

СИСТЕМА = f"""Ты аналитик банка. Отвечаешь на запрос коротким отчётом.

Правила:
- Числа берёшь только из базы через инструмент `run_sql`. Ничего не выдумывай
  и не отвечай по памяти: первым действием всегда вызывай `run_sql`.
- Если для ответа нужен график — строй его инструментом `make_chart`.
- Точные значения — месяц перехода через ноль, максимум, доля — считай отдельным
  запросом с условием и сортировкой, а не на глаз по таблице.
- Диалект SQL — PostgreSQL. В запросах для графиков давай столбцам понятные
  русские псевдонимы через AS: они станут подписями осей.
- Построенный график читатель уже видит: не вставляй в текст ссылки на файлы
  и разметку картинок, просто ссылайся на него словами.
- Отчёт делай коротким: что видно в данных, потом что с этим делать.
  Без вступлений вида «отличный вопрос» и без пересказа собственных действий.
- Если данных для вывода не хватает, скажи об этом прямо.

{СХЕМА}"""

ИНСТРУМЕНТЫ = [
    {
        "name": "run_sql",
        "description": "Выполнить SELECT в учебной базе и получить строки результата",
        "parameters": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "SQL-запрос SELECT"}},
            "required": ["query"],
        },
    },
    {
        "name": "make_chart",
        "description": ("Построить график по результату SQL-запроса и показать его в отчёте. "
                        "Типы: line — динамика по месяцам, bar — сравнение объектов, "
                        "barh — сравнение с длинными подписями."),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "SQL-запрос, дающий данные графика"},
                "kind": {"type": "string", "enum": ["line", "bar", "barh"],
                         "description": "тип графика"},
                "title": {"type": "string", "description": "заголовок графика на русском языке"},
                "x": {"type": "string", "description": "столбец для горизонтальной оси"},
                "y": {"type": "string", "description": "столбец со значениями"},
                "series": {"type": "string", "description": "столбец разбивки на линии, необязательный"},
            },
            "required": ["query", "kind", "title", "x", "y"],
        },
    },
]


def _в_тетради() -> bool:
    try:
        from IPython import get_ipython
        return get_ipython() is not None and "IPKernelApp" in get_ipython().config
    except Exception:
        return False


def _число(v):
    return float(v) if v is not None else None


def _масштаб(values) -> tuple[float, str]:
    """Крупные суммы переводим в миллионы — иначе подписи оси нечитаемы."""
    предел = max((abs(v) for v in values if v is not None), default=0)
    return (1_000_000.0, ", млн ₽") if предел >= 1_000_000 else (1.0, "")


def _график(запрос: str, тип: str, заголовок: str, x: str, y: str, серия: str | None = None):
    строки = sqlcell.rows(запрос)
    if not строки:
        return {"ошибка": "запрос ничего не вернул, график не построен"}
    for столбец in (x, y):
        if столбец not in строки[0]:
            return {"ошибка": f"в результате запроса нет столбца «{столбец}», "
                              f"есть: {', '.join(строки[0])}"}

    CHARTS.mkdir(exist_ok=True)
    fig, ax = plt.subplots(figsize=(9, 4.6), dpi=130)
    делитель, подпись_единиц = _масштаб([_число(r[y]) for r in строки])

    if тип == "line":
        группы: dict = {}
        for r in строки:
            ключ = str(r[серия]) if серия and серия in r else ""
            группы.setdefault(ключ, []).append((r[x], _число(r[y]) / делитель))
        for ключ, точки in группы.items():
            точки.sort(key=lambda p: p[0])
            ax.plot([p[0] for p in точки], [p[1] for p in точки],
                    linewidth=2, label=ключ or None)
        if len(группы) > 1:
            ax.legend(fontsize=8, ncol=2)
        ax.axhline(0, color="#999", linewidth=0.8)
    else:
        подписи = [str(r[x]) for r in строки]
        значения = [_число(r[y]) / делитель for r in строки]
        if тип == "barh":
            ax.barh(подписи[::-1], значения[::-1], color="#2f6f4e")
        else:
            ax.bar(подписи, значения, color="#2f6f4e")
            if max((len(s) for s in подписи), default=0) > 8:
                plt.setp(ax.get_xticklabels(), rotation=30, ha="right")

    # Подписываем оси только человеческими названиями: если ассистент оставил
    # служебное имя столбца, подпись не помогает, а мешает.
    def читаемое(имя: str) -> str:
        понятно = any("а" <= c.lower() <= "я" or c == "ё" for c in имя)
        return имя if понятно else ""

    if тип == "barh":
        ax.set_xlabel(читаемое(y) and f"{читаемое(y)}{подпись_единиц}")
        ax.set_ylabel(читаемое(x))
    else:
        ax.set_xlabel(читаемое(x))
        ax.set_ylabel(читаемое(y) and f"{читаемое(y)}{подпись_единиц}")
    if тип != "barh":                      # у горизонтальных столбцов ось Y — подписи
        ax.yaxis.set_major_locator(mticker.MaxNLocator(nbins=6, integer=делитель == 1))
    ax.set_title(заголовок, fontsize=12, pad=12)
    ax.grid(axis="y" if тип != "barh" else "x", alpha=0.25)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()

    путь = CHARTS / f"{abs(hash(заголовок)) % 10 ** 8}.png"
    fig.savefig(путь)
    plt.close(fig)
    if _в_тетради():                       # в тетради показываем сразу
        from IPython.display import Image, display
        display(Image(filename=str(путь)))
    # Путь к файлу ассистенту не отдаём: получив его, он вставляет в отчёт
    # ссылку на картинку с локальным путём — она никуда не ведёт.
    return {"построен": заголовок, "точек": len(строки), "показан_пользователю": True}


def отчёт(запрос: str, показывать_шаги: bool = True, model: str | None = None) -> str | None:
    """Ответить на запрос отчётом. Возвращает текст отчёта."""
    ассистент = Assistant(model=model)
    журнал = (lambda s: print(s)) if показывать_шаги else (lambda s: None)

    def вызов(имя: str, аргументы: dict):
        if имя == "run_sql":
            строки = sqlcell.rows(аргументы["query"])
            журнал(f"     строк получено: {len(строки)}")
            return строки[:200]
        if имя == "make_chart":
            return _график(
                аргументы["query"], аргументы.get("kind", "bar"),
                аргументы.get("title", "График"), аргументы["x"], аргументы["y"],
                аргументы.get("series"),
            )
        return {"ошибка": f"инструмента «{имя}» нет"}

    журнал(f"Запрос: {запрос}\n")
    текст, _ = ассистент.run(
        [{"role": "system", "content": СИСТЕМА}, {"role": "user", "content": запрос}],
        ИНСТРУМЕНТЫ, вызов, log=журнал, force_first="run_sql",
    )
    if _в_тетради():
        from IPython.display import Markdown, display
        display(Markdown(текст))
        return None                        # текст уже показан, не дублируем
    print("\n" + "\n".join(textwrap.fill(s, 100) for s in текст.split("\n")))
    return текст


if __name__ == "__main__":
    отчёт(" ".join(sys.argv[1:]) or "Когда портфель инициатив выходит в плюс?")
