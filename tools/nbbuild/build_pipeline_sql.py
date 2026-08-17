# -*- coding: utf-8 -*-
"""Сборка тетради «Кредитный конвейер: SQL от первого запроса до панели»."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nb import code, md, sql, write            # noqa: E402

OUT = (Path(__file__).resolve().parents[2] / "2.6_кейс_кредитный_конвейер" /
       "2.6.1_конвейер_sql.ipynb")

cells = [
    md("""
# Кредитный конвейер: от первого запроса до панели в BI

**Управленческий вопрос.** Где конвейер теряет время и заявки — и что чинить первым?

Работаем только запросами: сначала смотрим, что в базе, потом проверяем данные,
потом считаем, и в конце получаем запрос, который переносится в систему дашбордов
новой панелью.

Данные — четыре выгрузки, как они приходят из систем:

| Таблица | Что в ней |
|---|---|
| `raw_applications` | заявки: продукт, канал, регион, сумма, время подачи |
| `raw_stage_events` | прохождение этапов: вход и выход по каждому этапу |
| `raw_decisions` | решения по заявкам с причиной |
| `raw_disbursements` | выдачи средств |
"""),

    code("""
import sys
sys.path.append("..")
from tools.sqlcell import setup

setup()
"""),

    md("""
## Шаг 1. Посмотреть, что вообще есть

Первый запрос к незнакомым данным — всегда про объём и границы периода.
Без этого любое число ниже повисает в воздухе.
"""),

    sql("""
SELECT
    count(*)                        AS "Строк в выгрузке",
    count(DISTINCT application_id)  AS "Уникальных заявок",
    min(submitted_at)::date         AS "Первая заявка",
    max(submitted_at)::date         AS "Последняя заявка"
FROM raw_applications
"""),

    md("Дальше — простейшая группировка: сколько заявок по каналам и продуктам."),

    sql("""
SELECT
    channel                                  AS "Канал",
    count(*)                                 AS "Заявок",
    round(avg(amount_requested))             AS "Средняя сумма, ₽"
FROM raw_applications
GROUP BY channel
ORDER BY "Заявок" DESC
"""),

    md("""
## Шаг 2. Проверить данные до того, как считать

Выгрузка почти никогда не приходит чистой. Четыре проверки, которые стоит делать
всегда: повторы строк, служебные записи, невозможные значения, разрывы между
источниками.

### Повторы строк
"""),

    sql("""
SELECT
    count(*)                                          AS "Строк",
    count(DISTINCT application_id)                    AS "Заявок",
    count(*) - count(DISTINCT application_id)         AS "Лишних строк"
FROM raw_applications
"""),

    md("### Служебные записи"),

    sql("""
SELECT
    count(DISTINCT application_id) AS "Тестовых заявок"
FROM raw_applications
WHERE is_test OR client_id = 'CL-TEST'
"""),

    md("""
### Невозможные значения и незакрытые этапы

Этап не может закончиться раньше, чем начался: такие строки означают рассинхрон
времени между системами. Пустое время выхода — это другое: этап ещё идёт на момент
выгрузки. Первое чиним, второе учитываем отдельно.
"""),

    sql("""
SELECT
    count(*) FILTER (WHERE left_at < entered_at)  AS "Выход раньше входа",
    count(*) FILTER (WHERE left_at IS NULL)       AS "Этап не закрыт",
    count(*)                                      AS "Всего событий"
FROM raw_stage_events
"""),

    md("### Разрыв между источниками: заявки, по которым нет решения"),

    sql("""
SELECT count(*) AS "Заявок без решения"
FROM (SELECT DISTINCT application_id FROM raw_applications) a
LEFT JOIN raw_decisions d USING (application_id)
WHERE d.application_id IS NULL
"""),

    md("""
### Сколько стоит пропустить проверку

Считаем конверсию в выдачу двумя способами: как есть и после отсева повторов и
служебных записей. Разница — цена одной пропущенной проверки.
"""),

    sql("""
