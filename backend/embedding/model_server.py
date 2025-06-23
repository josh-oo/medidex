from tokenizers import Tokenizer
from dotenv import load_dotenv
import torch

import embedding_pb2
import embedding_pb2_grpc
from concurrent import futures
import os

import grpc
from grpc_health.v1 import health
from grpc_health.v1 import health_pb2
from grpc_health.v1 import health_pb2_grpc

load_dotenv()

MODEL_PATH = os.getenv("MODEL_PATH")
MODEL_REVISION = os.getenv("MODEL_REVISION")
MODEL_DIM = os.getenv("MODEL_DIM")
ASPECTS = os.getenv("ASPECTS").split(",")

class EmbedServiceServicer(embedding_pb2_grpc.EmbedServiceServicer):
    def __init__(self):
        self.device = (
            "cuda" if torch.cuda.is_available()
            else "mps" if torch.backends.mps.is_available()
            else "cpu"
        )
        self.tokenizer = Tokenizer.from_file("tokenizer.json")
        self.tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")  # Replace with correct pad_token if needed
        self.tokenizer.enable_truncation(max_length=512)

        self.model = torch.jit.load("traced_model.pt")
        self.model = self.model.to(self.device)

    def get_embeddings(self, texts, return_aspects=True):
        prefix = ""
        if return_aspects:
            prefix = "".join(["<" + aspect + ">" for aspect in ASPECTS])

        texts = [prefix + text for text in texts]
        encoded_batch = self.tokenizer.encode_batch(texts)

        # Extract input_ids and attention_mask with uniform lengths
        input_ids = [enc.ids for enc in encoded_batch]
        attention_mask = [enc.attention_mask for enc in encoded_batch]

        # Convert to tensors
        input_ids_tensor = torch.tensor(input_ids).to(self.device)
        attention_mask_tensor = torch.tensor(attention_mask).to(self.device)

        with torch.inference_mode():
            last_hidden_states, pooling = self.model(input_ids_tensor, attention_mask_tensor)

        embeddings = last_hidden_states[:, 0]

        if not return_aspects:
            return embeddings

        aspects = last_hidden_states[:, 1:1 + len(ASPECTS)]

        return embeddings, aspects
    
    def GetEmbedding(self, request_iterator, context):
        context.send_initial_metadata((
            ('model', MODEL_PATH),
            ('revision', MODEL_REVISION),
            ('aspects', None),
            ('dimension', str(MODEL_DIM))
        ))

        def yield_embeddings(id, texts):
            embedding = self.get_embeddings(texts, return_aspects=False)
            batch_embeddings = []
            for emb in embedding:
                batch_embeddings.append(embedding_pb2.EmbeddingVector(values=emb.tolist()))
            return embedding_pb2.EmbedResponse(id=id, embedding=batch_embeddings)

        for request in request_iterator:
            yield yield_embeddings(request.id, request.text)

    def GetEmbeddingAspects(self, request_iterator, context):
        context.send_initial_metadata((
            ('model', MODEL_PATH),
            ('revision', MODEL_REVISION),
            ('aspects', ";".join(ASPECTS)),
            ('dimension', str(MODEL_DIM))
        ))

        def yield_embeddings(id, texts):
            embedding, aspect_embeddings = self.get_embeddings(texts)
            batch_embeddings = []
            batch_aspect_embeddings = []
            for i, emb in enumerate(embedding):
                batch_embeddings.append(embedding_pb2.EmbeddingVector(values=emb.tolist()))
                aspect_vector = embedding_pb2.AspectVectors(
                    aspect_embeddings=[
                        embedding_pb2.EmbeddingVector(values=aspect.tolist())
                        for aspect in aspect_embeddings[i]
                    ]
                )
                batch_aspect_embeddings.append(aspect_vector)                  
            return embedding_pb2.EmbedResponseAspects(
                id=id,
                embedding=batch_embeddings,
                aspect_embeddings=batch_aspect_embeddings,
            )

        for request in request_iterator:
            yield yield_embeddings(request.id, request.text)

def _configure_health_server(server: grpc.Server):
    health_servicer = health.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)

    # This must match the service name used in grpc_health_probe or other health clients
    health_servicer.set("embed.EmbedService", health_pb2.HealthCheckResponse.SERVING)
    health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)  # for default check

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    embedding_pb2_grpc.add_EmbedServiceServicer_to_server(EmbedServiceServicer(), server)
    server.add_insecure_port('[::]:50051')
    _configure_health_server(server)
    server.start()
    server.wait_for_termination()

if __name__ == "__main__":
    serve()