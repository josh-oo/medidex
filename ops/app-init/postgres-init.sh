#!/bin/sh
# Mounted into the postgres container at /docker-entrypoint-initdb.d/postgres-init.sh
# and run once, only when the postgres_data volume is first created.
#
# This is the only place that creates POSTGRES_DB_RESOURCES/KEYCLOAK: the
# databases must already exist by the time postgres accepts connections from
# the other containers. app-init later waits on the resource database being
# reachable but does not create it.
#
# Changing this file has no effect on an existing volume. To re-run it, remove
# the volume first (docker compose down -v), which deletes all Postgres data.
# For an existing volume, create any missing databases manually instead.
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

create_database "${POSTGRES_DB_RESOURCES:-resources}"
create_database "${POSTGRES_DB_LANGGRAPH:-langgraph_state}"
create_database "${POSTGRES_DB_KEYCLOAK:-keycloak}"
