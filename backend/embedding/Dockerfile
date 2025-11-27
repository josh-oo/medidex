# Stage 1: Compile the .proto file
FROM python:3.11-slim AS model-builder
ARG MODEL_PATH
ARG MODEL_REVISION
ARG MODEL_DTYPE
ARG TOKENIZER_PATH
ARG TOKENIZER_REVISION
ARG ASPECTS

ENV MODEL_PATH=${MODEL_PATH}
ENV MODEL_REVISION=${MODEL_REVISION}
ENV MODEL_DTYPE=${MODEL_DTYPE}
ENV TOKENIZER_PATH=${TOKENIZER_PATH}
ENV TOKENIZER_REVISION=${TOKENIZER_REVISION}
ENV ASPECTS=${ASPECTS}

WORKDIR /model
RUN pip3 install --no-cache-dir grpcio-tools==1.72.1
RUN pip3 install --no-cache-dir transformers==4.52.4
RUN pip3 install --no-cache-dir python-dotenv==1.1.0
RUN pip3 install --no-cache-dir torch==2.7.0

COPY embedding/model_loader.py .
RUN python model_loader.py

COPY tools/utils/embedding.proto .
RUN python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. embedding.proto

# Stage 2: Main app
FROM python:3.11-slim

RUN groupadd -r appgroup && useradd -r -g appgroup appuser

ENV PYTHONDONTWRITEBYTECODE 1

WORKDIR /app

#RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

COPY embedding/requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

COPY embedding/model_server.py .

# 👇 Copy compiled model files from the builder stage
COPY --from=model-builder /model/embedding_pb2.py .
COPY --from=model-builder /model/embedding_pb2_grpc.py .
COPY --from=model-builder /model/tokenizer/tokenizer.json .
COPY --from=model-builder /model/traced_model.pt .

EXPOSE 50051

# Switch to the non-root user before running the application
USER appuser

ENTRYPOINT ["python3", "model_server.py"]
