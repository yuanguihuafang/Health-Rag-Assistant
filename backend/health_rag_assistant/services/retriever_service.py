"""
本地检索服务（历史兼容模块）

职责：
1. 提供纯本地关键词/TF-IDF/哈希向量混合排序能力。
2. 仅用于推荐等非主问答链路的兼容检索。
3. 不包含 LangChain/FAISS 依赖，避免误导主链路架构。
"""
import hashlib
import math
import re
from collections import Counter
from difflib import SequenceMatcher
from typing import Dict, Iterable, List, Sequence, Set, Tuple

import numpy as np
from django.conf import settings

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    SKLEARN_AVAILABLE = True
except Exception:
    TfidfVectorizer = None  # type: ignore
    cosine_similarity = None  # type: ignore
    SKLEARN_AVAILABLE = False

LOW_CONFIDENCE_SCORE = 0.30
HIGH_RELEVANCE_LABEL = "高相关"
MEDIUM_RELEVANCE_LABEL = "较相关"
LOW_RELEVANCE_LABEL = "弱相关"

HEALTH_QUERY_EXPANSIONS: Dict[str, Sequence[str]] = {
    "失眠": ("睡不着", "入睡困难", "睡眠差", "早醒", "多梦", "熬夜"),
    "胃痛": ("胃疼", "胃部不适", "上腹痛", "反酸", "烧心"),
    "发烧": ("发热", "体温", "高热", "退烧"),
    "胸闷": ("胸口不舒服", "心慌", "心悸", "呼吸不顺"),
    "心悸": ("心慌", "心跳快", "胸闷"),
    "减肥": ("减脂", "体重管理", "运动", "饮食控制"),
    "血压": ("高血压", "血压监测", "低盐饮食", "慢病管理"),
}

HEALTH_TOPIC_KEYWORDS: Dict[str, Sequence[str]] = {
    "sleep": ("失眠", "睡不着", "入睡困难", "睡眠", "熬夜"),
    "digestive": ("胃", "肠", "消化", "腹痛", "腹泻", "便秘"),
    "cardio": ("血压", "心脏", "胸闷", "心悸", "心慌"),
    "weight": ("减肥", "减脂", "体重", "肥胖", "久坐", "运动"),
    "women": ("月经", "经期", "痛经", "妇科", "白带"),
    "men": ("前列腺", "阳痿", "早泄", "射精", "睾丸"),
    "urgent": ("胸痛", "出冷汗", "呼吸困难", "急诊", "立即就医"),
}

GENERIC_QUERY_TERMS: Set[str] = {
    "怎么办",
    "怎么",
    "怎么治疗",
    "怎么缓解",
    "怎么改善",
    "建议",
}


class SimpleEmbedder:
    """轻量哈希向量编码器。"""

    def __init__(self, n_features: int = 512):
        self.n_features = int(n_features)

    def _tokens(self, text: str) -> List[str]:
        raw = (text or "").lower()
        tokens: List[str] = []
        ascii_buf: List[str] = []
        cjk_chars: List[str] = []

        def flush_ascii() -> None:
            if ascii_buf:
                tokens.append("".join(ascii_buf))
                ascii_buf.clear()

        for char in raw:
            if "\u4e00" <= char <= "\u9fff":
                flush_ascii()
                cjk_chars.append(char)
                tokens.append(char)
                continue
            if char.isascii() and char.isalnum():
                ascii_buf.append(char)
            else:
                flush_ascii()
        flush_ascii()

        compact_cjk = "".join(cjk_chars)
        for n in (2, 3):
            if len(compact_cjk) >= n:
                tokens.extend(
                    compact_cjk[idx : idx + n]
                    for idx in range(0, len(compact_cjk) - n + 1)
                )
        return [token for token in tokens if token]

    def encode(self, text: str) -> List[float]:
        vector = np.zeros(self.n_features, dtype=float)
        for token in self._tokens(text):
            digest = hashlib.md5(token.encode("utf-8")).hexdigest()
            idx = int(digest[:8], 16) % self.n_features
            vector[idx] += 1.0
        norm = np.linalg.norm(vector) or 1.0
        return (vector / norm).astype(float).tolist()

    @staticmethod
    def similarity(vec_a: Iterable[float], vec_b: Iterable[float]) -> float:
        a = np.array(list(vec_a), dtype=float)
        b = np.array(list(vec_b), dtype=float)
        if a.size == 0 or b.size == 0 or a.shape != b.shape:
            return 0.0
        return float(np.dot(a, b))


def expand_health_query(question: str) -> str:
    text = (question or "").strip()
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


def _active_topic_keywords(expanded_query: str) -> Set[str]:
    active: Set[str] = set()
    for keywords in HEALTH_TOPIC_KEYWORDS.values():
        active.update(
            keyword
            for keyword in keywords
            if keyword in expanded_query and keyword not in GENERIC_QUERY_TERMS
        )
    return active


def relevance_label(score: float) -> str:
    score = float(score)
    if score >= 0.70:
        return HIGH_RELEVANCE_LABEL
    if score >= LOW_CONFIDENCE_SCORE:
        return MEDIUM_RELEVANCE_LABEL
    return LOW_RELEVANCE_LABEL


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip())