SELECT
    round(100.0 * (SELECT count(*) FROM raw_disbursements)
                / (SELECT count(*) FROM raw_applications), 1)          AS "Как есть, %",
    round(100.0 * (SELECT count(DISTINCT d.application_id)
                     FROM raw_disbursements d
                     JOIN (SELECT DISTINCT application_id
                             FROM raw_applications
                            WHERE NOT is_test AND client_id <> 'CL-TEST') a USING (application_id))
                / (SELECT count(DISTINCT application_id)
                     FROM raw_applications
                    WHERE NOT is_test AND client_id <> 'CL-TEST'), 1)  AS "После проверки, %"
"""),

    md("""
Разница почти в два процентных пункта — на таком масштабе это сотни заявок.
А минимальная длительность этапа в сырых данных отрицательная, то есть число
не просто смещено, она невозможна.

## Шаг 3. Собрать чистый слой

Чистку не повторяют в каждом запросе — её один раз оформляют представлением.
Дальше все расчёты идут поверх него, и правило чистки живёт в одном месте.
"""),

    sql("""
CREATE OR REPLACE VIEW v_applications_clean AS
SELECT DISTINCT ON (application_id)
    application_id,
    client_id,
    product,
    channel,
    region,
    amount_requested,
    submitted_at,
    source_system
FROM raw_applications
WHERE NOT is_test
  AND client_id <> 'CL-TEST'
ORDER BY application_id, submitted_at
"""),

    sql("""
CREATE OR REPLACE VIEW v_stage_events_clean AS
SELECT
    e.event_id,
    e.application_id,
    e.stage,
    e.entered_at,
    e.left_at,
    EXTRACT(EPOCH FROM (e.left_at - e.entered_at)) / 3600 AS hours
FROM raw_stage_events e
JOIN v_applications_clean a USING (application_id)
WHERE e.left_at IS NOT NULL
  AND e.left_at > e.entered_at
"""),

    md("Проверяем, что чистый слой не потерял лишнего."),

    sql("""
SELECT
    (SELECT count(*) FROM raw_applications)        AS "Строк было",
    (SELECT count(*) FROM v_applications_clean)    AS "Заявок стало",
    (SELECT count(*) FROM raw_stage_events)        AS "Событий было",
    (SELECT count(*) FROM v_stage_events_clean)    AS "Событий стало"
"""),

    md("""
## Шаг 4. Посчитать то, ради чего всё затевалось

### Куда доходят заявки
"""),

    sql("""
SELECT
    e.stage                                                             AS "Этап",
    count(DISTINCT e.application_id)                                    AS "Дошло заявок",
    round(100.0 * count(DISTINCT e.application_id)
          / (SELECT count(*) FROM v_applications_clean), 1)             AS "Доля от поданных, %"
FROM v_stage_events_clean e
GROUP BY e.stage
ORDER BY "Дошло заявок" DESC
"""),

    md("""
### Сколько времени занимает этап

Среднее по длительностям обманывает: хвост тянет его вверх. Смотрим медиану и
девяностую перцентиль — типичный срок и срок, в который укладывается почти всё.
"""),

    sql("""
SELECT
    stage                                                                        AS "Этап",
    count(*)                                                                     AS "Событий",
    round(percentile_cont(0.5) WITHIN GROUP (ORDER BY hours)::numeric, 1)        AS "Медиана, ч",
    round(percentile_cont(0.9) WITHIN GROUP (ORDER BY hours)::numeric, 1)        AS "P90, ч"
FROM v_stage_events_clean
GROUP BY stage
ORDER BY "Медиана, ч" DESC
"""),

    md("""
Самый долгий этап виден сразу. Следующий вопрос — одинаково ли он долгий везде.
"""),

    sql("""
SELECT
    a.channel                                                                    AS "Канал",
    count(*)                                                                     AS "Заявок",
    round(percentile_cont(0.5) WITHIN GROUP (ORDER BY e.hours)::numeric, 1)      AS "Медиана, ч",
    round(percentile_cont(0.9) WITHIN GROUP (ORDER BY e.hours)::numeric, 1)      AS "P90, ч"
