#!/bin/sh
set -eu

create_database() {
  database_name="$1"

  psql \
    --username "$POSTGRES_USER" \
    --dbname postgres \
    --set db_name="$database_name" <<'SQL'
SELECT format('CREATE DATABASE %I', :'db_name')
WHERE NOT EXISTS (
  SELECT FROM pg_database WHERE datname = :'db_name'
)\gexec
SQL
}

create_database "${POSTGRES_DB_RESOURCES:-meerkat}"
create_database "${POSTGRES_DB_USERS:-users}"
create_database "${POSTGRES_DB_FRONTEND:-medidex}"
