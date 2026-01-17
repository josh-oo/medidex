from qdrant_client import models
from qdrant_client.http.models import PointStruct
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Filter, FieldCondition, DatetimeRange

from dotenv import load_dotenv
import os
import numpy as np
from typing import List, Any, Optional

from datetime import datetime, timezone

from .embedding import EmbeddingService

load_dotenv()

VECTORSTORE_HOST = os.getenv("VECTORSTORE_SERVICE_HOST")
VECTORSTORE_PORT = os.getenv("VECTORSTORE_SERVICE_PORT")
COLLECTION_NAME = os.getenv("VECTORSTORE_COLLECTION_NAME")

CLIENT = AsyncQdrantClient(
    host=VECTORSTORE_HOST, 
    grpc_port=VECTORSTORE_PORT, 
    prefer_grpc=True
)

def transform_to_uuid(id, tag="0000"):
    id = str(id).lower()
    missing_zeros = 12 - len(id)
    id = "0"*missing_zeros + id
    return f"00000000-{tag}-4000-a000-{id}"

def transform_to_crg_report_id(uuid):
    return int(uuid.split("-")[-1])

class VectorstoreService():

    def __init__(self, user_id : str, embedding_service : EmbeddingService):
        self.client = CLIENT
        self.user_id = user_id
        self.embedding_service = embedding_service

    async def get_collections(self):
        return await self.client.get_collections()

    async def get_all_saved_crg_report_ids(self):
        """
        Remove orphan nodes from vectorstore - delete points whose source_id 
        doesn't exist in the Meerkat database anymore.
        """
        # Get all points with their source_id from vectorstore
        scroll_result = await self.client.scroll(
            collection_name=COLLECTION_NAME ,
            limit=10000,  # Adjust based on your collection size
            with_payload=['source_id'],
            with_vectors=False,
        )
        
        all_points = scroll_result[0]
        offset = scroll_result[1]
        
        # Continue scrolling if there are more points
        while offset is not None:
            scroll_result = await self.client.scroll(
                collection_name=COLLECTION_NAME ,
                limit=10000,
                offset=offset,
                with_payload=['source_id'],
                with_vectors=False,
            )
            all_points.extend(scroll_result[0])
            offset = scroll_result[1]
        
        # Extract source_ids from vectorstore
        vectorstore_source_ids = set()
        for point in all_points:
            if point.payload and 'source_id' in point.payload:
                vectorstore_source_ids.add(point.payload['source_id'])
        
        return vectorstore_source_ids

    async def link_report_to_study_ids(self, crg_report_id : int, study_ids : List[int], user : str):
        field = "belongs_to_study"
        if user:
            field = "temporary"
            study_ids = {user: {'belongs_to_study': study_ids}}
        await self.client.set_payload(
            collection_name=COLLECTION_NAME,
            payload={field: study_ids},
            points=[transform_to_uuid(crg_report_id)],
        )

    async def get_vectors_by_crg_report_id(self, crg_report_id : int):
        point_id = transform_to_uuid(crg_report_id)
        result = await self.client.retrieve(
            collection_name=COLLECTION_NAME ,
            ids=[point_id],
            with_vectors=True,
            with_payload=False,
        )
        return result[0].vector

    async def crg_reports_exist(self, crg_report_ids : int):
        point_ids = [transform_to_uuid(crg_report_id) for crg_report_id in crg_report_ids]
        result = await self.client.retrieve(
            collection_name=COLLECTION_NAME,
            ids=point_ids,
            with_vectors=False,
            with_payload=False,
        )
        if not result:
            return 0
        return len(result)

    async def calculate_score_pairs(self, crg_report_ids : List[int]):
        # Fetch all vectors
        point_ids = [transform_to_uuid(crg_report_id) for crg_report_id in crg_report_ids]
        results = await self.client.retrieve(
            collection_name=COLLECTION_NAME,
            ids=point_ids,
            with_vectors=True,
            with_payload=False,
        )
        vectors = np.array([point.vector['default'] for point in results])
        # Compute cosine similarity matrix
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        normalized = vectors / norms
        similarity_matrix = np.dot(normalized, normalized.T)
        # Return as list of (i, j, score) tuples
        pairs = []
        n = len(crg_report_ids)
        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                pairs.append((crg_report_ids[i], crg_report_ids[j], float(similarity_matrix[i, j])))
        return pairs


    async def delete_vectors_by_crg_report_ids(self, crg_report_ids : List[int]):
        ids = [transform_to_uuid(crg_report_id) for crg_report_id in crg_report_ids]
        await self.client.delete(
            collection_name=COLLECTION_NAME ,
            points_selector=models.PointIdsList(
                points=ids,
            )
    )

    async def add_report_to_vectorstore(self, report):
        title = report.Title
        abstract = report.Abstract
        authors = [item.strip() for item in report.Authors.split("//")]

        text_to_process = []
        if title:
            text_to_process.append(title)
        if abstract:
            text_to_process.append(abstract)
        text_to_process = "\n".join(text_to_process)
    
        vectors = await self.embedding_service.embed_report(text_to_process)
        #TODO maybe the batch is already deleted, then this vector should not be added

        new_id = transform_to_uuid(report.CRGReportID)
        payload = {
            'title': title,
            'abstract': abstract,
            'source_id': report.CRGReportID,
            'authors': authors,
            'date_entered': datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            'belongs_to_study': [],
            'belongs_to_trial_id': False,
            'temporary': {},
        }
        new_vectors = {"default": vectors.pop("embedding"), "authors": vectors.pop("author_embedding")}
        for key, value in vectors.items():
            new_vectors[key] = value

        new_vectors.pop("model_id")

        points = [PointStruct(id=new_id,vector=new_vectors, payload=payload)]
        await self.client.upsert(wait=True, collection_name=COLLECTION_NAME, points=points)

    async def search_report(self, query : Any, aspect : str ,k : int, filter : Any):
        return await self.client.query_points_groups(
                collection_name=COLLECTION_NAME,
                query=query,
                using=aspect,
                group_by="belongs_to_study",  # Path of the field to group by
                limit=k,  # Max amount of groups
                group_size=1,  # Max amount of points per group
                query_filter=filter,
                with_payload=["belongs_to_study", f"temporary.{self.user_id}.belongs_to_study", "title", "authors", "source_id"],
            )
    
    async def get_similar_tags(self, embedding : List[float], sources: List[str], aspect: str, k: int):
    
        #TODO implement more sophisticated tree based search here

        filters = []
        if "mesh" in sources:
            filters.append(models.FieldCondition(key="source", match=models.MatchValue(value="mesh")))

        if "meerkat" in sources:
            filters.append(models.Filter(
                must=[
                    models.FieldCondition(key="source", match=models.MatchValue(value="meerkat")),
                    models.FieldCondition(
                        key="tree_ids",
                        match=models.MatchAny(any=[aspect]), #TODO check if it as the same as aspect name
                    )
                ]
            ))

        filter = models.Filter(should=filters)

        search_results = await self.client.query_points(
            collection_name=COLLECTION_NAME + "_tags",
            query=embedding,
            limit=k,
            query_filter=filter,
        )

        results = {'ID': [], 'Keyword':[], 'Relevance': []}

        for result in search_results.points:
            results['ID'].append(result.payload['source_id'])
            results['Keyword'].append(result.payload['display_name'])
            results['Relevance'].append(str(round(result.score * 100)) + "%")

        return results
    
    async def score_tags(self, embedding : List[float], tag_ids : List[int], aspect : str):
        tag_filter = models.Filter(
            must=[
                models.FieldCondition(key="source", match=models.MatchValue(value="meerkat")),
                models.FieldCondition(key="tree_ids",match=models.MatchAny(any=[aspect])),
                models.FieldCondition(key="source_id",match=models.MatchAny(any=[str(item) for item in tag_ids]))
            ]
        )

        result = await self.client.query_points(
            collection_name=COLLECTION_NAME + "_tags",
            query=embedding,
            limit=len(tag_ids),
            query_filter=tag_filter,
        )

        related_tags = []
        for point in result.points:
            item = {}
            item['id'] = int(point.payload['source_id'])
            item['score'] = point.score
            related_tags.append(item)

        return related_tags
    
    async def recommendation_query_builder(self, report_id : int, negative_reports : Optional[List[int]]):

        if not negative_reports:
            negative_reports = []
        
        positive_ids = [transform_to_uuid(report_id)]
        negative_ids = [transform_to_uuid(negative_id) for negative_id in negative_reports]

        return models.RecommendQuery(
                    recommend=models.RecommendInput(
                        positive=positive_ids,
                        negative=negative_ids,
                        strategy=models.RecommendStrategy.AVERAGE_VECTOR,
                    )
                )
    
    async def search_similar_studies(self, query : Any, aspect : str, k : int, cutoff : str, excluded_studies : List[int], exclude_trial_related_studies : bool):


        filters = []
        if cutoff:
            filters.append(Filter(
                must=[
                    FieldCondition(key="date_entered",range=DatetimeRange(lt=datetime.fromisoformat(cutoff)))
                ]
            ))    

        if len(excluded_studies) > 0:
                
            if exclude_trial_related_studies:
                filters.append(
                    Filter(
                        must=[
                            models.FieldCondition(
                                key="belongs_to_trial_id",
                                match=models.MatchValue(value=False)
                            )
                        ],
                    )
                )
            filters.append(
                    Filter(
                        must_not=[
                            models.FieldCondition(
                                key="belongs_to_study",
                                match=models.MatchAny(any=excluded_studies)
                            )
                        ]
                    )
                )
        
        filter = models.Filter(must=filters)
    
        search_results = await self.search_report(query,aspect,k,filter)

        return search_results.groups