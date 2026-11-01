from qdrant_client import models
from qdrant_client.http.models import PointStruct
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Filter, FieldCondition, DatetimeRange

from dotenv import load_dotenv
import json
import os
import re
import numpy as np
from typing import List, Any, Optional, Dict, Set, Tuple

from src.utils.dto import TagCandidate

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

def transform_to_report_id(uuid):
    return int(uuid.split("-")[-1])

class VectorstoreService():
    # The payload field with the studies of one database that a report point belongs to (beside
    # `belongs_to_study`, which holds those of every database). The study search of a database groups by it, so
    # it only ever finds studies of that database.
    DATABASE_FIELD = "database_{}_studies"
    DATABASE_FIELD_PATTERN = re.compile(r"^database_\d+_studies$")

    def __init__(self, user_id : str, embedding_service : EmbeddingService):
        self.client = CLIENT
        self.user_id = user_id
        self.embedding_service = embedding_service

    @classmethod
    def database_field(cls, database_id: Optional[int]) -> str:
        """The field a study search groups by: that of the database, `belongs_to_study` for all databases."""
        return "belongs_to_study" if database_id is None else cls.DATABASE_FIELD.format(database_id)

    @classmethod
    def database_payload(cls, study_ids: List[int], study_databases: Dict[int, int]) -> Dict[str, List[int]]:
        """The database fields of a report point linked to `study_ids`, given the database of each study."""
        payload: Dict[str, List[int]] = {}
        for study_id in study_ids:
            if study_id in study_databases:
                payload.setdefault(cls.database_field(study_databases[study_id]), []).append(study_id)
        return payload

    async def get_collections(self):
        return await self.client.get_collections()

    async def get_all_saved_report_ids(self):
        """
        Remove orphan nodes from vectorstore - delete points whose source_id 
        doesn't exist in the database anymore.
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

    async def get_point_ids(self) -> Set[str]:
        """The ids of every point of the collection."""
        ids: Set[str] = set()
        offset = None
        while True:
            points, offset = await self.client.scroll(
                collection_name=COLLECTION_NAME, limit=10000, offset=offset, with_payload=False, with_vectors=False,
            )
            ids.update(str(point.id) for point in points)
            if offset is None:
                return ids

    async def upsert_points(self, points: List[Tuple[str, List[float], Dict[str, Any]]]) -> None:
        """Adds (or replaces) points given as (id, vector, payload)."""
        if points:
            await self.client.upsert(
                collection_name=COLLECTION_NAME, wait=True,
                points=[PointStruct(id=point_id, vector=vector, payload=payload) for point_id, vector, payload in points],
            )

    async def delete_points(self, point_ids: List[str]) -> None:
        if point_ids:
            await self.client.delete(collection_name=COLLECTION_NAME, points_selector=models.PointIdsList(points=point_ids))

    async def link_report_to_study_ids(self, report_id : int, study_ids : List[int], user : str):
        field = "belongs_to_study"
        if user:
            field = "temporary"
            study_ids = {user: {'belongs_to_study': study_ids}}
        await self.client.set_payload(
            collection_name=COLLECTION_NAME,
            payload={field: study_ids},
            points=[transform_to_uuid(report_id)],
        )

    async def link_report_to_study_id(self, report_id : int, study_id : int, database_id : int, user : str):
        point_id = transform_to_uuid(report_id)
        result = await self.client.retrieve(
            collection_name=COLLECTION_NAME,
            ids=[point_id],
            with_vectors=False,
            with_payload=True,
        )

        payload = result[0].payload if result else {}
        update_payload: Dict[str, Any] = {}

        if user:
            temporary_payload = dict(payload.get("temporary") or {})
            user_payload = dict(temporary_payload.get(user) or {})
            study_list = list(user_payload.get("belongs_to_study") or [])
            if study_id not in study_list:
                study_list.append(study_id)
            user_payload["belongs_to_study"] = study_list
            temporary_payload[user] = user_payload
            update_payload["temporary"] = temporary_payload
        else:
            study_list = list(payload.get("belongs_to_study") or [])
            if study_id not in study_list:
                study_list.append(study_id)
            update_payload["belongs_to_study"] = study_list
            field = self.database_field(database_id)
            database_list = list(payload.get(field) or [])
            if study_id not in database_list:
                database_list.append(study_id)
            update_payload[field] = database_list

        if update_payload:
            await self.client.set_payload(
                collection_name=COLLECTION_NAME,
                payload=update_payload,
                points=[point_id],
            )

    async def unlink_report_from_study_id(self, report_id : int, study_id : int, user : str):
        point_id = transform_to_uuid(report_id)
        result = await self.client.retrieve(
            collection_name=COLLECTION_NAME,
            ids=[point_id],
            with_vectors=False,
            with_payload=True,
        )

        if not result:
            return

        payload = result[0].payload or {}
        update_payload: Dict[str, Any] = {}

        if user:
            temporary_payload = dict(payload.get("temporary") or {})
            user_payload = dict(temporary_payload.get(user) or {})
            study_list = list(user_payload.get("belongs_to_study") or [])
            if study_id in study_list:
                study_list = [sid for sid in study_list if sid != study_id]
                if study_list:
                    user_payload["belongs_to_study"] = study_list
                    temporary_payload[user] = user_payload
                else:
                    user_payload.pop("belongs_to_study", None)
                    if user_payload:
                        temporary_payload[user] = user_payload
                    else:
                        temporary_payload.pop(user, None)
                update_payload["temporary"] = temporary_payload
        else:
            study_list = list(payload.get("belongs_to_study") or [])
            if study_id in study_list:
                study_list = [sid for sid in study_list if sid != study_id]
                update_payload["belongs_to_study"] = study_list
            # The study is in one database, whose field the payload names.
            for field, database_list in payload.items():
                if self.DATABASE_FIELD_PATTERN.match(field) and study_id in (database_list or []):
                    update_payload[field] = [sid for sid in database_list if sid != study_id]

        if update_payload:
            await self.client.set_payload(
                collection_name=COLLECTION_NAME,
                payload=update_payload,
                points=[point_id],
            )

    async def get_vectors_by_report_id(self, report_id : int):
        point_id = transform_to_uuid(report_id)
        result = await self.client.retrieve(
            collection_name=COLLECTION_NAME ,
            ids=[point_id],
            with_vectors=True,
            with_payload=False,
        )
        return result[0].vector

    async def reports_exist(self, report_ids: List[int]) -> List[int]:
        report_ids = report_ids or []
        if not report_ids:
            return []

        point_ids = [transform_to_uuid(report_id) for report_id in report_ids]
        result = await self.client.retrieve(
            collection_name=COLLECTION_NAME,
            ids=point_ids,
            with_vectors=False,
            with_payload=False,
        )

        if not result:
            return []

        existing_ids: List[int] = []
        for point in result:
            point_id = getattr(point, "id", None)
            if not point_id:
                continue
            existing_ids.append(transform_to_report_id(str(point_id)))

        return existing_ids

    async def usage(self, report_ids: List[int], chunk: int = 1000) -> Tuple[int, int]:
        """How many of the reports have a point, and about how many bytes they take: their vectors as float32 and their
        payloads as JSON (the index of the collection not included)."""
        vectors = (await self.client.get_collection(COLLECTION_NAME)).config.params.vectors
        dimensions = sum(params.size for params in vectors.values()) if isinstance(vectors, dict) else vectors.size
        points = payload_bytes = 0
        for start in range(0, len(report_ids), chunk):
            found = await self.client.retrieve(
                collection_name=COLLECTION_NAME,
                ids=[transform_to_uuid(report_id) for report_id in report_ids[start:start + chunk]],
                with_vectors=False,
                with_payload=True,
            )
            points += len(found)
            payload_bytes += sum(len(json.dumps(point.payload or {}, ensure_ascii=False).encode()) for point in found)
        return points, points * dimensions * 4 + payload_bytes

    async def calculate_score_pairs(self, report_ids : List[int]):
        # Fetch all vectors
        point_ids = [transform_to_uuid(report_id) for report_id in report_ids]
        results = await self.client.retrieve(
            collection_name=COLLECTION_NAME,
            ids=point_ids,
            with_vectors=True,
            with_payload=False,
        )
        vectors = np.array([point.vector for point in results])
        # Compute cosine similarity matrix
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        normalized = vectors / norms
        similarity_matrix = np.dot(normalized, normalized.T)
        # Return as list of (i, j, score) tuples
        pairs = []
        n = len(report_ids)
        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                pairs.append((report_ids[i], report_ids[j], float(similarity_matrix[i, j])))
        return pairs


    async def delete_vectors_by_report_ids(self, report_ids : List[int]):
        if not report_ids:
            return
        ids = [transform_to_uuid(report_id) for report_id in report_ids]
        await self.client.delete(
            collection_name=COLLECTION_NAME ,
            points_selector=models.PointIdsList(
                points=ids,
            )
    )

    async def add_report_to_vectorstore(self, report):
        title = report.title
        abstract = report.abstract
        authors = [item.strip() for item in report.authors.split("//")]

        text_to_process = []
        if title:
            text_to_process.append(title)
        if abstract:
            text_to_process.append(abstract)
        text_to_process = "\n".join(text_to_process)
    
        vector = await self.embedding_service.embed(text_to_process)

        new_id = transform_to_uuid(report.id)
        payload = {
            'title': title,
            'abstract': abstract,
            'source_id': report.id,
            'authors': authors,
            'date_entered': datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            'belongs_to_study': [],
            'belongs_to_trial_id': False,
            'temporary': {},
        }
        #new_vectors = {"default": vectors.pop("embedding")}#, "authors": vectors.pop("author_embedding")}
        #for key, value in vectors.items():
        #    new_vectors[key] = value

        #new_vectors.pop("model_id")
        #new_vectors = {"default": vector}

        points = [PointStruct(id=new_id,vector=vector, payload=payload)]
        await self.client.upsert(wait=True, collection_name=COLLECTION_NAME, points=points)

    async def add_study_report_to_vectorstore(self, report, study_ids : List[int], study_databases : Dict[int, int]):
        """A report already linked to its studies (e.g. of an imported database), found by the study search like
        the reports of the seed are (see ops/app-init/init.sh). `study_databases` maps each study to its database."""
        await self.add_report_to_vectorstore(report)
        await self.client.set_payload(
            collection_name=COLLECTION_NAME,
            payload={
                'is_report': True,
                'belongs_to_study': study_ids,
                'belongs_to_trial_id': bool(study_ids),
                'date_entered': report.date_entered,
                **self.database_payload(study_ids, study_databases),
            },
            points=[transform_to_uuid(report.id)],
        )

    async def merge_report(self, report_id : int, study_ids : List[int], study_databases : Dict[int, int]):
        """A report of an update merged into the core database: linked to its studies for every scope, like a report
        of an imported database (see add_study_report_to_vectorstore), its links in the scopes (`temporary`) gone."""
        await self.client.set_payload(
            collection_name=COLLECTION_NAME,
            payload={
                'is_report': True,
                'belongs_to_study': study_ids,
                'belongs_to_trial_id': bool(study_ids),
                'temporary': {},
                **self.database_payload(study_ids, study_databases),
            },
            points=[transform_to_uuid(report_id)],
        )

    async def search_report(self, query : Any ,k : int, filter : Any, database_id : Optional[int] = None):
        """The best-matching report point of each of the top-k studies (groups, by study id) of the database, or of
        all databases for None."""
        group_by = self.database_field(database_id)
        return await self.client.query_points_groups(
                collection_name=COLLECTION_NAME,
                query=query,
                group_by=group_by,  # Path of the field to group by
                limit=k,  # Max amount of groups
                group_size=1,  # Max amount of points per group
                query_filter=filter,
                with_payload=[group_by, f"temporary.{self.user_id}.belongs_to_study", "title", "authors", "source_id"],
            )

    def _in_database(self, database_id : Optional[int]) -> List[Any]:
        """The filter conditions for report points with a study of the database (none for all databases)."""
        if database_id is None:
            return []
        field = self.database_field(database_id)
        return [models.Filter(must_not=[models.IsEmptyCondition(is_empty=models.PayloadField(key=field))])]
    
    async def get_similar_tags_by_string(self, text : str, sources: List[str], aspect: str, k: int) -> List[TagCandidate]:
        vector = await self.embedding_service.embed(text)
        return await self.get_similar_tags(query=vector, sources=sources, aspect=aspect, k=k)

    async def get_similar_tags(self, query : Any, sources: List[str], aspect: str, k: int) -> List[TagCandidate]:
    
        #TODO implement more sophisticated tree based search here

        filters = []
        if "mesh" in sources:
            filters.append(models.FieldCondition(key="source", match=models.MatchValue(value="mesh")))

        if "internal" in sources:
            filters.append(models.Filter(
                must=[
                    models.FieldCondition(key="source", match=models.MatchValue(value="internal")),
                    models.FieldCondition(key="tree_ids",match=models.MatchAny(any=[aspect]))
                ]
            ))

        filter = models.Filter(should=filters)

        search_results = await self.client.query_points(
            collection_name=COLLECTION_NAME,
            query=query,
            limit=k,
            query_filter=filter,
        )

        return [TagCandidate(id=result.payload['source_id'], keyword=result.payload['display_name'], relevance=result.score) for result in search_results.points]
    
    async def score_tags(self, embedding : List[float], tag_ids : List[int], aspect : str) -> List[TagCandidate]:
        tag_filter = models.Filter(
            must=[
                models.FieldCondition(key="source", match=models.MatchValue(value="internal")),
                models.FieldCondition(key="tree_ids",match=models.MatchAny(any=[aspect])),
                models.FieldCondition(key="source_id",match=models.MatchAny(any=[str(item) for item in tag_ids]))
            ]
        )

        result = await self.client.query_points(
            collection_name=COLLECTION_NAME,
            query=embedding,
            limit=len(tag_ids),
            query_filter=tag_filter,
        )

        related_tags = []
        for point in result.points:
            related_tags.append(TagCandidate(id=point.payload['source_id'], keyword=point.payload['display_name'], relevance=point.score))

        return related_tags
    
    def build_recommandation_based_on_report_id(self, report_id : int):
        return models.RecommendQuery(
                    recommend=models.RecommendInput(
                        positive=[transform_to_uuid(report_id)],
                        strategy=models.RecommendStrategy.AVERAGE_VECTOR,
                    )
                )
    
    async def search_similar_studies(self, query : Any, k : int, cutoff : str, database_id : Optional[int] = None):
        """The top-k studies of the database (all databases for None), each as a group whose id is the study id."""
        filters = [models.FieldCondition(key="is_report",match=models.MatchValue(value=True)), *self._in_database(database_id)]
        if cutoff:
            filters.append(Filter(
                must=[
                    FieldCondition(key="date_entered",range=DatetimeRange(lt=datetime.fromisoformat(cutoff)))
                ]
            ))

        filter = models.Filter(must=filters)

        search_results = await self.search_report(query,k,filter,database_id)

        return search_results.groups

    async def score_studies(self, query : Any, study_ids : List[int], database_id : Optional[int] = None) -> Dict[int, float]:
        """Relevance of specific studies (of the database, if given) for `query`, scored exactly like
        search_similar_studies (best-matching report per study) but restricted to the given studies, so the
        result doesn't depend on whether they'd have made the top-k of an unrestricted search.
        Studies without any embedded report are absent from the result.
        """
        if not study_ids:
            return {}
        wanted = set(study_ids)
        filter = models.Filter(must=[
            models.FieldCondition(key="is_report", match=models.MatchValue(value=True)),
            models.FieldCondition(key=self.database_field(database_id), match=models.MatchAny(any=list(wanted))),
        ])
        results = await self.search_report(query, len(wanted), filter, database_id)
        scores: Dict[int, float] = {}
        for group in results.groups:
            if group.id in wanted and group.hits:
                scores[group.id] = group.hits[0].score
        return scores

    async def readyz(self):
        # Check vector store connectivity
        try:
            collections = await self.get_collections()
            return {
                "status": "healthy",
                "message": f"Vector store accessible, {len(collections.collections)} collections found"
            }
        except Exception as e:
            return {"status": "unhealthy", "message": f"Vector store error: {str(e)}"}