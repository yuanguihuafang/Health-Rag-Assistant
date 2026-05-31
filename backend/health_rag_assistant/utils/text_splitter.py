"""
文本切分器
- 按字符切分（简单实现，满足 MVP 需求）
- 支持 chunk_size 和 chunk_overlap 配置
"""
import re
from typing import List


def _fixed_split(content: str, chunk_size: int, chunk_overlap: int) -> List[str]:
    step = chunk_size - chunk_overlap
    chunks: List[str] = []
    start = 0
    length = len(content)
    while start < length:
        end = min(start + chunk_size, length)
        chunk = content[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= length:
            break
        start += step
    return chunks


def _adaptive_split(content: str, chunk_size: int, chunk_overlap: int) -> List[str]:
    # 先按句子粗分，再拼成目标长度，尽量不截断语义
    sentences = [s.strip() for s in re.split(r"(?<=[。！？!?；;\n])", content) if s.strip()]
    if not sentences:
        return _fixed_split(content, chunk_size, chunk_overlap)

    chunks: List[str] = []
    current = ""
    for sentence in sentences:
        if len(sentence) > chunk_size:
            # 句子过长时退回固定切分
            if current:
                chunks.append(current.strip())
                current = ""
            chunks.extend(_fixed_split(sentence, chunk_size, chunk_overlap))
            continue
        if not current:
            current = sentence
            continue
        if len(current) + len(sentence) <= chunk_size:
            current += sentence
        else:
            chunks.append(current.strip())
            # 用字符重叠作为过渡上下文
            overlap_tail = current[-chunk_overlap:] if chunk_overlap > 0 else ""
            current = (overlap_tail + sentence).strip()

    if current.strip():
        chunks.append(current.strip())
    return chunks


def split_text(
    text: str,
    chunk_size: int = 500,
    chunk_overlap: int = 80,
    split_mode: str = "fixed",
) -> List[str]:
    """
    简单文本切分器（按字符切分），满足 MVP 需要。
    """
    content = (text or "").strip()
    if not content:
        return []

    if chunk_size <= 0:
        chunk_size = 500
    if chunk_overlap < 0:
        chunk_overlap = 0
    if chunk_overlap >= chunk_size:
        chunk_overlap = max(0, chunk_size // 5)

    mode = str(split_mode or "fixed").strip().lower()
    if mode == "adaptive":
        return _adaptive_split(content, chunk_size, chunk_overlap)
    return _fixed_split(content, chunk_size, chunk_overlap)
