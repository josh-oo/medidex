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

import html
import unicodedata
from bs4 import BeautifulSoup

load_dotenv()

MODEL_PATH = os.getenv("EMBEDDING_MODEL_PATH")
MODEL_REVISION = os.getenv("EMBEDDING_MODEL_REVISION")
MODEL_DIM = os.getenv("EMBEDDING_MODEL_DIM")
MODEL_MAX_INPUT_LENGTH = int(os.getenv("EMBEDDING_MODEL_MAX_INPUT_LENGTH"))
ASPECTS = os.getenv("EMBEDDING_MODEL_ASPECTS").split(",")

class EmbedServiceServicer(embedding_pb2_grpc.EmbedServiceServicer):
    def __init__(self):
        self.device = (
            "cuda" if torch.cuda.is_available()
            else "mps" if torch.backends.mps.is_available()
            else "cpu"
        )
        self.tokenizer = Tokenizer.from_file("tokenizer.json")
        self.tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")  # Replace with correct pad_token if needed
        self.tokenizer.enable_truncation(max_length=MODEL_MAX_INPUT_LENGTH)

        self.model = torch.jit.load("traced_model.pt")
        self.model = self.model.to(self.device)

    def preprocess(self, text):

        utf8_string = html.unescape(text)
        utf8_string = utf8_string.replace('\r', '\n')
        utf8_string = utf8_string.replace('\n', ' ')

        soup = BeautifulSoup(utf8_string, "html.parser")
        utf8_string = soup.get_text(separator='')

        utf8_string = ' '.join(utf8_string.split())
        normalized_text = unicodedata.normalize("NFKC", utf8_string)
        return normalized_text

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
    
    def GetAspectEmbeddings(self, request_iterator, context):
        context.send_initial_metadata((
            ('model', MODEL_PATH),
            ('revision', MODEL_REVISION),
            ('aspects', None),
            ('dimension', str(MODEL_DIM))
        ))

        def yield_embeddings(id, texts):
            texts = [self.preprocess(text) for text in texts]
            embedding = self.get_embeddings(texts, return_aspects=False)
            batch_embeddings = [embedding_pb2.EmbeddingVector(values=emb.tolist()) for emb in embedding]
            return embedding_pb2.EmbedResponseAspects(id=id, embedding=batch_embeddings)

        for request in request_iterator:
            yield yield_embeddings(request.id, request.aspects)

    def GetReportEmbedding(self, request_iterator, context):
        context.send_initial_metadata((
            ('model', MODEL_PATH),
            ('revision', MODEL_REVISION),
            ('aspects', ";".join(ASPECTS)),
            ('dimension', str(MODEL_DIM))
        ))

        def yield_embeddings(id, text, authors=[]):
            text = self.preprocess(text)
            embedding, aspect_embeddings = self.get_embeddings([text])
            author_embeddings = torch.zeros(embedding[0].shape[0])
            if len(authors) > 0:
                author_embeddings = self.get_embeddings(authors, return_aspects=False)
                author_embeddings = author_embeddings.mean(dim=0)

            embedding = embedding[0]
            aspect_embeddings = aspect_embeddings[0]
            
            aspect_embeddings = [embedding_pb2.EmbeddingVector(values=aspect.tolist())for aspect in aspect_embeddings]
            author_embeddings = embedding_pb2.EmbeddingVector(values=author_embeddings.tolist())
            #author_embeddings = [embedding_pb2.EmbeddingVector(values=author.tolist())for author in author_embeddings]

            return embedding_pb2.EmbedResponseReport(
                id=id,
                embedding=embedding_pb2.EmbeddingVector(values=embedding.tolist()),
                aspect_embeddings=aspect_embeddings,
                author_embeddings=author_embeddings
            )

        for request in request_iterator:
            yield yield_embeddings(request.id, request.text, request.authors)

def _configure_health_server(server: grpc.Server):
    health_servicer = health.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)

    # This must match the service name used in grpc_health_probe or other health clients
    health_servicer.set("embed.EmbedService", health_pb2.HealthCheckResponse.SERVING)
    health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)  # for default check

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    embedding_pb2_grpc.add_EmbedServiceServicer_to_server(EmbedServiceServicer(), server)
    server.add_insecure_port('[::]:50051')
    _configure_health_server(server)
    server.start()
    server.wait_for_termination()

if __name__ == "__main__":
    serve()