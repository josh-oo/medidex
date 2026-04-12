import grpc
import os
import embedding_pb2
import embedding_pb2_grpc

import secrets
import asyncio

from dotenv import load_dotenv

load_dotenv()

MODEL_HOST = os.getenv("EMBEDDING_SERVICE_HOST")
MODEL_PORT = os.getenv("EMBEDDING_SERVICE_PORT")

CHANNEL = grpc.aio.insecure_channel(f"{MODEL_HOST}:{MODEL_PORT}")

class EmbeddingService:

    def __init__(self):
        self.channel = CHANNEL
        self.sem = asyncio.Semaphore(1) #max number of concurrent requests

    def get_channel(self):
        return self.channel

    async def embed_report(self, report_id : int, text : str):
        async with self.sem:
            request = embedding_pb2.EmbedReportRequest(id=str(report_id), text=text, authors=[])
            stub = embedding_pb2_grpc.EmbedServiceStub(self.channel)
            call = stub.GetReportEmbedding(request)
            response = await call
            initial_md = await call.initial_metadata()
            metadata = {k: v for k, v in initial_md}
            model_id = metadata['model'].replace("/", "_") + "_" + metadata["revision"]
            result = {"model_id": model_id, "embedding": list(response.embedding.values), "author_embedding": list(response.embedding.values)}
            for i, aspect in enumerate(metadata['aspects'].split(";")):
                result[aspect] = list(response.aspect_embeddings[i].values)
            return result

    async def embed_aspect(self, text : str):
        async with self.sem:
            token = secrets.token_urlsafe(8)
            request = embedding_pb2.EmbedAspectsRequest(id=token, aspects=[text])
            stub = embedding_pb2_grpc.EmbedServiceStub(self.channel)
            call = stub.GetAspectEmbeddings(request)
            response = await call
            initial_md = await call.initial_metadata()
            metadata = {k: v for k, v in initial_md}
            model_id = metadata['model'].replace("/", "_") + "_" + metadata["revision"]
            result = {"model_id": model_id, "embedding": list(response.embedding[0].values)}
            return result

    async def get_metadata(self):
        async with self.sem:
            token = secrets.token_urlsafe(8)
            request = embedding_pb2.EmbedAspectsRequest(id=token, aspects=[])
            stub = embedding_pb2_grpc.EmbedServiceStub(self.channel)
            call = stub.GetAspectEmbeddings(request)
            initial_md = await call.initial_metadata()
            metadata = dict(initial_md)
            return metadata
        
    def readyz(self):
        # Check gRPC embedding service connectivity
        try:
            channel = self.get_channel()
            # Simple connectivity check - channel state
            state = channel.get_state(try_to_connect=True)
            if state == grpc.ChannelConnectivity.READY:
                return {"status": "healthy", "message": "gRPC channel ready"}
            else:
                return {
                    "status": "degraded",
                    "message": f"gRPC channel state: {state.name}"
                }
        except Exception as e:
            return {"status": "unhealthy", "message": f"gRPC error: {str(e)}"}