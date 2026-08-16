-- Учебная схема стенда: сырые выгрузки как есть, без исправлений.
-- Дефекты в данных оставлены намеренно — их находят и чинят запросами.

DROP TABLE IF EXISTS raw_applications, raw_stage_events, raw_decisions,
                     raw_disbursements, initiative_passport, initiative_fact CASCADE;

-- ------------------------------------------------ кредитный конвейер

CREATE TABLE raw_applications (
    application_id   text,
    client_id        text,
    product          text,
    channel          text,
    region           text,
    amount_requested numeric,
    submitted_at     timestamp,
    source_system    text,
    is_test          boolean
);
COMMENT ON TABLE raw_applications IS 'Заявки как приходят из выгрузки: есть повторы строк и тестовые записи';

CREATE TABLE raw_stage_events (
    event_id       integer,
    application_id text,
    stage          text,
    entered_at     timestamp,
    left_at        timestamp,
    actor_role     text
);
COMMENT ON TABLE raw_stage_events IS 'События этапов: часть строк без времени выхода, у части выход раньше входа';

CREATE TABLE raw_decisions (
    application_id text,
    decision       text,
    decided_at     timestamp,
    reason         text
);
COMMENT ON TABLE raw_decisions IS 'Решения по заявкам: источник отстаёт, часть заявок остаётся без решения';

CREATE TABLE raw_disbursements (
    application_id   text,
    disbursed_at     timestamp,
    amount_disbursed numeric
);
COMMENT ON TABLE raw_disbursements IS 'Выдачи средств по одобренным заявкам';

-- ------------------------------------------------ портфель инициатив

CREATE TABLE initiative_passport (
    initiative_id     text PRIMARY KEY,
    name              text,
    direction         text,
    start_month       integer,   -- месяц старта относительно начала портфеля
    cost_rub          numeric,   -- расходы к моменту выхода на прибыльность
    months_to_profit  integer,   -- месяцев от старта до выхода на прибыльность
    months_to_payback integer    -- месяцев от старта до окупаемости
);
COMMENT ON TABLE initiative_passport IS 'Паспорт инициативы: четыре параметра, по которым инициатива превращается в кривую NPV';

CREATE TABLE initiative_fact (
    initiative_id     text,
    month_index       integer,
    actual_cost_rub   numeric,
    actual_profit_rub numeric
);
COMMENT ON TABLE initiative_fact IS 'Фактические расходы и прибыль по месяцам — для сверки плана с фактом';
