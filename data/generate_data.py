#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Генератор учебных наборов данных для практики.

Данные синтетические. Зерно фиксировано, поэтому повторный запуск даёт
побайтово те же файлы — их можно держать в репозитории и сверять.

    python3 data/generate_data.py

Три набора:
  cards/     — выгрузка по выданным картам для практики в таблицах (сырая, с дефектами)
  pipeline/  — кредитный конвейер для практики в SQL (сырая, с дефектами)
  portfolio/ — паспорта инициатив и факт по месяцам для портфельной практики
"""
from __future__ import annotations

import csv
import random
from datetime import date, datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
SEED = 20260816

# ---------------------------------------------------------------- утилиты


def write_csv(path: Path, header: list[str], rows: list[list], delimiter: str = ";",
              bom: bool = False) -> None:
    """bom=True — файл открывают в табличном редакторе, ему нужна метка кодировки.
    Файлы, которые грузит база, пишем без метки: COPY читает её как часть имени поля."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig" if bom else "utf-8", newline="") as f:
        w = csv.writer(f, delimiter=delimiter, quoting=csv.QUOTE_MINIMAL)
        w.writerow(header)
        w.writerows(rows)
    print(f"  {path.relative_to(BASE.parent)}: {len(rows)} строк")


def money_ru(value: float, rnd: random.Random) -> str:
    """Одна и та же сумма в разных начертаниях — так и приходит выгрузка."""
    style = rnd.random()
    if style < 0.45:
        return f"{value:,.0f}".replace(",", " ")
    if style < 0.75:
        return f"{value:.2f}".replace(".", ",")
    return f"{value:.2f}"


def date_ru(d: date, rnd: random.Random) -> str:
    return d.strftime("%d.%m.%Y") if rnd.random() < 0.7 else d.isoformat()


# ------------------------------------------------- набор 1: карточный бизнес

CHANNEL_VARIANTS = {
    "Отделение": ["Отделение", "отделение", "ОТДЕЛЕНИЕ", "Отделение ", "Офис банка"],
    "Мобильное приложение": ["Мобильное приложение", "мобильное приложение", "Мобильный банк", "МП"],
    "Сайт банка": ["Сайт банка", "сайт банка", "Веб-сайт"],
    "Партнёрская сеть": ["Партнёрская сеть", "Партнерская сеть", "партнёрская сеть", "Партнёр"],
}
TARIFFS = ["Классический", "Премиальный", "Зарплатный", "Кэшбэк-максимум"]
REGIONS = ["Центральный", "Северо-Западный", "Приволжский", "Сибирский", "Южный"]

# доля карт, по которым покупка происходит в первые 30 дней
ACTIVATION_BASE = {
    "Отделение": 0.62,
    "Мобильное приложение": 0.74,
    "Сайт банка": 0.58,
    "Партнёрская сеть": 0.31,   # проседание, которое участник должен найти
}
TARIFF_SHIFT = {
    "Классический": 0.0,
    "Премиальный": 0.06,
    "Зарплатный": 0.11,
    "Кэшбэк-максимум": -0.04,
}


