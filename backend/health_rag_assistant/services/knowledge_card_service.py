"""
知识卡片生成服务
- 将问答结果结构化为知识卡片（title / core_points / cautions / references）
- 优先用 LLM 生成结构化 JSON（force_json）
- LLM 失败时回退到启发式规则抽取
"""
import json
import re
from typing import Any, Dict, Iterable, List, Optional

from django.utils import timezone

from .llm_service import HealthLLMService


def _extract_json_text(text: str) -> str:
    """
    尽可能从模型输出中抽取 JSON 对象文本。
    - 支持 ```json ... ``` 包裹
    - 支持前后带额外说明文字时截取最外层 {...}
    """
    content = (text or "").strip()
    if not content:
        return "{}"

    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?", "", content, flags=re.IGNORECASE).strip()
        content = re.sub(r"```$", "", content).strip()

    if not content.startswith("{"):
        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end > start:
            content = content[start : end + 1]
    return content.strip() or "{}"


def _normalize_str_list(value: Any, *, limit: int) -> List[str]:
    if not value:
        return []
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list):
        items = value
    else:
        items = [str(value)]

    cleaned: List[str] = []
    for item in items:
        text = str(item or "").strip()
        if not text:
            continue
        # 去掉常见的编号前缀
        text = re.sub(r"^[\-\*\d\.\)\s]+", "", text).strip()
        if text:
            cleaned.append(text)
        if len(cleaned) >= limit:
            break
    return cleaned


def _guess_title(question: str) -> str:
    q = (question or "").strip()
    if not q:
        return "健康知识卡片"

    # 简单规则：保留前 10 个字符的核心主题
    q = re.sub(r"[，。？！!?,.\s]+", " ", q).strip()
    q = (
        q.replace("怎么", "")
        .replace("如何", "")
        .replace("应该", "")
        .replace("请问", "")
    )
    q = q.replace("怎么办", "").replace("有哪些", "").replace("有什么", "")
    q = q.strip()
    if not q:
        return "健康知识卡片"

    topic = q[:10].strip()
    if any(k in q for k in ("失眠", "睡眠")):
        return "失眠调理清单"
    if "感冒" in q or "流感" in q:
        return "感冒缓解方法"
    if "咳嗽" in q:
        return "咳嗽缓解要点"
    if "胃" in q or "肠" in q:
        return "肠胃调理清单"
    return f"{topic}要点"


def _score_label(score) -> str:
    try:
        value = float(score or 0)
    except Exception:
        value = 0.0
    if value >= 0.7:
        return "高相关"
    if value >= 0.3:
        return "较相关"
    return "弱相关"


def _fallback_card(question: str, answer: str, sources: List[dict]) -> Dict[str, Any]:
    # 从回答中抽取若干句子做“核心要点”
    answer_text = (answer or "").strip()
    segments = re.split(r"[。\n；;]+", answer_text)
    core_points = [seg.strip() for seg in segments if seg.strip()][:5]

    cautions = [
        "如出现高热不退、呼吸困难、胸痛等严重症状，请及时就医。",
        "以上建议仅供健康科普参考，不替代医生诊断与治疗。",
    ]

    references = []
    for src in sources or []:
        title = (src.get("document_title") or "未知文档").strip()
        chunk_index = int(src.get("chunk_index", 0) or 0) + 1
        score = src.get("score", None)
        label = src.get("relevance_label") or _score_label(score)
        if score is None:
            references.append(f"{title} 片段 {chunk_index}")
        else:
            references.append(f"{title} 片段 {chunk_index}（score: {score} / {label}）")
        if len(references) >= 6:
            break

    return {
        "title": _guess_title(question),
        "core_points": core_points,
        "cautions": cautions,
        "references": references,
        "generated_at": timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M:%S"),
        "engine": "fallback",
    }


def _build_source_lines(sources: Iterable[dict]) -> str:
    lines: List[str] = []
    for idx, src in enumerate(list(sources or [])[:8], start=1):
        title = (src.get("document_title") or "未知文档").strip()
        chunk_index = int(src.get("chunk_index", 0) or 0) + 1
        score = src.get("score", "")
        label = src.get("relevance_label") or _score_label(score)
        if score == "" or score is None:
            lines.append(f"[{idx}] {title} 片段 {chunk_index}")
        else:
            lines.append(f"[{idx}] {title} 片段 {chunk_index}（score: {score} / {label}）")
    return "\n".join(lines).strip()


def build_knowledge_card(
    *,
    question: str,
    answer: str,
    sources: Optional[List[dict]] = None,
    llm_config: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    将问答结果结构化为“知识卡片”，用于前端快速展示/复制分享。

    返回字段：
    - title: string
    - core_points: string[]
    - cautions: string[]
    - references: string[]
    - generated_at: string
    """
    sources = sources or []
    llm_config = llm_config or {}

    # 优先用 LLM 生成结构化 JSON；若不可用则回退到启发式抽取。
    try:
        llm_service = HealthLLMService(
            base_url=llm_config.get("base_url"),
            api_key=llm_config.get("api_key"),
            model_name=llm_config.get("model_name"),
        )

        system_prompt = (
            "你是健康知识卡片生成器。请根据用户问题与回答，生成便于快速查阅与分享的结构化知识卡片。"
            "只输出严格 JSON 对象，不要输出 Markdown、代码块或任何解释。"
            "JSON 字段要求："
            "title（string，简短清晰，例如“感冒缓解方法”“失眠调理清单”）；"
            "core_points（array[string]，3-6条，写成可执行要点）；"
            "cautions（array[string]，2-6条，包含禁忌/何时就医/人群注意事项）；"
            "references（array[string]，参考来源列表，优先使用给定来源文本，最多6条）。"
        )

        source_lines = _build_source_lines(sources)
        user_prompt = (
            f"用户问题：{(question or '').strip()}\n\n"
            f"问答回答：{(answer or '').strip()}\n\n"
            "可用引用来源（若为空可忽略）：\n"
            f"{source_lines or '（无）'}\n\n"
            "请直接输出 JSON："
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        raw_text = llm_service.generate_by_messages(messages, force_json=True)
        parsed = json.loads(_extract_json_text(raw_text))
        if not isinstance(parsed, dict):
            raise ValueError("知识卡片解析结果不是对象")

        title = str(parsed.get("title") or "").strip() or _guess_title(question)
        core_points = _normalize_str_list(parsed.get("core_points"), limit=6)
        cautions = _normalize_str_list(parsed.get("cautions"), limit=6)
        references = _normalize_str_list(parsed.get("references"), limit=6)

        if not core_points:
            # LLM 可能输出为空，兜底抽取
            core_points = _fallback_card(question, answer, sources).get(
                "core_points", []
            )[:6]
        if not cautions:
            cautions = _fallback_card(question, answer, sources).get("cautions", [])[:6]
        if not references:
            references = _fallback_card(question, answer, sources).get(
                "references", []
            )[:6]

        return {
            "title": title,
            "core_points": core_points,
            "cautions": cautions,
            "references": references,
            "generated_at": timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M:%S"),
            "engine": "llm",
        }
    except Exception:
        return _fallback_card(question, answer, sources)
