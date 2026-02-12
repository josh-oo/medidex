# Stage 1: Compile the .proto file
FROM python:3.13.11-slim AS model-builder
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
RUN pip3 install --no-cache-dir grpcio-tools==1.76.0 transformers==4.52.4 python-dotenv==1.1.0 onnxscript==0.6.2&& \
    pip3 install --no-cache-dir torch==2.10.0 --index-url https://download.pytorch.org/whl/cpu

COPY embedding/model_loader.py .
RUN python model_loader.py

COPY tools/utils/embedding.proto .
RUN python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. embedding.proto

# Stage 2: Main app
FROM python:3.13.11-slim

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
COPY --from=model-builder /model/model.onnx .
COPY --from=model-builder /model/model.onnx.data .

EXPOSE 50051

# Switch to the non-root user before running the application
USER appuser

ENTRYPOINT ["python3", "-u", "model_server.py"]
