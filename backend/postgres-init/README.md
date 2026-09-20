# Postgres init scripts

This directory is mounted into the `postgres` container at
`/docker-entrypoint-initdb.d`. Any `*.sql` or `*.sh` file placed here is executed
**once**, when the `postgres_data` volume is first created (i.e. on the very first
`docker compose up`). Files are run in alphabetical order. This `README.md` is
ignored by the entrypoint.

The project creates the three empty databases from the configured
`POSTGRES_DB_RESOURCES`, `POSTGRES_DB_USERS`, and `POSTGRES_DB_FRONTEND` values
using `01-create-databases.sh`. The frontend applies its committed Prisma
migrations when its container starts. Application data tables for the logic
service still need to come from your own dump or provisioning step.

Restoring a dump instead works the same way — put the `.sql` (or a `.sh` wrapping
`pg_restore`) here, or mount the dump through `POSTGRES_BACKUPS`, which is
available inside the container at `/backups`.

Note: changing files here has no effect on an existing volume. To re-run them,
remove the volume first (`docker compose down -v`), which deletes all Postgres
data. For an existing volume, create any missing databases manually or run the
script against the container before restarting the frontend.