def gen_cards(n: int = 2400) -> None:
    rnd = random.Random(SEED)
    start = date(2025, 1, 13)
    rows: list[list] = []

    for i in range(n):
        canon_channel = rnd.choices(
            list(CHANNEL_VARIANTS), weights=[0.32, 0.34, 0.16, 0.18]
        )[0]
        channel = rnd.choice(CHANNEL_VARIANTS[canon_channel])
        tariff = rnd.choices(TARIFFS, weights=[0.42, 0.14, 0.28, 0.16])[0]
        region = rnd.choices(REGIONS, weights=[0.3, 0.18, 0.2, 0.16, 0.16])[0]
        issued = start + timedelta(days=rnd.randint(0, 200))
        limit = rnd.choice([50_000, 75_000, 100_000, 150_000, 200_000, 300_000, 500_000])

        p = ACTIVATION_BASE[canon_channel] + TARIFF_SHIFT[tariff]
        activated = rnd.random() < max(0.05, min(0.95, p))

        if activated:
            first_purchase = issued + timedelta(days=rnd.randint(0, 29))
            turnover30 = rnd.uniform(0.08, 0.55) * limit
            turnover90 = turnover30 * rnd.uniform(1.6, 3.4)
        elif rnd.random() < 0.22:
            # покупка была, но позже 30 дней — карта «проснулась» с опозданием
            first_purchase = issued + timedelta(days=rnd.randint(31, 120))
            turnover30 = 0.0
            turnover90 = rnd.uniform(0.03, 0.2) * limit
        else:
            first_purchase = None
            turnover30 = 0.0
            turnover90 = 0.0

        status = rnd.choices(
            ["Активна", "активна", "Заблокирована", "Закрыта"],
            weights=[0.72, 0.14, 0.08, 0.06],
        )[0]

        card_id = f"CARD-{100000 + i}"
        first_txt = date_ru(first_purchase, rnd) if first_purchase else rnd.choice(["", "", "н/д"])
        t30 = money_ru(turnover30, rnd) if turnover30 else rnd.choice(["0", "0,00", ""])
        t90 = money_ru(turnover90, rnd) if turnover90 else rnd.choice(["0", "0,00", ""])

        rows.append([
            card_id, date_ru(issued, rnd), channel, tariff, region,
            money_ru(limit, rnd), first_txt, t30, t90, status,
        ])

    # повторная выгрузка части строк — классический дубль при склейке файлов
    for _ in range(int(n * 0.03)):
        rows.append(list(rnd.choice(rows)))
    rnd.shuffle(rows)

    write_csv(
        BASE / "cards" / "cards_issued_raw.csv",
        ["ID карты", "Дата выдачи", "Канал оформления", "Тарифный план", "Регион",
         "Кредитный лимит", "Дата первой покупки", "Оборот за 30 дней",
         "Оборот за 90 дней", "Статус"],
        rows, bom=True,
    )


# ------------------------------------------- набор 2: кредитный конвейер

STAGES = ["Приём заявки", "Скоринг", "Андеррайтинг", "Подготовка документов", "Выдача"]
PIPE_CHANNELS = ["Отделение", "Мобильное приложение", "Партнёрская сеть", "Корпоративный менеджер"]
PRODUCTS = ["Кредит наличными", "Кредитная карта", "Автокредит", "Кредит для бизнеса"]

# базовая длительность этапа в часах: (медиана, разброс)
STAGE_HOURS = {
    "Приём заявки": (1.5, 1.0),
    "Скоринг": (2.0, 1.5),
    "Андеррайтинг": (26.0, 22.0),   # узкое место
    "Подготовка документов": (9.0, 7.0),
    "Выдача": (5.0, 6.0),
}
# вероятность дойти до следующего этапа
STAGE_PASS = {
    "Приём заявки": 0.97,
    "Скоринг": 0.78,
    "Андеррайтинг": 0.81,
    "Подготовка документов": 0.93,
    "Выдача": 0.88,
}


