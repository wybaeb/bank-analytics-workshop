#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Агент, который собирает дашборд в системе BI по описанию словами.

Разница с предыдущей тетрадью принципиальная. Там ассистент отвечал картинкой,
которая живёт до закрытия ноутбука. Здесь он создаёт постоянные объекты: карточки
с SQL и дашборд, на который можно дать ссылку команде.

Инструменты агента повторяют то, что человек делает руками в интерфейсе:
  create_dashboard — создать пустой дашборд
  create_card      — создать карточку-вопрос из SQL и выбрать тип отображения
  add_card         — положить карточку на дашборд

Запуск из тетради:

    from tools.dashboard_agent import собрать_дашборд
    собрать_дашборд("Дашборд портфеля инициатив: кривая NPV портфеля, ...")

Из командной строки:

    python3 tools/dashboard_agent.py "Дашборд портфеля инициатив: ..."
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.llm import Assistant, load_env                    # noqa: E402
from tools.report_agent import СХЕМА                         # noqa: E402

load_env()

MB_URL = os.environ.get("MB_URL", "http://localhost:3000")
MB_USER = os.environ.get("MB_USER", "workshop@example.local")
MB_PASS = os.environ.get("MB_PASS", "WorkshopBI2026!")
DB_LABEL = os.environ.get("MB_DB_NAME", "Учебная база банка")

SESSION = requests.Session()
_состояние: dict = {"db_id": None, "раскладка": {}}


# ------------------------------------------------------------------ доступ

def войти() -> None:
    ответ = SESSION.post(f"{MB_URL}/api/session",
                         json={"username": MB_USER, "password": MB_PASS}, timeout=60)
    ответ.raise_for_status()
    SESSION.headers.update({"X-Metabase-Session": ответ.json()["id"]})


def _id_базы() -> int:
    if _состояние["db_id"] is None:
        данные = SESSION.get(f"{MB_URL}/api/database", timeout=60).json()
        список = данные["data"] if isinstance(данные, dict) else данные
        подходящие = [d for d in список if d.get("name") == DB_LABEL] or \
                     [d for d in список if d.get("engine") == "postgres"]
        if not подходящие:
            raise RuntimeError(f"Источник «{DB_LABEL}» не подключён. Запустите ./run.sh up")
        _состояние["db_id"] = подходящие[0]["id"]
    return int(_состояние["db_id"])


# -------------------------------------------------------- инструменты агента

def создать_дашборд(имя: str, описание: str = "") -> dict:
    ответ = SESSION.post(f"{MB_URL}/api/dashboard",
                         json={"name": имя, "description": описание}, timeout=60)
    if ответ.status_code >= 400:
        return {"ошибка": f"{ответ.status_code}: {ответ.text[:200]}"}
    д = ответ.json()
    return {"dashboard_id": д["id"], "имя": д["name"],
            "ссылка": f"{MB_URL}/dashboard/{д['id']}"}


def создать_карточку(имя: str, sql: str, вид: str = "table") -> dict:
    ответ = SESSION.post(f"{MB_URL}/api/card", json={
        "name": имя,
        "dataset_query": {"type": "native", "native": {"query": sql, "template-tags": {}},
                          "database": _id_базы()},
        "display": вид,
        "visualization_settings": {},
    }, timeout=120)
    if ответ.status_code >= 400:
        return {"ошибка": f"{ответ.status_code}: {ответ.text[:300]}"}
    к = ответ.json()
    _назначить_оси(к, вид)
    return {"card_id": к["id"], "имя": к["name"]}


def _назначить_оси(карточка: dict, вид: str) -> None:
    """Указать графику, какой столбец по горизонтали, а какие — значения.

    Для запроса, написанного вручную, система не всегда угадывает оси сама:
    если оба столбца числовые, карточка открывается с вопросом «какие поля
    взять для осей». Проставляем это явно.
    """
    if вид not in {"line", "bar", "area", "row", "combo"}:
        return
    столбцы = [c.get("name") for c in (карточка.get("result_metadata") or []) if c.get("name")]
    if len(столбцы) < 2:
        return
    SESSION.put(f"{MB_URL}/api/card/{карточка['id']}", json={
        "visualization_settings": {
            "graph.dimensions": столбцы[:1],
            "graph.metrics": столбцы[1:],
        }
    }, timeout=60)


