"""
Qdrant 向量库模块

职责：
1. 管理 Qdrant collection 生命周期（创建、状态、删除）。
2. 提供分块向量 upsert 与相似度检索。
3. 为知识库重建与问答检索提供统一向量存储接口。
"""
from typing import Iterable, List, Optional, Sequence

from django.conf import settings

try:
    from qdrant_client import QdrantClient
    from qdrant_client.http import models as qmodels

    QDRANT_AVAILABLE = True
except Exception:
    QdrantClient = None  # type: ignore
    qmodels = None  # type: ignore
    QDRANT_AVAILABLE = False


class QdrantVectorStore:
    def __init__(
        self,
        *,
        url: Optional[str] = None,
        collection_name: Optional[str] = None,
    ):
        self.url = (
            str(url or getattr(settings, "QDRANT_URL", "http://127.0.0.1:6333"))
            .strip()
            .rstrip("/")
        )
        self.collection_name = (
            str(
                collection_name
                or getattr(settings, "QDRANT_COLLECTION", "health_rag_chunks")
            )
            .strip()
        )
        self.timeout = int(getattr(settings, "QDRANT_TIMEOUT", 15))

    def _client(self):
        if not QDRANT_AVAILABLE:
            raise ValueError("qdrant-client 依赖未安装")
        return QdrantClient(url=self.url, timeout=self.timeout)

    def ensure_collection(self, *, vector_size: int) -> None:
        client = self._client()
        existing = [c.name for c in client.get_collections().collections]
        if self.collection_name in existing:
            return
        client.create_collection(
            collection_name=self.collection_name,
            vectors_config=qmodels.VectorParams(
                size=int(vector_size),
                distance=qmodels.Distance.COSINE,
            ),
        )

    def recreate_collection(self, *, vector_size: int) -> None:
        client = self._client()
        vectors_config = qmodels.VectorParams(
            size=int(vector_size),
            distance=qmodels.Distance.COSINE,
        )
        if hasattr(client, "recreate_collection"):
            client.recreate_collection(
                collection_name=self.collection_name,
                vectors_config=vectors_config,
            )
            return
        existing = [c.name for c in client.get_collections().collections]
        if self.collection_name in existing:
            client.delete_collection(collection_name=self.collection_name, timeout=self.timeout)
        self.ensure_collection(vector_size=vector_size)

    def clear_collection(self) -> None:
        client = self._client()
        existing = [c.name for c in client.get_collections().collections]
        if self.collection_name in existing:
            client.delete_collection(self.collection_name)

    def upsert_chunks(
        self,
        *,
        chunk_ids: Sequence[int],
        vectors: Sequence[Sequence[float]],
        payloads: Sequence[dict],
    ) -> int:
        if not (len(chunk_ids) == len(vectors) == len(payloads)):
            raise ValueError("upsert 输入长度不一致")
        if not vectors:
            return 0
        self.ensure_collection(vector_size=len(vectors[0]))
        client = self._client()
        points = [
            qmodels.PointStruct(
                id=int(chunk_id),
                vector=list(vector),
                payload=dict(payload),
            )
            for chunk_id, vector, payload in zip(chunk_ids, vectors, payloads)
        ]
        client.upsert(collection_name=self.collection_name, points=points, wait=True)
        return len(points)

    def delete_chunks(self, chunk_ids: Iterable[int]) -> None:
        ids = [int(item) for item in chunk_ids]
        if not ids:
            return
        client = self._client()
        existing = [c.name for c in client.get_collections().collections]
        if self.collection_name not in existing:
            return
        client.delete(
            collection_name=self.collection_name,
            points_selector=qmodels.PointIdsList(points=ids),
            wait=True,
        )

    def search(self, *, vector: Sequence[float], limit: int = 5):
        client = self._client()
        kwargs = {
            "collection_name": self.collection_name,
            "limit": int(limit),
            "with_payload": True,
            "with_vectors": False,
        }
        query_vector = list(vector)

        # 兼容不同 qdrant-client 版本：
        # - 老版本：client.search(...)
        # - 新版本：client.query_points(...)
        if hasattr(client, "search"):
            return client.search(query_vector=query_vector, **kwargs)

        if hasattr(client, "query_points"):
            result = client.query_points(query=query_vector, **kwargs)
            return list(getattr(result, "points", []) or [])

        raise AttributeError("当前 qdrant-client 不支持 search/query_points 接口")

    def status(self) -> dict:
        status = {
            "provider": "qdrant",
            "available": False,
            "url": self.url,
            "collection_name": self.collection_name,
            "points_count": 0,
            "vector_size": 0,
            "message": "",
        }
        if not QDRANT_AVAILABLE:
            status["message"] = "qdrant-client 依赖未安装"
            return status
        try:
            client = self._client()
            collections = [c.name for c in client.get_collections().collections]
            if self.collection_name not in collections:
                status["available"] = True
                status["message"] = "Qdrant 可用，collection 尚未创建"
                return status
            info = client.get_collection(self.collection_name)
            vector_size = 0
            try:
                vectors_cfg = getattr(getattr(info, "config", None), "params", None)
                vectors = getattr(vectors_cfg, "vectors", None)
                vector_size = int(getattr(vectors, "size", 0) or 0)
            except Exception:
                vector_size = 0
            status.update(
                {
                    "available": True,
                    "points_count": int(getattr(info, "points_count", 0) or 0),
                    "vector_size": vector_size,
                    "message": "Qdrant 可用",
                }
            )
            return status
        except Exception as exc:
            status["message"] = str(exc)
            return status
