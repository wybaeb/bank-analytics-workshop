-- Портфель инициатив: из паспорта — денежный поток, из потока — кривая NPV.
--
-- Модель. У инициативы четыре параметра паспорта: месяц старта, расходы,
-- число месяцев до выхода на прибыльность и число месяцев до окупаемости.
-- Расходы распределены равномерно по месяцам до выхода на прибыльность.
-- Ежемесячная прибыль подобрана так, чтобы накопленный дисконтированный поток
-- обнулился ровно в месяц окупаемости — это и делает паспорт самодостаточным.
-- Ставка дисконтирования 1 % в месяц, горизонт портфеля 36 месяцев.

DROP VIEW IF EXISTS v_portfolio_npv, v_initiative_npv, v_initiative_cashflow,
                    v_initiative_plan, v_initiative_fact_vs_plan CASCADE;

CREATE VIEW v_initiative_plan AS
WITH pv AS (
    SELECT
        p.*,
        (SELECT SUM((p.cost_rub / p.months_to_profit) / power(1.01, p.start_month + t))
           FROM generate_series(0, p.months_to_profit - 1) AS t)          AS spend_pv,
        (SELECT SUM(1 / power(1.01, p.start_month + t))
           FROM generate_series(p.months_to_profit, p.months_to_payback) AS t) AS unit_pv
    FROM initiative_passport p
)
SELECT
    initiative_id,
    name,
    direction,
    start_month,
    cost_rub,
    months_to_profit,
    months_to_payback,
    floor(cost_rub / months_to_profit)  AS monthly_cost_rub,
    -- округляем вверх до рубля: так накопленный поток гарантированно выходит
    -- в ноль не позже месяца окупаемости из паспорта
    ceil(spend_pv / unit_pv)            AS monthly_profit_rub
FROM pv;

COMMENT ON VIEW v_initiative_plan IS 'Паспорт инициативы, развёрнутый в план: сколько тратим в месяц и сколько зарабатываем после выхода на прибыльность';

CREATE VIEW v_initiative_cashflow AS
SELECT
    pl.initiative_id,
    pl.name,
    pl.direction,
    m.month_index,
    CASE
        WHEN m.month_index < pl.start_month THEN 0
        WHEN m.month_index < pl.start_month + pl.months_to_profit THEN -pl.monthly_cost_rub
        ELSE pl.monthly_profit_rub
    END                                                            AS cash_flow_rub,
    round(
        CASE
            WHEN m.month_index < pl.start_month THEN 0
            WHEN m.month_index < pl.start_month + pl.months_to_profit THEN -pl.monthly_cost_rub
            ELSE pl.monthly_profit_rub
        END / power(1.01, m.month_index), 2
    )                                                              AS discounted_rub
FROM v_initiative_plan pl
CROSS JOIN generate_series(0, 36) AS m(month_index);

CREATE VIEW v_initiative_npv AS
SELECT
    initiative_id,
    name,
    direction,
    month_index,
    cash_flow_rub,
    discounted_rub,
    SUM(discounted_rub) OVER (PARTITION BY initiative_id ORDER BY month_index) AS cum_npv_rub
FROM v_initiative_cashflow;

COMMENT ON VIEW v_initiative_npv IS 'Кривая NPV каждой инициативы по месяцам';

CREATE VIEW v_portfolio_npv AS
SELECT
    month_index,
    SUM(cash_flow_rub)                                        AS cash_flow_rub,
    SUM(discounted_rub)                                       AS discounted_rub,
    SUM(SUM(discounted_rub)) OVER (ORDER BY month_index)      AS cum_npv_rub
FROM v_initiative_cashflow
GROUP BY month_index;

COMMENT ON VIEW v_portfolio_npv IS 'Сумма кривых инициатив — кривая всего портфеля';

CREATE VIEW v_initiative_fact_vs_plan AS
SELECT
    f.initiative_id,
    pl.name,
    pl.direction,
    f.month_index,
    f.actual_cost_rub,
    f.actual_profit_rub,
    CASE WHEN f.month_index < pl.start_month + pl.months_to_profit
         THEN pl.monthly_cost_rub ELSE 0 END                  AS plan_cost_rub,
    CASE WHEN f.month_index >= pl.start_month + pl.months_to_profit
         THEN pl.monthly_profit_rub ELSE 0 END                AS plan_profit_rub
FROM initiative_fact f
JOIN v_initiative_plan pl USING (initiative_id);

COMMENT ON VIEW v_initiative_fact_vs_plan IS 'План и факт по месяцам: видно, где инициатива отстаёт от паспорта';
