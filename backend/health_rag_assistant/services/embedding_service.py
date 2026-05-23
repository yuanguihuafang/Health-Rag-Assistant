"""
Embedding 服务模块

职责：
1. 读取 OpenAI 兼容 embedding 配置。
2. 调用 /v1/embeddings 生成查询和文档分块向量。
3. 提供批量向量化能力，供知识库入库与检索复用。
"""
from typing import Iterable, List, Optional

import requests
from django.conf import settings


class EmbeddingService:
    """OpenAI 兼容 Embedding 调用封装。"""

    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
    ):
        self.base_url = self._normalize_base_url(
            base_url
            or getattr(settings, "EMBEDDING_BASE_URL", "")
            or getattr(settings, "LLM_BASE_URL", "")
        )
        self.api_key = (
            api_key
            or getattr(settings, "EMBEDDING_API_KEY", "")
            or getattr(settings, "LLM_API_KEY", "")
            or ""
        ).strip()
        self.model_name = (
            model_name
            or getattr(settings, "EMBEDDING_MODEL", "")
            or "text-embedding-3-small"
        ).strip()
        self.timeout = int(
            getattr(
                settings,
                "EMBEDDING_TIMEOUT",
                30,
            )
        )
        self.endpoint = self._build_embeddings_endpoint(self.base_url)

    @staticmethod
    def _normalize_base_url(base_url: Optional[str]) -> str:
        return str(base_url or "").strip().rstrip("/")

    @staticmethod
    def _build_embeddings_endpoint(base_url: str) -> str:
        if not base_url:
            return ""
        if base_url.endswith("/v1"):
            return f"{base_url}/embeddings"
        return f"{base_url}/v1/embeddings"

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _check_ready(self) -> None:
        if not self.base_url:
            raise ValueError("EMBEDDING_BASE_URL 未配置")
        if not self.model_name:
            raise ValueError("EMBEDDING_MODEL 未配置")
        if not self.endpoint:
            raise ValueError("Embedding 接口地址无效")

    def embed_documents(self, texts: Iterable[str]) -> List[List[float]]:
        self._check_ready()
        payload = {"model": self.model_name, "input": [str(text or "") for text in texts]}
        if not payload["input"]:
            return []
        response = requests.post(
            self.endpoint,
            json=payload,
            headers=self._headers(),
            timeout=self.timeout,
        )
        if response.status_code >= 400:
            raise ValueError(
                f"Embedding 调用失败 {response.status_code}: {response.text[:300]}"
            )
        body = response.json()
        data = body.get("data") or []
        embeddings = [item.get("embedding") for item in data if item.get("embedding")]
        if len(embeddings) != len(payload["input"]):
            raise ValueError("Embedding 响应数量与输入数量不一致")
        return embeddings

    def embed_query(self, text: str) -> List[float]:
        vectors = self.embed_documents([text])
        if not vectors:
            raise ValueError("Embedding 响应为空")
        return vectors[0]

    def status(self) -> dict:
        try:
            sample = self.embed_query("健康问答模型状态检查")
            return {
                "provider": "openai-compatible",
                "available": True,
                "base_url": self.base_url,
                "model_name": self.model_name,
                "api_key_configured": bool(self.api_key),
                "embedding_dim": len(sample),
                "message": "embedding 服务可用",
            }
        except Exception as exc:
            return {
                "provider": "openai-compatible",
                "available": False,
                "base_url": self.base_url,
                "model_name": self.model_name,
                "api_key_configured": bool(self.api_key),
                "embedding_dim": 0,
                "message": str(exc),
            }
