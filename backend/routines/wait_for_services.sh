#!/bin/sh

[ -f .env ] && . .env

echo "Waiting for Database... ${DATABASE_HOST}:${DATABASE_PORT}"

# Wait for Database to return HTTP 200 on /ready
until wget -q --spider http://${DATABASE_HOST}:${DATABASE_PORT}/readyz; do
  echo "Database not ready yet. Sleeping..."
  sleep 2
done

echo "Waiting for Qdrant... ${VECTORSTORE_HOST}:6333"

# Wait for Qdrant to return HTTP 200 on /ready
until wget -q --spider http://${VECTORSTORE_HOST}:6333/readyz; do
  echo "Qdrant not ready yet. Sleeping..."
  sleep 2
done

echo "Waiting for Embedding... ${EMBEDDING_HOST}:${EMBEDDING_PORT}"

# Wait for Embedding to return HTTP 200 on /ready
until grpc_health_probe -addr=${EMBEDDING_HOST}:${EMBEDDING_PORT}; do
  echo "gRPC server not ready yet. Sleeping..."
  sleep 2
done

# After waiting for all services, start the app
echo "All services are ready. Starting application..."

# Replace with your real app start command
exec python3 scripts.py
