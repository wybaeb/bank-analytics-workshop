# Стенд kk_dddm: запуск практики банка

Эта папка — клон [`wybaeb/bank-analytics-workshop`](https://github.com/wybaeb/bank-analytics-workshop),
подложенный рядом с другими уроками kk_dddm. Локальный `./run.sh up` и
`docker-compose.yml` из этого репо на стенде **запускать не нужно**: общий
Postgres и Metabase уже подняты, база `bank_training` залита из дампа.

## Что уже готово

- Общий Postgres контейнера `dddm-shuvaev-postgres-1` содержит БД
  `bank_training` под пользователем `bank_user` / `bank_pass`
  (6 таблиц + 8 представлений после прогона тетрадей).
- Общий Metabase (<http://localhost:3000>) содержит подключение
  «Учебная база банка» → `bank_training`.
- Провайдер ассистента переключён на роутер `agentplatform.ru` через
  `AI_PROVIDER_URL/TOKEN/MODEL` в окружении контейнера code-server;
  `.env` рядом с этим файлом задаёт `ASSISTANT_BACKEND=openai`, GigaChat
  отключён.

## Как открыть

1. Открыть VS Code в браузере: <http://localhost:8443> (пароль стенда —
   `dddm2026`).
2. В сайдбаре — папка `bank_workshop/` рядом со старыми уроками (`L2.*`,
   `L3.*` и т. п. не тронуты).
3. Двинуться по кейсам в этом порядке:
   - [`case_cards_spreadsheet/`](case_cards_spreadsheet/) — Excel/Google
     Таблицы + ассистент. Базу и Metabase не трогает.
   - [`case_pipeline_sql/конвейер_sql.ipynb`](case_pipeline_sql/) — SQL от
     `SELECT` до чистых представлений.
   - [`case_portfolio_agent/отчёт_по_запросу.ipynb`](case_portfolio_agent/)
     — агент отвечает отчётом с графиками.
   - [`case_portfolio_agent/дашборд_агентом.ipynb`](case_portfolio_agent/)
     — агент собирает дашборд в Metabase.

## Как запускать тетрадь

1. Открыть тетрадь двойным щелчком.
2. Вверху панели тетради нажать **Restart Kernel** (круговая стрелка) —
   это критично при первом запуске и после любой правки `tools/*.py`,
   иначе Jupyter возьмёт старую версию модуля из памяти ядра.
3. **Run All** — все ячейки по порядку.

В агентских тетрадях в логе шагов должно быть `шаг 1: run_sql(query=…)`,
`шаг 2: make_chart(...)` и т. д. — реальные вызовы. Если вместо этого
в тексте появляется «Tool use: run_sql …» — ядро не перезапустили, идите
в п. 2.

## Как открывать запросы в Metabase

В редакторе SQL Metabase вверху выпадашка «Database». По умолчанию там
может стоять «Sample Database» (это встроенная H2 демо-база), запрос из
тетради упадёт с `Table "V_..." not found [42102-...]`. Нужно выбрать
**«Учебная база банка»** — тогда всё работает.

## Откуда что берётся

| Что | Где на стенде |
|---|---|
| БД `bank_training` | контейнер `dddm-shuvaev-postgres-1`, порт 5432 в docker-сети (5433 с хоста) |
| Metabase | контейнер `dddm-shuvaev-metabase-1`, `http://metabase:3000` из code-server, `http://localhost:3000` с хоста |
| Реквизиты БД | из `.env` рядом с этим файлом (`PGHOST=postgres`, `PGPORT=5432`) |
| Провайдер ассистента | из окружения контейнера code-server (корневой `.env` kk_dddm), `ASSISTANT_BACKEND=openai` |

## Если что-то сломалось

Восстановить БД из дампа:

```bash
docker exec -i dddm-shuvaev-postgres-1 \
  psql -U bank_user -d bank_training -v ON_ERROR_STOP=1 \
  < sql/dump/bank_training.sql
```

Пересобрать pyc-кеш `tools/`:

```bash
docker exec dddm-shuvaev-code-server-1 \
  rm -rf /home/coder/project/bank_workshop/tools/__pycache__
```

Проверить, что БД видит `bank_user`:

```bash
docker exec dddm-shuvaev-postgres-1 \
  psql -U bank_user -d bank_training -c "\dt"
```
