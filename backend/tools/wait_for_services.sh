#!/bin/sh

[ -f .env ] && . .env

echo "Waiting for Backend... ${BACKEND_API}"

# Wait for Database to return HTTP 200 on /ready
until wget -q --spider ${BACKEND_API}/readyz; do
  echo "Backend not ready yet. Sleeping..."
  sleep 2
done

# After waiting for all services, start the app
echo "All services are ready. Starting application..."

# Replace with your real app start command
exec python3 prepare_vectorstore.py
