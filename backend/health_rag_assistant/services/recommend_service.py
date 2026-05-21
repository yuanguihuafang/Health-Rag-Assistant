"""
个性化推荐服务
- 分析用户近 90 天问答记录，按 13 个健康主题统计兴趣得分
- 用主题关键词作为检索 query，返回推荐知识片段
- 历史不足时返回近期更新的通用文档兜底
"""
import random
from datetime import timedelta
from typing import Dict, Iterable, List

from django.conf import settings
from django.utils import timezone

from ..models import HealthKnowledgeChunk, HealthKnowledgeDocument, HealthQARecord
from .retriever_service import retrieve_top_k

TOPIC_KEYWORDS: Dict[str, List[str]] = {
    "睡眠调理": ["失眠", "睡眠", "熬夜", "多梦", "早醒", "入睡"],
    "肠胃调理": ["胃", "肠", "消化", "腹痛", "腹泻", "便秘", "胃炎", "胃痛"],
    "感冒与免疫": ["感冒", "发烧", "咳嗽", "流感", "免疫", "鼻塞", "喉咙"],
    "关节与骨骼": ["关节", "膝盖", "骨质", "腰痛", "颈椎", "肩周", "扭伤"],
    "血压与心血管": ["高血压", "血压", "心脏", "血脂", "胸闷", "心悸"],
    "儿童母婴": ["宝宝发热", "儿童发热", "宝宝积食", "儿童消化", "婴儿喂养", "儿科", "喂养", "积食"],
    "运动体重": ["减肥", "减脂", "体重", "肥胖", "久坐", "运动", "锻炼", "热量"],
    "代谢与血糖": ["糖尿病", "血糖", "血脂", "肥胖", "代谢", "胰岛素"],
    "情绪与压力": ["焦虑", "抑郁", "压力", "情绪", "烦躁", "紧张"],
    "女性健康": ["月经", "妇科", "宫颈", "白带", "乳腺", "盆腔"],
    "男性健康": ["前列腺", "阳痿", "早泄", "精子", "射精", "包皮", "睾丸"],
    "皮肤与过敏": ["皮肤", "湿疹", "过敏", "痤疮", "瘙痒", "皮炎"],
}


def _format_dt(value) -> str:
    if not value:
        return ""
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _clip_text(text: str, limit: int = 220) -> str:
    normalized = " ".join((text or "").split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit]}..."


def _get_recent_records(user_id: int, history_days: int) -> List[HealthQARecord]:
    since = timezone.now() - timedelta(days=int(history_days))
    return list(
        HealthQARecord.objects.filter(user_id=user_id, created_at__gte=since)
        .order_by("-created_at")
        .only("question", "answer", "created_at")
    )


def _collect_text_corpus(records: Iterable[HealthQARecord]) -> str:
    fragments: List[str] = []
    for record in records:
        fragments.append(record.question or "")
        # 回答可能很长，这里只截取前段用于主题统计，避免噪声放大
        fragments.append((record.answer or "")[:300])
    return "\n".join(fragments)


def _analyze_topics(
    records: List[HealthQARecord],
    topic_count: int,
) -> List[dict]:
    if not records:
        return []

    text_corpus = _collect_text_corpus(records)
    topic_stats: List[dict] = []
    for topic, keywords in TOPIC_KEYWORDS.items():
        score = 0
        matched_keywords: List[str] = []
        for keyword in keywords:
            hit = text_corpus.count(keyword)
            if hit > 0:
                score += hit
                matched_keywords.append(keyword)
        if score > 0:
            topic_stats.append(
                {
                    "topic": topic,
                    "score": score,
                    "matched_keywords": matched_keywords[:6],
                }
            )

    topic_stats.sort(key=lambda item: item["score"], reverse=True)
    return topic_stats[: int(topic_count)]


def _build_topic_query(topic_item: dict) -> str:
    topic = topic_item.get("topic", "")
    keywords = topic_item.get("matched_keywords", []) or []
    head_keywords = keywords[:4]
    return f"{topic} {' '.join(head_keywords)}".strip()


