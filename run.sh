#!/usr/bin/env bash
# Управление учебным стендом: база с данными + система дашбордов.
#
#   ./run.sh up      — поднять стенд и настроить дашборды
#   ./run.sh status  — что запущено и сколько строк в таблицах
#   ./run.sh sql     — консоль psql
#   ./run.sh dump    — снять дамп базы в sql/dump/
#   ./run.sh down    — остановить
#   ./run.sh reset   — снести всё вместе с данными и собрать заново
set -euo pipefail

cd "$(cd "$(dirname "$0")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
PG="docker exec -i a360_postgres psql -U bank_user -d bank_training"

need_docker() {
  if ! docker info >/dev/null 2>&1; then
    echo "Docker не запущен. Запустите Docker Desktop и повторите." >&2
    exit 1
  fi
}

case "${1:-up}" in
  up)
    need_docker
    chmod +x sql/init/02_load.sh
    docker compose up -d
    echo "Жду готовности базы..."
    for _ in $(seq 1 60); do
      docker exec a360_postgres pg_isready -U bank_user -d bank_training >/dev/null 2>&1 && break
      sleep 2
    done
    echo "Жду готовности Metabase (первый запуск — до двух минут)..."
    for _ in $(seq 1 90); do
      curl -sf http://localhost:3000/api/health >/dev/null 2>&1 && break
      sleep 3
    done
    $PYTHON_BIN tools/metabase_setup.py
    echo
    echo "База:     postgresql://bank_user:bank_pass@localhost:5433/bank_training"
    echo "Дашборды: http://localhost:3000"
    ;;

  status)
    need_docker
    docker compose ps
    echo
    $PG -c "SELECT 'raw_applications' AS таблица, count(*) FROM raw_applications
            UNION ALL SELECT 'raw_stage_events', count(*) FROM raw_stage_events
            UNION ALL SELECT 'raw_decisions', count(*) FROM raw_decisions
            UNION ALL SELECT 'raw_disbursements', count(*) FROM raw_disbursements
            UNION ALL SELECT 'initiative_passport', count(*) FROM initiative_passport
            UNION ALL SELECT 'initiative_fact', count(*) FROM initiative_fact;"
    ;;

  sql)
    need_docker
    docker exec -it a360_postgres psql -U bank_user -d bank_training
    ;;

  dump)
    need_docker
    mkdir -p sql/dump
    docker exec a360_postgres pg_dump -U bank_user -d bank_training --no-owner --no-privileges \
      > sql/dump/bank_training.sql
    echo "Дамп: sql/dump/bank_training.sql ($(wc -l < sql/dump/bank_training.sql) строк)"
    ;;

  down)
    docker compose down
    ;;

  reset)
    docker compose down -v
    docker compose up -d
    echo "Стенд пересоздан с нуля. Дальше: ./run.sh up"
    ;;

  *)
    sed -n '2,10p' "$0"
    exit 1
    ;;
esac
