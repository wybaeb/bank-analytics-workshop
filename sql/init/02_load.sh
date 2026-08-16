#!/bin/bash
# Загрузка учебных выгрузок в базу. Выполняется автоматически при первом
# запуске контейнера базы: файлы примонтированы в /seed только на чтение.
set -euo pipefail

copy() {
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
       -c "\copy $1 FROM '/seed/$2' WITH (FORMAT csv, HEADER true)"
}

copy raw_applications   pipeline/raw_applications.csv
copy raw_stage_events   pipeline/raw_stage_events.csv
copy raw_decisions      pipeline/raw_decisions.csv
copy raw_disbursements  pipeline/raw_disbursements.csv
copy initiative_passport portfolio/initiative_passport.csv
copy initiative_fact     portfolio/initiative_fact.csv
