#!/bin/sh
set -eu

npx prisma migrate deploy
npx tsx scripts/seed-admin.ts
exec "$@"