def gen_pipeline(n: int = 3600) -> None:
    rnd = random.Random(SEED + 1)
    start = date(2025, 1, 6)

    apps: list[list] = []
    events: list[list] = []
    decisions: list[list] = []
    disb: list[list] = []
    event_id = 1

    for i in range(n):
        app_id = f"APP-{200000 + i}"
        channel = rnd.choices(PIPE_CHANNELS, weights=[0.3, 0.33, 0.22, 0.15])[0]
        product = rnd.choices(PRODUCTS, weights=[0.38, 0.24, 0.16, 0.22])[0]
        region = rnd.choices(REGIONS, weights=[0.3, 0.18, 0.2, 0.16, 0.16])[0]
        client_id = f"CL-{rnd.randint(400000, 460000)}"
        amount = rnd.choice([150_000, 300_000, 500_000, 800_000, 1_200_000, 2_500_000, 5_000_000])
        submitted = datetime.combine(start, datetime.min.time()) + timedelta(
            days=rnd.randint(0, 209), hours=rnd.randint(8, 19), minutes=rnd.randint(0, 59))
        is_test = rnd.random() < 0.015
        if is_test:
            client_id = "CL-TEST"

        apps.append([app_id, client_id, product, channel, region, amount,
                     submitted.strftime("%Y-%m-%d %H:%M:%S"),
                     "АБС" if rnd.random() < 0.6 else "CRM",
                     "true" if is_test else "false"])

        cursor = submitted
        rejected_at_stage = None
        for stage in STAGES:
            med, spread = STAGE_HOURS[stage]
            # партнёрская сеть заметно медленнее на андеррайтинге
            factor = 1.7 if (stage == "Андеррайтинг" and channel == "Партнёрская сеть") else 1.0
            hours = max(0.2, rnd.lognormvariate(0, 0.6) * med * factor + rnd.uniform(0, spread))
            entered = cursor
            left = entered + timedelta(hours=hours)

            row = [event_id, app_id, stage,
                   entered.strftime("%Y-%m-%d %H:%M:%S"),
                   left.strftime("%Y-%m-%d %H:%M:%S"),
                   rnd.choice(["Менеджер", "Андеррайтер", "Автоматика", "Операционист"])]

            # дефект: рассинхрон часовых поясов в источнике — конец раньше начала
            if rnd.random() < 0.012:
                row[4] = (entered - timedelta(hours=rnd.uniform(0.5, 3))).strftime("%Y-%m-%d %H:%M:%S")
            # дефект: этап не закрыт (выгрузка сделана в момент обработки)
            if rnd.random() < 0.02:
                row[4] = ""

            events.append(row)
            event_id += 1
            cursor = left

            if rnd.random() > STAGE_PASS[stage]:
                rejected_at_stage = stage
                break

        if is_test:
            decisions.append([app_id, "Одобрено", cursor.strftime("%Y-%m-%d %H:%M:%S"), "TEST"])
            continue

        if rejected_at_stage:
            reason = {
                "Приём заявки": "Неполный пакет документов",
                "Скоринг": "Скоринговый балл ниже порога",
                "Андеррайтинг": "Высокая долговая нагрузка",
                "Подготовка документов": "Клиент отозвал заявку",
                "Выдача": "Клиент не явился за средствами",
            }[rejected_at_stage]
            decisions.append([app_id, "Отказ", cursor.strftime("%Y-%m-%d %H:%M:%S"), reason])
        else:
            decisions.append([app_id, "Одобрено", cursor.strftime("%Y-%m-%d %H:%M:%S"), "Одобрено"])
            issued_at = cursor + timedelta(hours=rnd.uniform(0.5, 30))
            paid = amount * rnd.choice([1.0, 1.0, 1.0, 0.8, 0.6])
            disb.append([app_id, issued_at.strftime("%Y-%m-%d %H:%M:%S"), int(paid)])

    # дефект: часть заявок пришла в выгрузку дважды
    for _ in range(int(n * 0.02)):
        apps.append(list(rnd.choice(apps)))
    # дефект: заявки без решения — источник решений отстаёт на сутки
    orphan = rnd.sample(range(len(decisions)), int(n * 0.015))
    for idx in sorted(orphan, reverse=True):
        decisions.pop(idx)

    rnd.shuffle(apps)

    write_csv(BASE / "pipeline" / "raw_applications.csv",
              ["application_id", "client_id", "product", "channel", "region",
               "amount_requested", "submitted_at", "source_system", "is_test"], apps, ",")
    write_csv(BASE / "pipeline" / "raw_stage_events.csv",
              ["event_id", "application_id", "stage", "entered_at", "left_at", "actor_role"],
              events, ",")
    write_csv(BASE / "pipeline" / "raw_decisions.csv",
              ["application_id", "decision", "decided_at", "reason"], decisions, ",")
    write_csv(BASE / "pipeline" / "raw_disbursements.csv",
              ["application_id", "disbursed_at", "amount_disbursed"], disb, ",")


