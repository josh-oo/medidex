# Postgres init scripts

This directory is mounted into the `postgres` container at
`/docker-entrypoint-initdb.d`. Any `*.sql` or `*.sh` file placed here is executed
**once**, when the `postgres_data` volume is first created (i.e. on the very first
`docker compose up`). Files are run in alphabetical order. This `README.md` is
ignored by the entrypoint.

The project ships **no** schema on purpose: databases and tables are expected to
come from your own dump or provisioning step. Until they exist, the containers
still start, and the services report the missing database at request time
(`GET /backend/api/readyz` on the logic service shows the connection status).

To create the empty databases the services expect, drop a file like
`01-create-databases.sql` here:

```sql
CREATE DATABASE meerkat;   -- POSTGRES_DB_RESOURCES
CREATE DATABASE users;     -- POSTGRES_DB_USERS
CREATE DATABASE medidex;   -- POSTGRES_DB_FRONTEND (frontend / Prisma)
```

Restoring a dump instead works the same way — put the `.sql` (or a `.sh` wrapping
`pg_restore`) here, or mount the dump through `POSTGRES_BACKUPS`, which is
available inside the container at `/backups`.

Note: changing files here has no effect on an existing volume. To re-run them,
remove the volume first (`docker compose down -v`), which deletes all Postgres
data.
