# Stage 1: Compile the .proto file
FROM python:3.11-alpine AS proto-builder

WORKDIR /proto
RUN pip3 install --no-cache-dir grpcio-tools==1.72.1

COPY utils/embedding.proto .
RUN python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. embedding.proto

# Stage 2: Main app
FROM python:3.11-alpine

RUN addgroup -S appgroup && adduser -S -G appgroup appuser

ENV PYTHONDONTWRITEBYTECODE 1

WORKDIR /app

COPY routines/requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY routines/scripts.py .
COPY routines/.env.production .env
COPY routines/wait_for_services.sh /wait_for_services.sh
RUN chmod +x /wait_for_services.sh

# 👇 Copy compiled proto files from the builder stage
COPY --from=proto-builder /proto/embedding_pb2.py .
COPY --from=proto-builder /proto/embedding_pb2_grpc.py .

ADD https://github.com/grpc-ecosystem/grpc-health-probe/releases/latest/download/grpc_health_probe-linux-arm64 /usr/bin/grpc_health_probe
RUN chmod +x /usr/bin/grpc_health_probe

EXPOSE 8002

# Switch to the non-root user before running the application
USER appuser

ENTRYPOINT ["/wait_for_services.sh"]