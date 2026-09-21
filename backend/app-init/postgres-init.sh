#!/bin/sh
# Mounted into the postgres container at /docker-entrypoint-initdb.d/postgres-init.sh
# and run once, only when the postgres_data volume is first created.
#
# This is the only place that creates POSTGRES_DB_RESOURCES/USERS/FRONTEND: the
# frontend container has no dependency on app-init and applies its Prisma
# migrations as soon as it starts, so the databases must already exist by the
# time postgres accepts connections. app-init later waits on the resource
# database being reachable but does not create it.
#
# Changing this file has no effect on an existing volume. To re-run it, remove
# the volume first (docker compose down -v), which deletes all Postgres data.
# For an existing volume, create any missing databases manually instead. On an
# existing volume using the old name, rename it instead of recreating it:
# ALTER DATABASE meerkat RENAME TO resources (or set POSTGRES_DB_RESOURCES to
# the name you already use).
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
create_database "${POSTGRES_DB_USERS:-users}"
create_database "${POSTGRES_DB_FRONTEND:-medidex}"
