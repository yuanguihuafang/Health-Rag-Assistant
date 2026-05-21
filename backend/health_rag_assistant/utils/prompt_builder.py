"""
Prompt 构建
- 构建 LLM 问答 prompt：system 指令 + 多轮对话历史 + 参考资料 + 当前问题
- 构建上下文块：将检索结果格式化为可读引用列表
"""
from typing import Iterable, List, Optional


def build_context_block(contexts: Iterable[dict]) -> str:
    lines: List[str] = []
    for idx, item in enumerate(contexts, start=1):
        title = item.get("document_title") or "未知文档"
        chunk_index = item.get("chunk_index", 0)
        text = item.get("chunk_text") or ""
        lines.append(f"[来源{idx}] 文档: {title} | 片段: {chunk_index}\n{text}")
    return "\n\n".join(lines).strip()


def build_history_messages(conversation_history: Optional[Iterable[dict]]) -> List[dict]:
    messages: List[dict] = []
    for item in conversation_history or []:
        question = str(item.get("question") or "").strip()
        answer = str(item.get("answer") or "").strip()
        if question:
            messages.append({"role": "user", "content": question})
        if answer:
            messages.append({"role": "assistant", "content": answer})
    return messages


def build_messages(
    question: str,
    contexts: Iterable[dict],
    conversation_history: Optional[Iterable[dict]] = None,
) -> List[dict]:
    context_block = build_context_block(contexts)
    system_prompt = (
        "你是身体健康科普问答助手。请基于给定的知识片段作答，"
        "回答应简洁、可执行、易懂。若用户问题与上文对话相关，请结合当前会话历史连续作答。若知识不足请明确说明。"
        "必须在结尾提醒：仅供健康科普参考，不替代医生诊断。"
    )

    if context_block:
        user_prompt = (
            f"参考资料:\n{context_block}\n\n"
            f"请结合以上资料回答用户当前问题：{question}"
        )
    else:
        user_prompt = (
            f"用户当前问题: {question}\n\n"
            "当前未检索到有效知识片段，请基于通用健康科普给出谨慎建议，"
            "并明确提醒用户必要时就医。"
        )

    return [
        {"role": "system", "content": system_prompt},
        *build_history_messages(conversation_history),
        {"role": "user", "content": user_prompt},
    ]
