import grpc
import os
import embedding_pb2
import embedding_pb2_grpc

import secrets

from dotenv import load_dotenv

load_dotenv()

MODEL_HOST = os.getenv("EMBEDDING_SERVICE_HOST")
MODEL_PORT = os.getenv("EMBEDDING_SERVICE_PORT")

CHANNEL = grpc.aio.insecure_channel(f"{MODEL_HOST}:{MODEL_PORT}")

async def single_element_generator(element):
    yield element

class EmbeddingService:

    def __init__(self):
        self.channel = CHANNEL

    def get_grpc_channel(self):
        return self.channel

    async def embed_report(self, text : str):
        token = secrets.token_urlsafe(8)

        request = embedding_pb2.EmbedReportRequest(id=token, text=text, authors=[])

        stub = embedding_pb2_grpc.EmbedServiceStub(self.channel)

        responses = stub.GetReportEmbedding(single_element_generator(request))

        metadata = {k: v for k, v in (await responses.initial_metadata())}

        model_id = metadata['model'].replace("/", "_") + "_" + metadata["revision"]

        response = await responses.read()

        result = {"model_id": model_id, "embedding": list(response.embedding.values), "author_embedding": list(response.embedding.values)}
        for i, aspect in enumerate(metadata['aspects'].split(";")):
            result[aspect] = list(response.aspect_embeddings[i].values)

        return result

    async def embed_aspect(self, text : str):
        token = secrets.token_urlsafe(8)

        request = embedding_pb2.EmbedAspectsRequest(id=token, aspects=[text])

        stub = embedding_pb2_grpc.EmbedServiceStub(self.channel)

        responses = stub.GetAspectEmbeddings(single_element_generator(request))

        metadata = {k: v for k, v in (await responses.initial_metadata())}

        model_id = metadata['model'].replace("/", "_") + "_" + metadata["revision"]

        response = await responses.read()

        result = {"model_id": model_id, "embedding": list(response.embedding[0].values)}

        return result

    async def get_metadata(self):
        token = secrets.token_urlsafe(8)

        request = embedding_pb2.EmbedAspectsRequest(id=token, aspects=[])

        stub = embedding_pb2_grpc.EmbedServiceStub(self.channel)

        responses = stub.GetAspectEmbeddings(single_element_generator(request))

        metadata = {k: v for k, v in (await responses.initial_metadata())}

        return metadata