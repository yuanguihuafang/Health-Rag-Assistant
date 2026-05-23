"""
Rerank 服务模块

职责：
1. 调用 OpenAI 兼容重排接口（适配阿里云百炼 qwen3-rerank）。
2. 对召回候选进行二次排序，降低低相关片段进入 Prompt 的概率。
"""
from typing import List, Optional, Sequence

import requests
from django.conf import settings


class RerankService:
    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
    ):
        self.base_url = str(
            base_url or getattr(settings, "RERANK_BASE_URL", "") or getattr(settings, "LLM_BASE_URL", "")
        ).strip().rstrip("/")
        self.api_key = str(
            api_key or getattr(settings, "RERANK_API_KEY", "") or getattr(settings, "LLM_API_KEY", "")
        ).strip()
        self.model_name = str(
            model_name or getattr(settings, "RERANK_MODEL", "qwen3-rerank")
        ).strip()
        self.timeout = int(getattr(settings, "RERANK_TIMEOUT", 30))

    def _endpoint(self) -> str:
        if not self.base_url:
            raise ValueError("RERANK_BASE_URL 未配置")
        if self.base_url.endswith("/reranks") or self.base_url.endswith("/rerank"):
            return self.base_url
        if "dashscope.aliyuncs.com" in self.base_url and self.model_name.startswith("qwen3-rerank"):
            root = self.base_url.split("/compatible-")[0]
            return f"{root}/compatible-api/v1/reranks"
        if self.base_url.endswith("/v1"):
            return f"{self.base_url}/rerank"
        return f"{self.base_url}/v1/rerank"

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    @staticmethod
    def _parse_results(body: dict) -> List[dict]:
        if isinstance(body.get("results"), list):
            return body.get("results") or []
        output = body.get("output") or {}
        if isinstance(output.get("results"), list):
            return output.get("results") or []
        data = body.get("data")
        if isinstance(data, list):
            return data
        return []

    def rerank(self, *, query: str, documents: Sequence[str], top_n: int) -> List[dict]:
        docs = [str(item or "") for item in documents]
        if not docs:
            return []
        endpoint = self._endpoint()
        payload = {
            "model": self.model_name,
            "query": str(query or ""),
            "documents": docs,
            "top_n": int(max(min(top_n, len(docs)), 1)),
        }
        if not self.model_name.startswith("qwen3-rerank"):
            payload["return_documents"] = False
        response = requests.post(
            endpoint,
            json=payload,
            headers=self._headers(),
            timeout=self.timeout,
        )
        if response.status_code >= 400:
            raise ValueError(f"Rerank 调用失败 {response.status_code}: {response.text[:300]}")
        body = response.json()
        results = self._parse_results(body)
        normalized = []
        for item in results:
            index = item.get("index")
            score = item.get("relevance_score", item.get("score", 0))
            if index is None:
                continue
            normalized.append({"index": int(index), "score": float(score)})
        normalized.sort(key=lambda x: x["score"], reverse=True)
        return normalized