def положить_на_дашборд(dashboard_id: int, card_id: int,
                        ширина: int = 12, высота: int = 6) -> dict:
    """Раскладка по сетке в 24 колонки: слева направо, с переносом на новый ряд."""
    карточки = _состояние["раскладка"].setdefault(dashboard_id, [])
    колонка = sum(к["size_x"] for к in карточки) % 24
    ряд = (sum(к["size_x"] for к in карточки) // 24) * высота
    if колонка + ширина > 24:
        колонка = 0
        ряд = max((к["row"] + к["size_y"] for к in карточки), default=0)

    карточки.append({"id": -(len(карточки) + 1), "card_id": card_id,
                     "row": ряд, "col": колонка, "size_x": ширина, "size_y": высота,
                     "parameter_mappings": [], "visualization_settings": {}})
    ответ = SESSION.put(f"{MB_URL}/api/dashboard/{dashboard_id}",
                        json={"dashcards": карточки}, timeout=120)
    if ответ.status_code >= 400:
        карточки.pop()
        return {"ошибка": f"{ответ.status_code}: {ответ.text[:300]}"}
    return {"готово": True, "карточек_на_дашборде": len(карточки)}


ИНСТРУМЕНТЫ = [
    {
        "name": "create_dashboard",
        "description": "Создать пустой дашборд. Вызывается первым, один раз.",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "название дашборда на русском"},
            "description": {"type": "string", "description": "одна строка о назначении"}},
            "required": ["name"]},
    },
    {
        "name": "create_card",
        "description": ("Создать карточку-вопрос из SQL. Виды отображения: "
                        "line — динамика, bar — сравнение, row — горизонтальные столбцы, "
                        "scalar — одно число, table — таблица."),
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "название карточки на русском"},
            "sql": {"type": "string", "description": "SQL-запрос PostgreSQL"},
            "display": {"type": "string", "enum": ["line", "bar", "row", "scalar", "table", "area", "pie"]}},
            "required": ["name", "sql", "display"]},
    },
    {
        "name": "add_card",
        "description": "Положить созданную карточку на дашборд.",
        "parameters": {"type": "object", "properties": {
            "dashboard_id": {"type": "integer"},
            "card_id": {"type": "integer"},
            "width": {"type": "integer", "description": "ширина в колонках сетки из 24, обычно 12"},
            "height": {"type": "integer", "description": "высота, обычно 6"}},
            "required": ["dashboard_id", "card_id"]},
    },
]

СИСТЕМА = f"""Ты аналитик, который собирает дашборд в BI-системе.

Порядок работы:
1. Создай дашборд инструментом create_dashboard.
2. На каждый показатель из запроса создай карточку через create_card
   и сразу положи её на дашборд через add_card.
3. Когда все карточки на месте, коротко ответь текстом: что на дашборде и
   какой вопрос закрывает каждая карточка. Ссылку не выдумывай — её подставят.

Правила:
- SQL — только PostgreSQL и только по объектам из схемы ниже.
- В карточке для динамики по месяцам сортируй по месяцу и бери тип line.
- Одно итоговое число — тип scalar, запрос возвращает ровно одну строку и один столбец.
- Столбцам давай русские псевдонимы через AS: они попадут в подписи.
- Не создавай больше карточек, чем просили.

{СХЕМА}"""


def собрать_дашборд(запрос: str, показывать_шаги: bool = True,
                    model: str | None = None) -> dict:
    """Собрать дашборд по описанию. Возвращает ссылку и список карточек."""
    войти()
    журнал = (lambda s: print(s)) if показывать_шаги else (lambda s: None)
    итог: dict = {"dashboard_id": None, "ссылка": None, "карточки": []}

    def вызов(имя: str, аргументы: dict):
        if имя == "create_dashboard":
            r = создать_дашборд(аргументы.get("name", "Дашборд"), аргументы.get("description", ""))
            if "dashboard_id" in r:
                итог["dashboard_id"] = r["dashboard_id"]
                итог["ссылка"] = r["ссылка"]
                журнал(f"     дашборд создан: {r['ссылка']}")
            return r
        if имя == "create_card":
            r = создать_карточку(аргументы["name"], аргументы["sql"], аргументы.get("display", "table"))
            if "card_id" in r:
                итог["карточки"].append(r["имя"])
                журнал(f"     карточка «{r['имя']}» ({аргументы.get('display')})")
            else:
                журнал(f"     карточка не создалась: {r['ошибка'][:120]}")
            return r
        if имя == "add_card":
            return положить_на_дашборд(
                int(аргументы["dashboard_id"]), int(аргументы["card_id"]),
                int(аргументы.get("width", 12)), int(аргументы.get("height", 6)))
        return {"ошибка": f"инструмента «{имя}» нет"}

    журнал(f"Запрос: {запрос}\n")
    текст, _ = Assistant(model=model).run(
        [{"role": "system", "content": СИСТЕМА}, {"role": "user", "content": запрос}],
        ИНСТРУМЕНТЫ, вызов, log=журнал, max_steps=20,
        force_first="create_dashboard",
    )
    итог["ответ"] = текст

    if итог["ссылка"]:
        журнал(f"\nДашборд собран: {итог['ссылка']}")
        журнал(f"Карточек: {len(итог['карточки'])} — {', '.join(итог['карточки'])}")
    if _в_тетради_ли():
        from IPython.display import Markdown, display
        display(Markdown(f"{текст}\n\n**Дашборд:** [{итог['ссылка']}]({итог['ссылка']})"
                         if итог["ссылка"] else текст))
    return итог


def _в_тетради_ли() -> bool:
    try:
        from IPython import get_ipython
        return get_ipython() is not None and "IPKernelApp" in get_ipython().config
    except Exception:
        return False


if __name__ == "__main__":
    собрать_дашборд(" ".join(sys.argv[1:]) or
                    "Дашборд портфеля инициатив: кривая накопленного NPV портфеля по месяцам, "
                    "расходы по направлениям и число инициатив одним числом")
