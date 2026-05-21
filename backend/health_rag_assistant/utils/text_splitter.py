"""
文本切分器
- 按字符切分（简单实现，满足 MVP 需求）
- 支持 chunk_size 和 chunk_overlap 配置
"""
from typing import List


def split_text(text: str, chunk_size: int = 500, chunk_overlap: int = 80) -> List[str]:
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
