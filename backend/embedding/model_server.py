from tokenizers import Tokenizer
from dotenv import load_dotenv
import numpy as np
import onnxruntime as ort

import embedding_pb2
import embedding_pb2_grpc
import os

import grpc
from grpc_health.v1 import health
from grpc_health.v1 import health_pb2
from grpc_health.v1 import health_pb2_grpc

import html
import unicodedata
from bs4 import BeautifulSoup

import asyncio

load_dotenv()

MODEL_PATH = os.getenv("EMBEDDING_MODEL_PATH")
MODEL_REVISION = os.getenv("EMBEDDING_MODEL_REVISION")
MODEL_DIM = os.getenv("EMBEDDING_MODEL_DIM")
MODEL_MAX_INPUT_LENGTH = int(os.getenv("EMBEDDING_MODEL_MAX_INPUT_LENGTH"))
ASPECTS = os.getenv("EMBEDDING_MODEL_ASPECTS").split(",")

TOKENIZER = Tokenizer.from_file("tokenizer.json")
TOKENIZER.enable_padding(pad_id=0, pad_token="[PAD]")  # Replace with correct pad_token if needed
TOKENIZER.enable_truncation(max_length=MODEL_MAX_INPUT_LENGTH)

options = ort.SessionOptions()
options.enable_mem_pattern = False
options.enable_cpu_mem_arena = False
options.enable_mem_reuse = False

ONNX_SESSION = ort.InferenceSession("model.onnx", sess_options=options, providers=["CPUExecutionProvider"])

class EmbedServiceServicer(embedding_pb2_grpc.EmbedServiceServicer):
    def __init__(self):
        self.tokenizer = TOKENIZER
        self.onnx_session = ONNX_SESSION

    async def preprocess(self, text):
        def _preprocess(text):
            utf8_string = html.unescape(text)
            utf8_string = utf8_string.replace('\r', '\n')
            utf8_string = utf8_string.replace('\n', ' ')

            soup = BeautifulSoup(utf8_string, "lxml")
            utf8_string = soup.get_text(separator='')

            utf8_string = ' '.join(utf8_string.split())
            normalized_text = unicodedata.normalize("NFKC", utf8_string)
            return normalized_text
        return await asyncio.to_thread(_preprocess, text)

    def get_embeddings(self, texts, return_aspects=True):
        prefix = ""
        if return_aspects:
            prefix = "".join(["<" + aspect + ">" for aspect in ASPECTS])

        texts = [prefix + text for text in texts]
        encoded_batch = self.tokenizer.encode_batch(texts)

        # Extract input_ids and attention_mask with uniform lengths
        input_ids = [enc.ids for enc in encoded_batch]
        attention_mask = [enc.attention_mask for enc in encoded_batch]

        # Convert to numpy arrays for ONNX
        input_ids_np = np.array(input_ids, dtype=np.int64)
        attention_mask_np = np.array(attention_mask, dtype=np.int64)

        # ONNX inference
        ort_inputs = {
            "input_ids": input_ids_np,
            "attention_mask": attention_mask_np
        }
        ort_outs = self.onnx_session.run(None, ort_inputs)
        last_hidden_states = ort_outs[0]  # This is a numpy array

        embeddings = last_hidden_states[:, 0]

        if not return_aspects:
            return embeddings

        aspects = last_hidden_states[:, 1:1 + len(ASPECTS)]

        return embeddings, aspects
    
    async def GetAspectEmbeddings(self, request, context):
        await context.send_initial_metadata((
            ('model', MODEL_PATH),
            ('revision', MODEL_REVISION),
            ('aspects', None),
            ('dimension', str(MODEL_DIM))
        ))

        texts = await asyncio.gather(*[self.preprocess(text) for text in request.aspects])
        embedding = self.get_embeddings(texts, return_aspects=False)
        batch_embeddings = [embedding_pb2.EmbeddingVector(values=emb.tolist()) for emb in embedding]
        return embedding_pb2.EmbedResponseAspects(id=request.id, embedding=batch_embeddings)

    async def GetReportEmbedding(self, request, context):
        await context.send_initial_metadata((
            ('model', MODEL_PATH),
            ('revision', MODEL_REVISION),
            ('aspects', ";".join(ASPECTS)),
            ('dimension', str(MODEL_DIM))
        ))

        text = await self.preprocess(request.text)
        embeddings, aspect_embeddings = self.get_embeddings([text])

        embedding_val = embeddings[0]
        aspect_embeddings_val = aspect_embeddings[0]
        aspect_embeddings_proto = [embedding_pb2.EmbeddingVector(values=aspect.tolist()) for aspect in aspect_embeddings_val]
        response = embedding_pb2.EmbedResponseReport(
            id=request.id,
            embedding=embedding_pb2.EmbeddingVector(values=embedding_val.tolist()),
            aspect_embeddings=aspect_embeddings_proto
        )

        return response

async def _configure_health_server(server: grpc.Server):
    health_servicer = health.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)

    # This must match the service name used in grpc_health_probe or other health clients
    health_servicer.set("embed.EmbedService", health_pb2.HealthCheckResponse.SERVING)
    health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)  # for default check

async def serve():
    server = grpc.aio.server()
    embedding_pb2_grpc.add_EmbedServiceServicer_to_server(EmbedServiceServicer(), server)
    server.add_insecure_port('[::]:50051')
    await _configure_health_server(server)
    await server.start()
    await server.wait_for_termination()

if __name__ == "__main__":
    asyncio.run(serve())