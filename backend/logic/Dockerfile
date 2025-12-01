# Stage 1: Compile the .proto file
FROM python:3.13-slim AS proto-builder

WORKDIR /proto
RUN pip3 install --no-cache-dir grpcio-tools==1.72.1

COPY tools/utils/embedding.proto .
RUN python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. embedding.proto

# Stage 2: Main app
FROM python:3.13-slim

RUN groupadd -r appgroup && useradd -r -g appgroup appuser

ENV PYTHONDONTWRITEBYTECODE 1

WORKDIR /app

COPY logic/requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY logic/api.py .
COPY logic/src/ ./src/

# 👇 Copy compiled proto files from the builder stage
COPY --from=proto-builder /proto/embedding_pb2.py .
COPY --from=proto-builder /proto/embedding_pb2_grpc.py .

# Switch to the non-root user before running the application
USER appuser

# uvicorn api:app --host 0.0.0.0 --port 8002
ENTRYPOINT ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8002"]