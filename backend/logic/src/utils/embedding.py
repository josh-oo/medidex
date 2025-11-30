import embedding_pb2
import embedding_pb2_grpc

import secrets

async def single_element_generator(element):
    yield element

async def _embed_report(text : str, channel):
    token = secrets.token_urlsafe(8)

    request = embedding_pb2.EmbedReportRequest(id=token, text=text, authors=[])

    stub = embedding_pb2_grpc.EmbedServiceStub(channel)

    responses = stub.GetReportEmbedding(single_element_generator(request))

    metadata = {k: v for k, v in (await responses.initial_metadata())}

    model_id = metadata['model'].replace("/", "_") + "_" + metadata["revision"]

    response = await responses.read()

    result = {"model_id": model_id, "embedding": list(response.embedding.values), "author_embedding": list(response.embedding.values)}
    for i, aspect in enumerate(metadata['aspects'].split(";")):
        result[aspect] = list(response.aspect_embeddings[i].values)

    return result

async def _embed_aspect(text : str, channel):
    token = secrets.token_urlsafe(8)

    request = embedding_pb2.EmbedAspectsRequest(id=token, aspects=[text])

    stub = embedding_pb2_grpc.EmbedServiceStub(channel)

    responses = stub.GetAspectEmbeddings(single_element_generator(request))

    metadata = {k: v for k, v in (await responses.initial_metadata())}

    model_id = metadata['model'].replace("/", "_") + "_" + metadata["revision"]

    response = await responses.read()

    result = {"model_id": model_id, "embedding": list(response.embedding[0].values)}

    return result

async def get_metadata(channel):
    token = secrets.token_urlsafe(8)

    request = embedding_pb2.EmbedAspectsRequest(id=token, aspects=[])

    stub = embedding_pb2_grpc.EmbedServiceStub(channel)

    responses = stub.GetAspectEmbeddings(single_element_generator(request))

    metadata = {k: v for k, v in (await responses.initial_metadata())}

    return metadata