def _recommend_from_topics(
    topics: List[dict],
    limit: int,
    k_per_topic: int,
    randomize: bool = False,
) -> List[dict]:
    max_chunks = max(
        int(limit) * max(int(k_per_topic), 1) * 4,
        int(getattr(settings, "HEALTH_RAG_RECOMMEND_MAX_CHUNKS", 600)),
    )
    chunks_qs = (
        HealthKnowledgeChunk.objects.filter(document__status="active")
        .select_related("document")
        .order_by("-document__updated_at", "document_id", "chunk_index")[:max_chunks]
    )
    if not chunks_qs.exists():
        return []

    recs: List[dict] = []
    seen_chunk_ids = set()
    candidate_k = max(int(k_per_topic), int(limit) * 2) if randomize else int(k_per_topic)
    for topic_item in topics:
        query = _build_topic_query(topic_item)
        if not query:
            continue

        top_scored = retrieve_top_k(
            question=query,
            chunks=chunks_qs,
            k=candidate_k,
            user_id=0,
        )
        for score, chunk in top_scored:
            if chunk.id in seen_chunk_ids:
                continue
            seen_chunk_ids.add(chunk.id)
            recs.append(
                {
                    "topic": topic_item.get("topic", ""),
                    "reason": f"近期问答中多次出现“{topic_item.get('topic', '')}”相关问题",
                    "document_id": chunk.document_id,
                    "document_title": chunk.document.title,
                    "source_path": chunk.document.source_path,
                    "chunk_id": chunk.id,
                    "chunk_index": chunk.chunk_index,
                    "score": round(float(score), 4),
                    "snippet": _clip_text(chunk.chunk_text, 220),
                    "document_updated_at": _format_dt(chunk.document.updated_at),
                }
            )
            if not randomize and len(recs) >= int(limit):
                return recs
    if randomize:
        random.shuffle(recs)
    return recs


def _fallback_recommendations(limit: int, existed_doc_ids: set, randomize: bool = False) -> List[dict]:
    docs_qs = (
        HealthKnowledgeDocument.objects.filter(status="active")
        .exclude(id__in=list(existed_doc_ids))
        .order_by("-updated_at")
    )
    docs = list(docs_qs[: max(int(limit), int(limit) * 3 if randomize else int(limit))])
    if randomize:
        random.shuffle(docs)
        docs = docs[: int(limit)]
    results: List[dict] = []
    for doc in docs:
        results.append(
            {
                "topic": "通用健康知识",
                "reason": "你最近历史问答较少，先推荐近期更新的基础健康知识",
                "document_id": doc.id,
                "document_title": doc.title,
                "source_path": doc.source_path,
                "chunk_id": None,
                "chunk_index": None,
                "score": None,
                "snippet": _clip_text(doc.content, 220) or "暂无摘要",
                "document_updated_at": _format_dt(doc.updated_at),
            }
        )
    return results


def build_personal_recommendations(
    *,
    user_id: int,
    limit: int = 8,
    history_days: int = 90,
    topic_count: int = 3,
    k_per_topic: int = 3,
    randomize: bool = False,
) -> dict:
    limit = int(limit)
    records = _get_recent_records(user_id=user_id, history_days=int(history_days))
    topics = _analyze_topics(records=records, topic_count=int(topic_count))
    recommendations = _recommend_from_topics(
        topics=topics,
        limit=limit,
        k_per_topic=int(k_per_topic),
        randomize=bool(randomize),
    )

    existed_doc_ids = {
        item["document_id"] for item in recommendations if item.get("document_id")
    }
    if len(recommendations) < limit:
        recommendations.extend(
            _fallback_recommendations(
                limit=limit - len(recommendations),
                existed_doc_ids=existed_doc_ids,
                randomize=bool(randomize),
            )
        )

    return {
        "profile": {
            "history_record_count": len(records),
            "analysis_window_days": int(history_days),
            "topic_focus": topics,
        },
        "recommendations": recommendations[:limit],
    }
