"""
RAG 问答主流程
- 多轮对话检索查询重写（处理短追问）
- 混合检索（向量 + 稀疏）与 RRF 融合
- 可选 Rerank 重排
- LLM 生成与答案后处理
"""
import re
from typing import Dict, List, Optional, Sequence, Tuple

from django.conf import settings

from ..models import HealthKnowledgeChunk
from .embedding_service import EmbeddingService
from .llm_service import HealthLLMService
from .rerank_service import RerankService
from .retriever_service import relevance_label, retrieve_top_k
from .vector_store import QdrantVectorStore

FOLLOW_UP_TERMS = (
    "呢",
    "那",
    "这个",
    "这种",
    "上述",
    "上面",
    "继续",
    "还有",
    "也",
    "男性",
    "女性",
    "老人",
    "孩子",
    "宝宝",
)

HEALTH_QUERY_EXPANSIONS: Dict[str, Sequence[str]] = {
    "失眠": ("睡不着", "入睡困难", "睡眠差", "早醒", "多梦", "熬夜", "睡眠不足", "休息不好"),
    "睡不着": ("失眠", "入睡困难", "睡眠差", "早醒", "多梦"),
    "睡眠": ("失眠", "睡不着", "入睡困难", "睡眠差", "早醒", "多梦", "熬夜"),
    "胃痛": ("胃疼", "胃部不适", "胃难受", "上腹痛", "反酸", "烧心", "胃酸"),
    "反酸": ("烧心", "胃酸", "胃食管反流", "饭后不适", "胸口烧", "嘴里发酸"),
    "发烧": ("发热", "体温", "高热", "退烧", "儿童发热", "宝宝发热", "儿科"),
    "发热": ("发烧", "体温", "高热", "退烧", "儿童发热", "宝宝发热", "儿科"),
    "儿童发热": ("宝宝发热", "小孩发烧", "儿科", "退烧", "体温观察"),
    "宝宝发热": ("儿童发热", "小孩发烧", "儿科", "退烧", "体温观察"),
    "小孩发烧": ("儿童发热", "宝宝发热", "儿科", "退烧", "体温观察"),
    "胸闷": ("胸口不舒服", "胸口发闷", "心慌", "心悸", "心跳快", "呼吸不顺"),
    "心悸": ("心慌", "心跳快", "心跳突然很快", "心跳明显", "胸闷", "心脏跳得乱"),
    "心慌": ("心悸", "心跳快", "胸闷", "心跳明显"),
    "胸痛": ("胸口痛", "胸前区疼痛", "出冷汗", "急症", "急诊", "心血管"),
    "出冷汗": ("胸痛", "急症", "急诊", "心血管", "立即就医"),
    "经期": ("痛经", "月经", "月经期间腹痛", "小腹痛", "女性健康", "妇科"),
    "痛经": ("经期腹痛", "月经期间腹痛", "小腹痛", "女性健康", "妇科", "调理"),
    "经期腹痛": ("痛经", "月经期间腹痛", "小腹痛", "女性健康", "妇科", "调理"),
    "白带": ("妇科", "阴道分泌物", "女性健康"),
    "积食": ("儿童消化", "不爱吃饭", "腹胀", "喂养", "儿科", "宝宝积食"),
    "宝宝积食": ("儿童消化", "不爱吃饭", "腹胀", "喂养", "儿科"),
    "喂养": ("儿童母婴", "宝宝", "不爱吃饭", "积食", "儿科"),
    "老人血压": ("老年高血压", "慢病管理", "血压监测", "低盐饮食"),
    "老年血压": ("老人血压", "慢病管理", "血压监测", "低盐饮食"),
    "血压": ("高血压", "血压监测", "低盐饮食", "慢病管理"),
    "高血压": ("血压偏高", "血压监测", "低盐饮食", "慢病管理"),
    "膝盖": ("膝关节", "运动损伤", "拉伸", "休息", "骨骼关节"),
    "酸痛": ("运动后酸痛", "拉伸", "休息", "运动损伤"),
    "久坐": ("久坐少动", "活动不足", "运动", "拉伸", "体重管理", "代谢"),
    "减肥": ("减脂", "体重管理", "控制热量", "运动", "饮食控制", "肥胖"),
    "减脂": ("减肥", "体重管理", "控制热量", "运动", "饮食控制"),
    "体重": ("体重管理", "减脂", "肥胖", "运动", "饮食控制"),
    "肥胖": ("体重管理", "减肥", "减脂", "控制热量", "运动", "饮食控制"),
}

