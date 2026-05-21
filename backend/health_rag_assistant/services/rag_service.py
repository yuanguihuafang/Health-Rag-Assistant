"""
RAG 问答主流程
- 多轮对话检索查询重写（处理短追问）
- 检索 + LLM 生成的完整 RAG 链路
- 答案后处理（去除 think 标签、代码块标记等）
"""
import re
from typing import Dict, List, Optional, Tuple

from ..models import HealthKnowledgeChunk
from .llm_service import HealthLLMService
from .retriever_service import (
    LOW_CONFIDENCE_SCORE,
    MIN_SOURCE_SCORE,
    relevance_label,
    retrieve_top_k,
)

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


def _build_fallback_answer(
    question: str, contexts: List[dict], error: Exception
) -> str:
    if not contexts:
        return (
            "当前模型服务暂不可用，且知识库未检索到相关内容。"
            "请稍后重试，或在“模型状态”页配置可用的 BASE_URL/API_KEY/MODEL。"
        )

    lines = [
        "当前模型服务暂不可用，已返回知识库检索内容供参考：",
        f"问题：{question}",
        "",
        "参考片段：",
    ]
    for idx, ctx in enumerate(contexts[:3], start=1):
        snippet = (ctx.get("chunk_text") or "").replace("\n", " ").strip()
        if len(snippet) > 140:
            snippet = snippet[:140] + "..."
        lines.append(
            f"{idx}. 【{ctx.get('document_title', '未知文档')}#{ctx.get('chunk_index', 0)}】{snippet}"
        )
    lines.append("")
    lines.append(f"（模型错误：{error}）")
    return "\n".join(lines)


def build_contextual_retrieval_question(
    question: str,
    conversation_history: Optional[List[dict]] = None,
) -> str:
    """
    多轮对话里的检索查询要能理解短追问。
    例如上一轮是“男性久坐想减肥”，下一轮“女性呢？”时，检索应围绕
    “久坐/减肥/体重管理”继续，而不是把“女性”单独当成妇科问题。
    """
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


def ask_with_rag(
    user_id: int,
    question: str,
    k: int = 5,
    llm_config: Optional[Dict[str, str]] = None,
    conversation_history: Optional[List[dict]] = None,
) -> Tuple[str, List[dict]]:
    chunks_qs = HealthKnowledgeChunk.objects.filter(
        document__status="active",
    ).select_related("document")

    retrieval_question = build_contextual_retrieval_question(
        question=question,
        conversation_history=conversation_history,
    )
    top_scored = retrieve_top_k(
        question=retrieval_question,
        chunks=chunks_qs,
        k=k,
        user_id=0,
    )

    contexts = []
    sources = []
    top_score = float(top_scored[0][0]) if top_scored else 0.0
    low_confidence = bool(top_scored and top_score < LOW_CONFIDENCE_SCORE)
    for score, chunk in top_scored:
        score_value = round(float(score), 4)
        if score_value < MIN_SOURCE_SCORE:
            continue
        contexts.append(
            {
                "document_title": chunk.document.title,
                "chunk_index": chunk.chunk_index,
                "chunk_text": chunk.chunk_text,
                "score": score_value,
                "relevance_label": relevance_label(score_value),
                "low_confidence": low_confidence,
            }
        )
        sources.append(
            {
                "document_title": chunk.document.title,
                "chunk_index": chunk.chunk_index,
                "score": score_value,
                "relevance_label": relevance_label(score_value),
                "low_confidence": low_confidence,
            }
        )

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