def _keyword_coverage_score(query: str, text: str) -> float:
    tokens = [tok for tok in re.split(r"[^0-9A-Za-z\u4e00-\u9fff]+", query) if tok]
    if not tokens:
        return 0.0
    hit = sum(1 for token in set(tokens) if token and token in text)
    return hit / max(len(set(tokens)), 1)


def _topic_boost(active_keywords: Set[str], text: str) -> float:
    if not active_keywords:
        return 0.0
    hits = sum(1 for keyword in active_keywords if keyword in text)
    return min(hits / max(len(active_keywords), 1), 1.0) * 0.18


def _tokenize_for_sparse(text: str) -> List[str]:
    raw = str(text or "").lower()
    tokens: List[str] = []
    ascii_buf: List[str] = []
    cjk_chars: List[str] = []

    def flush_ascii() -> None:
        if ascii_buf:
            tokens.append("".join(ascii_buf))
            ascii_buf.clear()

    for char in raw:
        if "\u4e00" <= char <= "\u9fff":
            flush_ascii()
            cjk_chars.append(char)
            tokens.append(char)
            continue
        if char.isascii() and char.isalnum():
            ascii_buf.append(char)
        else:
            flush_ascii()
    flush_ascii()

    compact_cjk = "".join(cjk_chars)
    for n in (2, 3):
        if len(compact_cjk) >= n:
            tokens.extend(
                compact_cjk[idx : idx + n]
                for idx in range(0, len(compact_cjk) - n + 1)
            )
    return [tok for tok in tokens if tok]


def _tfidf_score(query: str, texts: List[str]) -> List[float]:
    if not SKLEARN_AVAILABLE or not texts:
        return [0.0 for _ in texts]
    corpus = [query] + texts
    vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(2, 3), min_df=1)
    tfidf = vectorizer.fit_transform(corpus)
    q_vec = tfidf[0:1]
    d_vec = tfidf[1:]
    sims = cosine_similarity(q_vec, d_vec)[0]
    return [float(max(min(x, 1.0), 0.0)) for x in sims]


def _bm25_score(
    query: str,
    texts: List[str],
    *,
    k1: float = 1.5,
    b: float = 0.75,
) -> List[float]:
    if not texts:
        return []
    docs_tokens = [_tokenize_for_sparse(text) for text in texts]
    query_tokens = _tokenize_for_sparse(query)
    if not query_tokens:
        return [0.0 for _ in texts]

    avgdl = sum(len(tokens) for tokens in docs_tokens) / max(len(docs_tokens), 1)
    avgdl = max(avgdl, 1.0)
    df = Counter()
    for tokens in docs_tokens:
        df.update(set(tokens))
    total_docs = len(docs_tokens)

    raw_scores: List[float] = []
    for tokens in docs_tokens:
        dl = len(tokens)
        tf = Counter(tokens)
        score = 0.0
        for token in query_tokens:
            freq = tf.get(token, 0)
            if freq <= 0:
                continue
            n_q = df.get(token, 0)
            idf = math.log(1 + (total_docs - n_q + 0.5) / (n_q + 0.5))
            denom = freq + k1 * (1 - b + b * (dl / avgdl))
            score += idf * ((freq * (k1 + 1)) / max(denom, 1e-9))
        raw_scores.append(float(score))

    max_score = max(raw_scores) if raw_scores else 0.0
    if max_score <= 0:
        return [0.0 for _ in raw_scores]
    return [float(max(min(s / max_score, 1.0), 0.0)) for s in raw_scores]


def retrieve_top_k(question: str, chunks=None, k: int = 5, user_id: int = None):
    """
    轻量本地检索（仅兼容推荐场景）。
    """
    if chunks is None:
        return []

    expanded = expand_health_query(question)
    if not expanded:
        return []
    active_keywords = _active_topic_keywords(expanded)

    chunk_list = list(chunks)
    if not chunk_list:
        return []

    texts = [_normalize_text(chunk.chunk_text or "") for chunk in chunk_list]
    sparse_method = str(getattr(settings, "RAG_SPARSE_METHOD", "bm25")).strip().lower()
    if sparse_method == "tfidf":
        sparse_scores = _tfidf_score(expanded, texts)
    else:
        sparse_scores = _bm25_score(expanded, texts)

    embedder = SimpleEmbedder()
    q_vec = embedder.encode(expanded)
    scored: List[Tuple[float, object]] = []

    for idx, chunk in enumerate(chunk_list):
        text = texts[idx]
        if not text:
            continue
        hash_score = SimpleEmbedder.similarity(q_vec, embedder.encode(text))
        keyword_score = _keyword_coverage_score(expanded, text)
        seq_score = SequenceMatcher(None, expanded[:200], text[:300]).ratio()
        topic_score = _topic_boost(active_keywords, text)
        sparse_score = sparse_scores[idx] if idx < len(sparse_scores) else 0.0

        score = (
            0.38 * hash_score
            + 0.32 * sparse_score
            + 0.18 * keyword_score
            + 0.07 * seq_score
            + topic_score
        )
        scored.append((max(0.0, min(1.0, float(score))), chunk))

    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[: max(int(k), 1)]