# ------------------------------------------- набор 3: портфель инициатив

INITIATIVES = [
    # название, направление, месяц старта, расходы к старту, месяц прибыльности, месяц окупаемости
    ("Автоплатёж по кредитной карте", "Карты", 0, 4_200_000, 5, 14),
    ("Предодобренный лимит в приложении", "Карты", 2, 6_800_000, 7, 19),
    ("Скоринг заявок на автокредит", "Кредиты", 1, 9_500_000, 9, 24),
    ("Электронная подпись в конвейере", "Кредиты", 4, 3_100_000, 4, 11),
    ("Речевая аналитика контакт-центра", "Обслуживание", 3, 7_400_000, 8, 21),
    ("Самообслуживание по выпискам", "Обслуживание", 6, 2_600_000, 3, 9),
    ("Витрина клиентских событий", "Данные", 0, 12_000_000, 12, 30),
    ("Единый ключ группы компаний", "Данные", 8, 5_300_000, 6, 17),
    ("Онбординг малого бизнеса за день", "Бизнес", 5, 8_100_000, 7, 20),
    ("Пакетные тарифы для МСБ", "Бизнес", 9, 4_700_000, 5, 13),
]

DISCOUNT = 0.01      # ставка дисконтирования, 1 % в месяц
HORIZON = 36         # горизонт портфеля, месяцев


def monthly_profit(cost: float, m_profit: int, m_payback: int, start: int) -> float:
    """Ежемесячная прибыль, при которой инициатива окупается ровно в свой месяц.

    Расходы равномерно распределены по месяцам до выхода на прибыльность,
    дальше идёт равномерная прибыль. Величина прибыли подбирается из условия
    «дисконтированный накопленный поток обнуляется в месяц окупаемости».
    """
    spend_pv = sum((cost / m_profit) / (1 + DISCOUNT) ** (start + t) for t in range(m_profit))
    profit_pv_unit = sum(1 / (1 + DISCOUNT) ** (start + t) for t in range(m_profit, m_payback + 1))
    return spend_pv / profit_pv_unit


def gen_portfolio() -> None:
    rnd = random.Random(SEED + 2)
    passports: list[list] = []
    facts: list[list] = []

    for idx, (name, direction, start, cost, m_profit, m_payback) in enumerate(INITIATIVES, 1):
        init_id = f"INI-{idx:02d}"
        passports.append([init_id, name, direction, start, cost, m_profit, m_payback])

        profit = monthly_profit(cost, m_profit, m_payback, start)
        # факт есть только по месяцам, которые уже прошли: горизонт наблюдения — 12 месяцев
        for month in range(start, min(start + m_payback + 1, 12)):
            t = month - start
            if t < m_profit:
                plan_cost, plan_profit = cost / m_profit, 0.0
            else:
                plan_cost, plan_profit = 0.0, profit
            facts.append([
                init_id, month,
                round(plan_cost * rnd.uniform(0.85, 1.25)),
                round(plan_profit * rnd.uniform(0.7, 1.15)),
            ])

    write_csv(BASE / "portfolio" / "initiative_passport.csv",
              ["initiative_id", "name", "direction", "start_month", "cost_rub",
               "months_to_profit", "months_to_payback"], passports, ",")
    write_csv(BASE / "portfolio" / "initiative_fact.csv",
              ["initiative_id", "month_index", "actual_cost_rub", "actual_profit_rub"],
              facts, ",")


if __name__ == "__main__":
    print("Карточный бизнес:")
    gen_cards()
    print("Кредитный конвейер:")
    gen_pipeline()
    print("Портфель инициатив:")
    gen_portfolio()
    print("Готово.")
