# -*- coding: utf-8 -*-
"""Пары «одна операция — два способа»: запрос к базе и то же самое в pandas.

Единственный источник правды для памятки. Из этого списка собирается и тетрадь
(`build_sql_pandas_memo.py`), и страница памятки в материалах курса. Поэтому
код здесь пишется так, чтобы его можно было читать, а не только
выполнять: без сокращений, с русскими именами результатов.

Договорённость об именах таблиц в памяти:
    заявки  — raw_applications      этапы   — raw_stage_events
    решения — raw_decisions         выдачи  — raw_disbursements
"""

ВСТУПЛЕНИЕ = """Одна и та же операция разведочного анализа — слева запросом
к базе, справа в pandas. Обе колонки выполняются на одних и тех же данных
кредитного конвейера, и результат сверяется автоматически: памятка не даёт
обещаний, которые нельзя проверить."""

ПРАВИЛО = """SQL считает там, где лежат данные: база читает миллионы строк
и отдаёт десятки. Pandas работает уже с тем, что поместилось в память
тетради. Отсюда практическое правило: **отбор, соединение и агрегация —
запросом; доводка, форма таблицы и график — в pandas.** Ошибка, которая
дорого стоит, — вытащить `SELECT *` на миллион строк и группировать его
в тетради: то же самое база сделает за секунды и вернёт готовый ответ."""

