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
ENV GRPC_HEALTH_PROBE_VERSION=v0.4.38

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

RUN ARCH=$(dpkg --print-architecture) && \
    case "$ARCH" in \
      amd64)  ARCH_DL=linux-amd64 ;; \
      arm64)  ARCH_DL=linux-arm64 ;; \
      armhf)  ARCH_DL=linux-arm ;; \
      *)      echo "Unsupported architecture: $ARCH" && exit 1 ;; \
    esac && \
    curl -sSL -o /home/appuser/grpc_health_probe \
      https://github.com/grpc-ecosystem/grpc-health-probe/releases/download/${GRPC_HEALTH_PROBE_VERSION}/grpc_health_probe-${ARCH_DL} && \
    chmod 755 /home/appuser/grpc_health_probe && \
    chown appuser:appuser /home/appuser/grpc_health_probe

EXPOSE 8002

# Switch to the non-root user before running the application
USER appuser

ENTRYPOINT ["/wait_for_services.sh"]