MIN_SOURCE_SCORE = 0.15
LOW_CONFIDENCE_SCORE = 0.25
RRF_K = 60


def clean_model_answer(answer: str) -> str:
    text = str(answer or "")
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"</?think>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"['\"]?point['\"]?\s*[:：]\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"```(?:json|markdown|md)?", "", text, flags=re.IGNORECASE)
    text = text.replace("```", "")
    text = re.sub(r"^\s*[\{\[]\s*", "", text)
    text = re.sub(r"\s*[\}\]]\s*$", "", text)
    text = re.sub(r"^\s*[-*]\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*{2,}", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() or "暂未生成有效回答，请稍后重试。"


def _build_fallback_answer(question: str, contexts: List[dict], error: Exception) -> str:
    if not contexts:
        return (
            "当前模型服务暂不可用，且知识库未检索到相关内容。"
            "请稍后重试，或在“模型状态”页配置可用的 BASE_URL/API_KEY/MODEL。"
        )
    lines = ["当前模型服务暂不可用，已返回知识库检索内容供参考：", f"问题：{question}", "", "参考片段："]
    for idx, ctx in enumerate(contexts[:3], start=1):
        snippet = (ctx.get("chunk_text") or "").replace("\n", " ").strip()
        if len(snippet) > 140:
            snippet = snippet[:140] + "..."
        lines.append(f"{idx}. 【{ctx.get('document_title', '未知文档')}#{ctx.get('chunk_index', 0)}】{snippet}")
    lines.append("")
    lines.append(f"（模型错误：{error}）")
    return "\n".join(lines)


def build_contextual_retrieval_question(
    question: str,
    conversation_history: Optional[List[dict]] = None,
) -> str:
    current = str(question or "").strip()
    if not current:
        return ""
    normalized = re.sub(r"\s+", "", current)
    is_short_follow_up = len(normalized) <= 12
    has_follow_up_marker = any(term in normalized for term in FOLLOW_UP_TERMS)
    if not conversation_history or not (is_short_follow_up or has_follow_up_marker):
        return current
    previous_questions = [
        str(item.get("question") or "").strip()
        for item in conversation_history[-2:]
        if str(item.get("question") or "").strip()
    ]
    if not previous_questions:
        return current
    return " ".join([*previous_questions, current])


def expand_health_query(question: str) -> str:
    text = str(question or "").strip()
    if not text:
        return ""
    terms: List[str] = [text]
    for trigger, expansions in HEALTH_QUERY_EXPANSIONS.items():
        if trigger in text:
            terms.extend(expansions)
    deduped: List[str] = []
    seen = set()
    for term in terms:
        item = str(term or "").strip()
        if item and item not in seen:
            seen.add(item)
            deduped.append(item)
    return " ".join(deduped)


def build_retrieval_query(question: str, conversation_history: Optional[List[dict]] = None) -> str:
    contextual = build_contextual_retrieval_question(question=question, conversation_history=conversation_history)
    enabled = bool(getattr(settings, "RAG_ENABLE_QUERY_EXPANSION", True))
    if not enabled:
        return contextual
    return expand_health_query(contextual)


def _rrf_merge(vector_ranked: List[dict], sparse_ranked: List[dict], top_k: int = 20) -> List[dict]:
    by_id: Dict[int, dict] = {}
    for idx, item in enumerate(vector_ranked, start=1):
        cid = int(item["chunk_id"])
        score = 1.0 / (RRF_K + idx)
        current = by_id.get(cid, {"chunk_id": cid, "rrf_score": 0.0, "vector_rank": None, "sparse_rank": None})
        current["rrf_score"] += score
        current["vector_rank"] = idx
        current["vector_score"] = item.get("score", 0.0)
        by_id[cid] = current
    for idx, item in enumerate(sparse_ranked, start=1):
        cid = int(item["chunk_id"])
        score = 1.0 / (RRF_K + idx)
        current = by_id.get(cid, {"chunk_id": cid, "rrf_score": 0.0, "vector_rank": None, "sparse_rank": None})
        current["rrf_score"] += score
        current["sparse_rank"] = idx
        current["sparse_score"] = item.get("score", 0.0)
        by_id[cid] = current
    merged = sorted(by_id.values(), key=lambda x: x["rrf_score"], reverse=True)
    return merged[: max(int(top_k), 1)]


def _enrich_ranked_items(items: List[dict], chunk_map: Dict[int, HealthKnowledgeChunk]) -> List[dict]:
    enriched = []
    for item in items:
        current = dict(item)
        chunk = chunk_map.get(int(current["chunk_id"]))
        if chunk:
            current.setdefault("document_id", int(chunk.document_id))
            current.setdefault("document_title", chunk.document.title)
            current.setdefault("chunk_index", int(chunk.chunk_index))
            current.setdefault("source_path", chunk.document.source_path)
        enriched.append(current)
    return enriched


def _display_score(item: dict) -> float:
    for key in ("rerank_score", "score", "vector_score", "sparse_score", "rrf_score"):
        value = item.get(key)
        try:
            if value is not None:
                return float(value)
        except Exception:
            continue
    return 0.0


def retrieve_hybrid(
    question: str,
    conversation_history: Optional[List[dict]] = None,
    *,
    vector_k: Optional[int] = None,
    sparse_k: Optional[int] = None,
    fused_k: int = 20,
) -> dict:
    retrieval_query = build_retrieval_query(question=question, conversation_history=conversation_history)
    vector_k = int(vector_k or getattr(settings, "RAG_VECTOR_TOP_K", 30))
    sparse_k = int(sparse_k or getattr(settings, "RAG_VECTOR_TOP_K", 30))

    embedder = EmbeddingService()
    query_vector = embedder.embed_query(retrieval_query)
    vector_hits = QdrantVectorStore().search(vector=query_vector, limit=vector_k)
    vector_ranked = []
    for hit in vector_hits:
        payload = getattr(hit, "payload", {}) or {}
        chunk_id = payload.get("chunk_id")
        if not chunk_id:
            continue
        vector_ranked.append(
            {
                "chunk_id": int(chunk_id),
                "score": float(getattr(hit, "score", 0.0)),
                "document_id": payload.get("document_id"),
                "document_title": payload.get("document_title", ""),
                "chunk_index": payload.get("chunk_index", 0),
                "source_path": payload.get("source_path", ""),
            }
        )

    chunks_qs = (
        HealthKnowledgeChunk.objects.filter(document__status="active")
        .select_related("document")
        .order_by("document_id", "chunk_index")
    )
    sparse_top = retrieve_top_k(question=retrieval_query, chunks=chunks_qs, k=sparse_k)
    sparse_ranked = []
    for score, chunk in sparse_top:
        sparse_ranked.append(
            {
                "chunk_id": int(chunk.id),
                "score": float(score),
                "document_id": int(chunk.document_id),
                "document_title": chunk.document.title,
                "chunk_index": int(chunk.chunk_index),
                "source_path": chunk.document.source_path,
            }
        )

    rrf_ranked = _rrf_merge(vector_ranked=vector_ranked, sparse_ranked=sparse_ranked, top_k=fused_k)
    rrf_chunk_ids = [int(item["chunk_id"]) for item in rrf_ranked]
    chunk_map = {
        chunk.id: chunk
        for chunk in HealthKnowledgeChunk.objects.filter(
            id__in=rrf_chunk_ids, document__status="active"
        ).select_related("document")
    }
    rrf_ranked = _enrich_ranked_items(rrf_ranked, chunk_map)

    rerank_enabled = bool(getattr(settings, "RERANK_ENABLED", True))
    rerank_top_n = int(getattr(settings, "RERANK_TOP_N", 5))
    rerank_ranked = []
    rerank_error = ""
    final_ranked = list(rrf_ranked)

    if rerank_enabled and rrf_ranked:
        docs_for_rerank = []
        valid_rrf = []
        for item in rrf_ranked:
            chunk = chunk_map.get(int(item["chunk_id"]))
            if not chunk:
                continue
            valid_rrf.append(item)
            docs_for_rerank.append(chunk.chunk_text or "")
        try:
            rerank_results = RerankService().rerank(
                query=retrieval_query,
                documents=docs_for_rerank,
                top_n=min(rerank_top_n, len(docs_for_rerank)),
            )
            rerank_ranked = []
            for rank_item in rerank_results:
                idx = int(rank_item["index"])
                if idx < 0 or idx >= len(valid_rrf):
                    continue
                base = dict(valid_rrf[idx])
                base["rerank_score"] = float(rank_item["score"])
                rerank_ranked.append(base)
            if rerank_ranked:
                final_ranked = _enrich_ranked_items(rerank_ranked, chunk_map)
        except Exception as exc:
            rerank_error = str(exc)

    contexts: List[dict] = []
    sources: List[dict] = []
    final_ranked = _enrich_ranked_items(final_ranked, chunk_map)
    top_score = _display_score(final_ranked[0]) if final_ranked else 0.0
    low_confidence = bool(final_ranked and top_score < LOW_CONFIDENCE_SCORE)

    for item in final_ranked[: max(int(getattr(settings, "RAG_TOP_K", 5)), 1)]:
        chunk_id = int(item["chunk_id"])
        chunk = chunk_map.get(chunk_id)
        if not chunk:
            continue
        score_value = _display_score(item)
        has_semantic_score = any(item.get(key) is not None for key in ("rerank_score", "score", "vector_score", "sparse_score"))
        if has_semantic_score and score_value < MIN_SOURCE_SCORE:
            continue
        score_value = round(score_value, 4)
        context_item = {
            "chunk_id": int(chunk.id),
            "document_id": int(chunk.document_id),
            "document_title": chunk.document.title,
            "chunk_index": chunk.chunk_index,
            "chunk_text": chunk.chunk_text,
            "source_path": chunk.document.source_path,
            "score": score_value,
            "relevance_label": relevance_label(score_value),
            "low_confidence": low_confidence,
        }
        contexts.append(context_item)
        sources.append(
            {
                "document_title": chunk.document.title,
                "chunk_index": chunk.chunk_index,
                "score": score_value,
                "relevance_label": relevance_label(score_value),
                "low_confidence": low_confidence,
            }
        )

    return {
        "question": question,
        "retrieval_query": retrieval_query,
        "query_embedding_dim": len(query_vector),
        "vector_hits": vector_ranked,
        "sparse_hits": sparse_ranked,
        "rrf_hits": rrf_ranked,
        "rerank_hits": rerank_ranked,
        "rerank_error": rerank_error,
        "final_hits": final_ranked,
        "contexts": contexts,
        "sources": sources,
    }


def ask_with_rag(
    user_id: int,
    question: str,
    k: int = 5,
    llm_config: Optional[Dict[str, str]] = None,
    conversation_history: Optional[List[dict]] = None,
) -> Tuple[str, List[dict]]:
    _ = user_id
    _ = k
    retrieval = retrieve_hybrid(
        question=question,
        conversation_history=conversation_history,
        fused_k=20,
    )
    contexts = retrieval.get("contexts") or []
    sources = retrieval.get("sources") or []

    config = llm_config or {}
    llm_service = HealthLLMService(
        base_url=config.get("base_url"),
        api_key=config.get("api_key"),
        model_name=config.get("model_name"),
    )
    try:
        answer = llm_service.generate_answer(
            question=question,
            contexts=contexts,
            conversation_history=conversation_history,
        )
    except Exception as exc:
        answer = _build_fallback_answer(question=question, contexts=contexts, error=exc)
    return clean_model_answer(answer), sources