FROM v_stage_events_clean e
JOIN v_applications_clean a USING (application_id)
WHERE e.stage = 'Андеррайтинг'
GROUP BY a.channel
ORDER BY "Медиана, ч" DESC
"""),

    md("""
### Где теряются заявки

Причины отказов показывают, что именно чинить: скоринговый порог, документы
или работу с клиентом.
"""),

    sql("""
SELECT
    d.reason                                                        AS "Причина",
    count(*)                                                        AS "Заявок",
    round(100.0 * count(*) / sum(count(*)) OVER (), 1)              AS "Доля, %"
FROM raw_decisions d
JOIN v_applications_clean a USING (application_id)
WHERE d.decision = 'Отказ'
GROUP BY d.reason
ORDER BY "Заявок" DESC
"""),

    md("""
## Шаг 5. Запрос, который уходит в панель

Разовый ответ в тетради живёт до закрытия ноутбука. Чтобы им пользовались,
запрос переносят в систему дашбордов. Ниже — тот самый запрос: срок каждого
этапа в разрезе канала.
"""),

    sql("""
SELECT
    a.channel                                                                    AS "Канал",
    e.stage                                                                      AS "Этап",
    count(*)                                                                     AS "Заявок",
    round(percentile_cont(0.5) WITHIN GROUP (ORDER BY e.hours)::numeric, 1)      AS "Медиана, ч",
    round(percentile_cont(0.9) WITHIN GROUP (ORDER BY e.hours)::numeric, 1)      AS "P90, ч"
FROM v_stage_events_clean e
JOIN v_applications_clean a USING (application_id)
GROUP BY a.channel, e.stage
ORDER BY "Медиана, ч" DESC
"""),

    md("""
Тот же расчёт оформляем представлением — тогда панель ссылается на него, а правило
расчёта остаётся в базе и не расходится между отчётами.
"""),

    sql("""
CREATE OR REPLACE VIEW v_pipeline_stage_sla AS
SELECT
    a.channel                                                              AS channel,
    e.stage                                                                AS stage,
    count(*)                                                               AS applications,
    round(percentile_cont(0.5) WITHIN GROUP (ORDER BY e.hours)::numeric, 1) AS median_hours,
    round(percentile_cont(0.9) WITHIN GROUP (ORDER BY e.hours)::numeric, 1) AS p90_hours
FROM v_stage_events_clean e
JOIN v_applications_clean a USING (application_id)
GROUP BY a.channel, e.stage
"""),

    sql("""
SELECT * FROM v_pipeline_stage_sla ORDER BY median_hours DESC
"""),

    md("""
## Перенести запрос в панель

1. Откройте систему дашбордов: <http://localhost:3000>
2. **Создать → Запрос → Свой SQL-запрос**, источник «Учебная база банка».
3. Вставьте запрос из ячейки выше и выполните.
4. Смените тип отображения на столбчатую диаграмму: по горизонтали — этап,
   по вертикали — медиана, разбивка по каналу.
5. Сохраните под именем «Сроки этапов конвейера» и добавьте на новый дашборд
   «Кредитный конвейер».

Если данные в базе обновятся, панель покажет новые значения без единой правки —
именно поэтому расчёт переносят в BI, а не рассылают картинку.

## Что из этого следует

- Самый долгий этап конвейера — андеррайтинг, и он неодинаков по каналам:
  партнёрская сеть ждёт заметно дольше остальных.
- Проверка данных меняет управленческий вывод: конверсия «как есть» и конверсия
  после отсева повторов отличаются почти на два процентных пункта.
- Правило чистки живёт в представлении, а не в переписке: любой следующий запрос
  считает по тем же правилам.

**Задание.** Возьмите свой процесс и повторите путь: обзор → проверки → чистый
слой → медиана и P90 по этапам → запрос в панель. Достаточно одного показателя,
который вы готовы обсуждать с командой.
"""),
]

write(OUT, cells)
