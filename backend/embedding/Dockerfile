# Stage 1: Compile the .proto file
FROM python:3.13-slim AS model-builder
ARG EMBEDDING_MODEL_PATH
ARG EMBEDDING_MODEL_REVISION
ARG EMBEDDING_MODEL_DTYPE
ARG EMBEDDING_MODEL_TOKENIZER_PATH
ARG EMBEDDING_MODEL_TOKENIZER_REVISION
ARG EMBEDDING_MODEL_ASPECTS

ENV EMBEDDING_MODEL_PATH=${EMBEDDING_MODEL_PATH}
ENV EMBEDDING_MODEL_REVISION=${EMBEDDING_MODEL_REVISION}
ENV EMBEDDING_MODEL_DTYPE=${EMBEDDING_MODEL_DTYPE}
ENV EMBEDDING_MODEL_TOKENIZER_PATH=${EMBEDDING_MODEL_TOKENIZER_PATH}
ENV EMBEDDING_MODEL_TOKENIZER_REVISION=${EMBEDDING_MODEL_TOKENIZER_REVISION}
ENV EMBEDDING_MODEL_ASPECTS=${EMBEDDING_MODEL_ASPECTS}

WORKDIR /model
RUN pip3 install --no-cache-dir grpcio-tools==1.72.1
RUN pip3 install --no-cache-dir transformers==4.52.4
RUN pip3 install --no-cache-dir python-dotenv==1.1.0
RUN pip3 install --no-cache-dir torch==2.9.1 --index-url https://download.pytorch.org/whl/cpu

COPY embedding/model_loader.py .
RUN python model_loader.py

COPY tools/utils/embedding.proto .
RUN python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. embedding.proto

# Stage 2: Main app
FROM python:3.13-slim

RUN groupadd -r appgroup && useradd -r -g appgroup appuser

ENV PYTHONDONTWRITEBYTECODE 1

ENV OMP_NUM_THREADS=4
ENV MKL_NUM_THREADS=4
ENV TOKENIZERS_PARALLELISM=false

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