PAIRS = [
    dict(
        n=1,
        title="Размер выгрузки и границы периода",
        why="Первый вопрос к незнакомым данным: сколько строк и за какой период. "
            "Пока это не проверено, любое число ниже повисает в воздухе.",
        sql="""SELECT count(*)                       AS строк,
       count(DISTINCT application_id) AS заявок,
       min(submitted_at)::date        AS первая,
       max(submitted_at)::date        AS последняя
FROM raw_applications""",
        pd="""справа = pd.DataFrame([{
    "строк":  len(заявки),
    "заявок": заявки["application_id"].nunique(),
    "первая": заявки["submitted_at"].min().date(),
    "последняя": заявки["submitted_at"].max().date(),
}])""",
        note="Строк больше, чем заявок, — это уже находка: в выгрузке повторы.",
    ),
    dict(
        n=2,
        title="Какие столбцы и какого они типа",
        why="Тип столбца решает, что с ним можно делать. Сумма, сохранённая "
            "как текст, искажает среднее.",
        sql="""SELECT column_name AS столбец, data_type AS тип
FROM information_schema.columns
WHERE table_name = 'raw_applications'
ORDER BY ordinal_position""",
        pd="""справа = заявки.dtypes""",
        note="В базе тип задан схемой и гарантирован. В pandas тип угадывается "
             "при чтении файла, поэтому `dtypes` смотрят всегда: `object` "
             "у колонки с суммами означает, что внутри текст.",
        compare=False,
    ),
    dict(
        n=3,
        title="Посмотреть первые строки",
        why="Просмотр десятка строк показывает то, чего не видно ни в одной "
            "сводке: формат дат, лишние пробелы, служебные значения.",
        sql="""SELECT application_id, product, channel, amount_requested
FROM raw_applications
ORDER BY application_id
LIMIT 5""",
        pd="""справа = (заявки.sort_values("application_id")
          [["application_id", "product", "channel", "amount_requested"]]
          .head(5))""",
        note="`LIMIT` без `ORDER BY` возвращает произвольные строки: порядок "
             "в таблице базы не определён. То же и с `head()` — он берёт "
             "первые строки в текущем порядке кадра.",
    ),
    dict(
        n=4,
        title="Отобрать строки по условию",
        why="Любая проверка гипотезы начинается с отбора: один продукт, один "
            "канал, один диапазон сумм.",
        sql="""SELECT count(*) AS заявок, round(avg(amount_requested)) AS средняя
FROM raw_applications
WHERE product = 'Автокредит'
  AND amount_requested > 3000000""",
        pd="""крупные = заявки[(заявки["product"] == "Автокредит")
                & (заявки["amount_requested"] > 3_000_000)]
справа = pd.DataFrame([{
    "заявок":  len(крупные),
    "средняя": round(крупные["amount_requested"].mean()),
}])""",
        note="Скобки вокруг каждого условия в pandas обязательны: `&` "
             "выполняется раньше сравнения, и без скобок выражение падает.",
    ),
    dict(
        n=5,
        title="Уникальные значения категории",
        why="Пока не видно списка значений, группировка по столбцу "
            "бессмысленна: «Отделение» и «отделение » — две разные строки.",
        sql="""SELECT DISTINCT channel AS канал
FROM raw_applications
ORDER BY канал""",
        pd="""справа = pd.DataFrame({"канал": sorted(заявки["channel"].unique())})""",
        note="Порядок сортировки строк в базе и в Python может отличаться "
             "локалью — если сверяете списки, сортируйте обе стороны одинаково.",
    ),
    dict(
        n=6,
        title="Частоты значений: сколько чего",
        why="Самая частая операция разведочного анализа. Показывает и "
            "структуру данных, и некорректные значения в них.",
        sql="""SELECT channel        AS канал,
       count(*)       AS заявок
FROM raw_applications
GROUP BY channel
ORDER BY заявок DESC""",
        pd="""справа = (заявки["channel"].value_counts()
          .rename_axis("канал").reset_index(name="заявок"))""",
        note="`value_counts()` сразу сортирует по убыванию — это и есть "
             "`GROUP BY … ORDER BY count(*) DESC` одной командой.",
    ),
    dict(
        n=7,
        title="Пропуски по столбцам",
        why="Пропуск — это не всегда ошибка. Незакрытый этап означает «ещё "
            "идёт», и такие строки считают отдельно, а не выбрасывают.",
        sql="""SELECT count(*) FILTER (WHERE left_at IS NULL)    AS без_выхода,
       count(*) FILTER (WHERE actor_role IS NULL) AS без_роли,
       count(*)                                   AS всего
FROM raw_stage_events""",
        pd="""справа = pd.DataFrame([{
    "без_выхода": int(этапы["left_at"].isna().sum()),
    "без_роли":   int(этапы["actor_role"].isna().sum()),
    "всего":      len(этапы),
}])""",
        note="`FILTER (WHERE …)` — способ посчитать несколько условий одним "
             "проходом по таблице. В pandas тому же соответствует `isna().sum()` "
             "по каждому столбцу.",
    ),
    dict(
        n=8,
        title="Сколько строк лишние: повторы",
        why="Повторы приезжают при склейке выгрузок из разных систем и "
            "завышают всё, что считается по строкам.",
        sql="""SELECT count(*)                                  AS строк,
       count(DISTINCT application_id)            AS заявок,
       count(*) - count(DISTINCT application_id) AS лишних
FROM raw_applications""",
        pd="""справа = pd.DataFrame([{
    "строк":  len(заявки),
    "заявок": заявки["application_id"].nunique(),
    "лишних": int(заявки["application_id"].duplicated().sum()),
}])""",
        note="`duplicated()` по умолчанию помечает все повторы, кроме первого, — "
             "поэтому его сумма и есть число лишних строк.",
    ),
    dict(
        n=9,
        title="Убрать повторы, оставив первую запись",
        why="Правило «какую из копий оставляем» задаёт аналитик, а не "
            "инструмент: обычно самую раннюю или самую свежую по времени.",
        sql="""SELECT count(*) AS осталось
FROM (
    SELECT DISTINCT ON (application_id) application_id
    FROM raw_applications
    ORDER BY application_id, submitted_at
) t""",
        pd="""без_повторов = (заявки.sort_values(["application_id", "submitted_at"])
                 .drop_duplicates("application_id", keep="first"))
справа = pd.DataFrame([{"осталось": len(без_повторов)}])""",
        note="`DISTINCT ON` — приём PostgreSQL: он оставляет первую строку "
             "в порядке `ORDER BY`. В других диалектах то же делают через "
             "`ROW_NUMBER() OVER (PARTITION BY …)` и отбор `= 1`.",
    ),
    dict(
        n=10,
        title="Привести тип: суммы к числу",
        why="В выгрузке из файла суммы почти всегда приходят текстом — "
            "с пробелами и запятой. Пока не приведены, среднее считать нельзя.",
        sql="""SELECT round(sum(amount_requested)) AS сумма
FROM raw_applications""",
        pd="""суммы = pd.to_numeric(заявки["amount_requested"], errors="coerce")
справа = pd.DataFrame([{"сумма": round(суммы.sum())}])""",
        note="`errors=\"coerce\"` превращает неразобранное в `NaN` вместо "
             "ошибки — и число таких `NaN` сразу показывает, сколько значений "
             "не приводились к типу. В базе тип задан схемой, приводить нечего.",
    ),
    dict(
        n=11,
        title="Группировка с несколькими метриками",
        why="Основной рабочий инструмент: разрез плюс два-три показателя.",
        sql="""SELECT channel                     AS канал,
       count(*)                    AS заявок,
       round(avg(amount_requested)) AS средняя,
       round(sum(amount_requested)) AS сумма
FROM raw_applications
GROUP BY channel
ORDER BY заявок DESC""",
        pd="""справа = (заявки.groupby("channel")
          .agg(заявок=("application_id", "count"),
               средняя=("amount_requested", "mean"),
               сумма=("amount_requested", "sum"))
          .round(0).reset_index()
          .rename(columns={"channel": "канал"})
          .sort_values("заявок", ascending=False)
          .reset_index(drop=True))""",
        note="Именованная агрегация в pandas (`заявок=(столбец, функция)`) — "
             "прямой аналог `AS` в SQL: столбцы сразу называются по-человечески.",
    ),
    dict(
        n=12,
        title="Фильтр после агрегации",
        why="«Показать только те группы, где заявок больше тысячи» — это "
            "условие на результат, а не на строки.",
        sql="""SELECT channel   AS канал,
       count(*)  AS заявок
FROM raw_applications
GROUP BY channel
HAVING count(*) > 1000
ORDER BY заявок DESC""",
        pd="""справа = (заявки["channel"].value_counts()
          .rename_axis("канал").reset_index(name="заявок")
          .query("заявок > 1000")
          .reset_index(drop=True))""",
        note="`WHERE` отбирает строки до группировки, `HAVING` — группы после. "
             "В pandas это просто фильтр по уже посчитанному кадру.",
    ),
    dict(
        n=13,
        title="Сортировка и первые N",
        why="Рейтинг — самая частая просьба руководителя: «покажи топ-5».",
        sql="""SELECT region                       AS регион,
       round(sum(amount_requested)) AS сумма
FROM raw_applications
GROUP BY region
ORDER BY сумма DESC
LIMIT 5""",
        pd="""справа = (заявки.groupby("region")["amount_requested"].sum()
          .round(0).rename_axis("регион").reset_index(name="сумма")
          .sort_values("сумма", ascending=False)
          .head(5).reset_index(drop=True))""",
        note="При равных значениях на границе топа порядок не определён "
             "ни там, ни там: если это важно, добавляйте второй ключ сортировки.",
    ),
    dict(
        n=14,
        title="Соединить две таблицы",
        why="Данные почти никогда не лежат в одной таблице: заявки в одной, "
            "решения по ним в другой.",
        sql="""SELECT a.channel   AS канал,
       count(*)    AS отказов
FROM raw_applications a
JOIN raw_decisions d ON d.application_id = a.application_id
WHERE d.decision = 'Отказ'
GROUP BY a.channel
ORDER BY отказов DESC""",
        pd="""вместе = заявки.merge(решения, on="application_id", how="inner")
справа = (вместе[вместе["decision"] == "Отказ"]["channel"]
          .value_counts().rename_axis("канал").reset_index(name="отказов"))""",
        note="`how=\"inner\"` — это `JOIN`, `how=\"left\"` — `LEFT JOIN`. "
             "После соединения всегда проверяйте число строк: если оно выросло, "
             "ключ не уникален и результат уже задвоен.",
    ),
    dict(
        n=15,
        title="Разбивка по месяцам",
        why="Динамика отвечает на вопрос «стало лучше или хуже», а одна "
            "число за период — нет.",
        sql="""SELECT to_char(date_trunc('month', submitted_at), 'YYYY-MM') AS месяц,
       count(*)                                          AS заявок
FROM raw_applications
GROUP BY 1
ORDER BY 1""",
        pd="""справа = (заявки["submitted_at"].dt.to_period("M").astype(str)
          .value_counts().sort_index()
          .rename_axis("месяц").reset_index(name="заявок"))""",
        note="`date_trunc` округляет дату вниз до начала периода. В pandas ту "
             "же роль играет `to_period(\"M\")`, а `dt.month` — не то же самое: "
             "он склеит январь двух разных лет.",
    ),
    dict(
        n=16,
        title="Сводная таблица: два разреза сразу",
        why="Пересечение двух признаков показывает то, чего не видно "
            "по каждому в отдельности: например, что доля канала неодинакова "
            "у разных продуктов.",
        sql="""SELECT product AS продукт,
       count(*) FILTER (WHERE channel = 'Отделение')            AS отделение,
       count(*) FILTER (WHERE channel = 'Мобильное приложение') AS приложение
FROM raw_applications
GROUP BY product
ORDER BY продукт""",
        pd="""сводная = заявки.pivot_table(index="product", columns="channel",
                            values="application_id", aggfunc="count",
                            fill_value=0)
справа = (сводная[["Отделение", "Мобильное приложение"]]
          .rename(columns={"Отделение": "отделение",
                           "Мобильное приложение": "приложение"})
          .rename_axis("продукт").reset_index()
          .sort_values("продукт").reset_index(drop=True))""",
        note="`pivot_table` — самый быстрый способ увидеть пересечение "
             "признаков. В SQL то же делают через `FILTER (WHERE …)` или "
             "`CASE WHEN` внутри агрегата.",
    ),
    dict(
        n=17,
        title="Доля от общего",
        why="Абсолютные числа сравнивать нельзя, если группы разного размера. "
            "Доля — минимальная нормировка.",
        sql="""SELECT channel                                          AS канал,
       count(*)                                         AS заявок,
       round(100.0 * count(*) / sum(count(*)) OVER (), 1) AS доля
FROM raw_applications
GROUP BY channel
ORDER BY заявок DESC""",
        pd="""по_каналу = (заявки["channel"].value_counts()
             .rename_axis("канал").reset_index(name="заявок"))
по_каналу["доля"] = (100 * по_каналу["заявок"]
                     / по_каналу["заявок"].sum()).round(1)
справа = по_каналу""",
        note="`sum(count(*)) OVER ()` — оконная функция: считает итог по всем "
             "группам, не схлопывая их. В pandas это просто деление на сумму "
             "столбца.",
    ),
    dict(
        n=18,
        title="Медиана и перцентиль",
        why="Среднее по длительностям обманывает: один долгий случай тянет "
            "его вверх. Медиана — типичный срок, P90 — тот, в который "
            "укладывается почти всё.",
        sql="""SELECT stage AS этап,
       round(percentile_cont(0.5) WITHIN GROUP (
             ORDER BY EXTRACT(EPOCH FROM (left_at - entered_at)) / 3600)::numeric, 1) AS медиана,
       round(percentile_cont(0.9) WITHIN GROUP (
             ORDER BY EXTRACT(EPOCH FROM (left_at - entered_at)) / 3600)::numeric, 1) AS p90
FROM raw_stage_events
WHERE left_at IS NOT NULL AND left_at > entered_at
GROUP BY stage
ORDER BY медиана DESC""",
        pd="""закрытые = этапы[этапы["left_at"].notna()
                  & (этапы["left_at"] > этапы["entered_at"])].copy()
закрытые["часы"] = ((закрытые["left_at"] - закрытые["entered_at"])
                    .dt.total_seconds() / 3600)
справа = (закрытые.groupby("stage")["часы"]
          .agg(медиана=lambda s: s.quantile(0.5),
               p90=lambda s: s.quantile(0.9))
          .round(1).rename_axis("этап").reset_index()
          .sort_values("медиана", ascending=False)
          .reset_index(drop=True))""",
        note="`percentile_cont` в PostgreSQL и `quantile()` в pandas "
             "интерполируют одинаково — линейно. `percentile_disc` вернул бы "
             "существующее значение из выборки, и числа разошлись бы.",
    ),
    dict(
        n=19,
        title="Условная колонка: разложить по корзинам",
        why="Непрерывную величину почти всегда режут на группы: малые, "
            "средние и крупные заявки ведут себя по-разному.",
        sql="""SELECT CASE WHEN amount_requested < 500000  THEN '1. до 500 тыс'
            WHEN amount_requested < 2000000 THEN '2. 0,5–2 млн'
            ELSE                                 '3. свыше 2 млн'
       END      AS размер,
       count(*) AS заявок
FROM raw_applications
GROUP BY размер
ORDER BY размер""",
        pd="""размер = pd.cut(заявки["amount_requested"],
                 bins=[-1, 499_999, 1_999_999, float("inf")],
                 labels=["1. до 500 тыс", "2. 0,5–2 млн", "3. свыше 2 млн"])
справа = (размер.value_counts().sort_index()
          .rename_axis("размер").reset_index(name="заявок"))""",
        note="Границы корзин задаёт аналитик, и они всегда спорные — поэтому "
             "их проговаривают вслух вместе с выводом, а не прячут в код.",
    ),
    dict(
        n=20,
        title="Оконная функция: первая заявка клиента",
        why="«Первый», «последний», «предыдущий» — это всегда окно: строки "
            "нумеруются внутри группы, а не по всей таблице.",
        sql="""SELECT count(*) AS первых_заявок
FROM (
    SELECT ROW_NUMBER() OVER (PARTITION BY client_id
                              ORDER BY submitted_at) AS n
    FROM raw_applications
) t
WHERE n = 1""",
        pd="""номер = (заявки.sort_values("submitted_at")
         .groupby("client_id").cumcount() + 1)
справа = pd.DataFrame([{"первых_заявок": int((номер == 1).sum())}])""",
        note="Оконная функция не схлопывает строки: рядом с каждой заявкой "
             "появляется её номер, и дальше можно отобрать любой. В pandas "
             "тот же приём — `cumcount()` после сортировки.",
    ),
    dict(
        n=21,
        title="Выбросы по правилу полутора размахов",
        why="Классический способ отделить «долго» от «невозможно долго». "
            "Найденное — повод для вопроса, а не для удаления строки.",
        sql="""WITH ч AS (
    SELECT EXTRACT(EPOCH FROM (left_at - entered_at)) / 3600 AS часы
    FROM raw_stage_events
    WHERE stage = 'Андеррайтинг' AND left_at > entered_at
), г AS (
    SELECT percentile_cont(0.25) WITHIN GROUP (ORDER BY часы) AS q1,
           percentile_cont(0.75) WITHIN GROUP (ORDER BY часы) AS q3
    FROM ч
)
SELECT count(*) AS выбросов,
       round((SELECT (q3 + 1.5 * (q3 - q1))::numeric FROM г), 1) AS порог
FROM ч, г
WHERE ч.часы > г.q3 + 1.5 * (г.q3 - г.q1)""",
        pd="""андеррайтинг = этапы[(этапы["stage"] == "Андеррайтинг")
                     & (этапы["left_at"] > этапы["entered_at"])]
часы = ((андеррайтинг["left_at"] - андеррайтинг["entered_at"])
        .dt.total_seconds() / 3600)
q1, q3 = часы.quantile(0.25), часы.quantile(0.75)
порог = q3 + 1.5 * (q3 - q1)
справа = pd.DataFrame([{"выбросов": int((часы > порог).sum()),
                        "порог": round(порог, 1)}])""",
        note="Правило работает на распределениях без длинного хвоста. Там, где "
             "хвост есть по природе процесса, оно пометит выбросами нормальные "
             "случаи — тогда границу задают перцентилем, например P99.",
    ),
]

for _p in PAIRS:                      # по умолчанию результаты сверяются
    _p.setdefault("compare", True)
