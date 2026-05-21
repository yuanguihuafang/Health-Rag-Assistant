"""
检索器——健康 RAG 的核心检索引擎
- 纯本地混合重排：哈希相似度 + TF-IDF + 关键词命中 + 主题加成
- 健康领域同义词扩展（40+ 组症状映射）
- 13 个健康主题分类与 topic boost
- FAISS 索引维护（仅构建/状态展示，检索走本地重排）
"""
import hashlib
import json
import re
import shutil
from difflib import SequenceMatcher
from pathlib import Path
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

LANGCHAIN_FAISS_AVAILABLE = False
EMBEDDING_ENGINE = "hybrid-char-ngram-tfidf-keyword-v1"
MIN_SOURCE_SCORE = 0.18
LOW_CONFIDENCE_SCORE = 0.30

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
    "调理": ("改善", "缓解", "建议", "生活规律", "规律作息", "注意休息"),
    "怎么办": ("怎么治疗", "怎么缓解", "怎么改善", "建议"),
    "怎么": ("怎么办", "怎么治疗", "怎么缓解", "怎么改善", "建议"),
}

HEALTH_TOPIC_KEYWORDS: Dict[str, Sequence[str]] = {
    "sleep": (
        "失眠",
        "睡不着",
        "入睡困难",
        "睡眠",
        "睡眠差",
        "睡眠非常差",
        "睡眠不足",
        "早醒",
        "多梦",
        "熬夜",
        "作息",
        "休息",
    ),
    "digestive": ("胃", "肠", "消化", "腹痛", "腹泻", "便秘", "胃炎", "胃痛"),
    "cold": ("感冒", "发烧", "咳嗽", "鼻塞", "喉咙", "流感", "免疫"),
    "pediatric": ("儿科", "儿童发热", "宝宝发热", "宝宝积食", "儿童消化", "婴儿喂养", "小孩发烧", "积食", "喂养"),
    "skin": ("皮肤", "湿疹", "过敏", "瘙痒", "皮炎", "痤疮", "红肿"),
    "cardio": ("血压", "心脏", "胸闷", "心悸", "心慌", "心跳", "胸口", "血脂"),
    "bone": ("关节", "膝盖", "腰痛", "颈椎", "肩周", "扭伤"),
    "weight": ("减肥", "减脂", "体重", "肥胖", "久坐", "运动", "锻炼", "热量", "饮食控制"),
    "emotion": ("焦虑", "抑郁", "压力", "情绪", "烦躁", "紧张"),
    "women": ("月经", "经期", "痛经", "妇科", "怀孕", "孕期", "白带", "乳腺", "盆腔", "小腹痛"),
    # “男性/女性”本身只是人群背景，不能单独触发专科主题，否则“男性久坐/减肥”
    # 会被误导到男性泌尿资料。男性健康只由明确专科症状触发。
    "men": ("前列腺", "阳痿", "早泄", "射精", "包皮", "睾丸"),
    "urgent": ("胸痛", "出冷汗", "呼吸困难", "嘴唇发紫", "昏迷", "抽搐", "急诊", "立即就医"),
}

BACKGROUND_ONLY_TERMS: Set[str] = {"男性", "女性", "宝宝", "婴儿", "儿童", "小孩", "孩子", "老人", "老年"}

HIGH_RELEVANCE_LABEL = "高相关"
MEDIUM_RELEVANCE_LABEL = "较相关"
LOW_RELEVANCE_LABEL = "弱相关"
GENERIC_QUERY_TERMS: Set[str] = {
    "怎么办",
    "怎么",
    "怎么治疗",
    "怎么缓解",
    "怎么改善",
    "建议",
    "需要去医院吗",
    "正常吗",
}

TOPIC_HINTS: Dict[str, Sequence[str]] = {
    "sleep": ("睡眠作息", "睡眠", "失眠"),
    "digestive": ("饮食肠胃", "消化", "肠胃", "胃", "反酸", "便秘", "腹泻"),
    "pediatric": ("儿童母婴", "儿童", "宝宝", "婴儿", "儿科", "喂养"),
    "cardio": ("心血管", "胸闷", "心悸", "心慌", "血压", "心脏"),
    "urgent": ("急症风险", "急诊", "立即就医", "胸痛", "呼吸困难"),
    "women": ("女性孕产", "女性健康", "妇科", "月经", "经期", "痛经", "怀孕"),
    "men": ("男性泌尿", "男性健康", "前列腺", "阳痿", "早泄", "射精", "包皮", "睾丸"),
    "bone": ("骨骼关节", "膝盖", "膝关节", "运动损伤", "关节"),
    "weight": ("运动体重", "体重管理", "减肥", "减脂", "肥胖", "运动", "锻炼", "久坐", "饮食"),
    "emotion": ("情绪心理", "焦虑", "压力", "睡不好"),
    "skin": ("皮肤过敏", "皮肤", "过敏", "瘙痒", "红疹"),
}

QUESTION_SUFFIXES: Sequence[str] = (
    "需要去医院吗",
    "怎么处理",
    "怎么缓解",
    "怎么改善",
    "怎么办",
    "正常吗",
    "需要重视吗",
    "要不要马上处理",
    "要不要马上去医院",
)
try:
    from langchain_community.vectorstores import FAISS

    LANGCHAIN_FAISS_AVAILABLE = True
except Exception:
    FAISS = None  # type: ignore


class SimpleEmbedder:
    """
    轻量哈希向量编码器。
    说明：
    1) 作为纯 Python 回退检索方案
    2) 作为 LangChain+FAISS 的 embedding 实现（避免强依赖 sentence-transformers）
    """

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

        # 中文连续字符加入 2/3-gram，提升“失眠”等短问题与长知识片段的匹配。
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
        if a.size == 0 or b.size == 0:
            return 0.0
        if a.shape != b.shape:
            return 0.0
        return float(np.dot(a, b))


class HashEmbeddings:
    """
    LangChain Embeddings 兼容实现（基于 SimpleEmbedder）。
    """

    def __init__(self, n_features: int = 512):
        self.embedder = SimpleEmbedder(n_features=n_features)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self.embedder.encode(text) for text in texts]

    def embed_query(self, text: str) -> List[float]:
        return self.embedder.encode(text)


def _embedding_features() -> int:
    try:
        value = int(getattr(settings, "HEALTH_RAG_EMBEDDING_DIM", 512))
        if value <= 0:
            return 512
        return value
    except Exception:
        return 512


def _faiss_root() -> Path:
    configured = getattr(settings, "HEALTH_RAG_FAISS_ROOT", "")
    if configured:
        return Path(str(configured))
    base_dir = Path(getattr(settings, "BASE_DIR", Path(".")))
    return base_dir / "data" / "health_rag" / "faiss"


def _user_faiss_dir(user_id: int) -> Path:
    return _faiss_root() / f"user_{int(user_id)}"


def _write_manifest(user_id: int, chunk_count: int) -> None:
    manifest = {
        "user_id": int(user_id),
        "chunk_count": int(chunk_count),
        "embedding_dim": _embedding_features(),
        "engine": EMBEDDING_ENGINE,
    }
    root = _user_faiss_dir(user_id)
    root.mkdir(parents=True, exist_ok=True)
    (root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def build_faiss_index_for_user(user_id: int, chunks: Iterable) -> Tuple[bool, str]:
    """
    为用户构建并持久化 FAISS 索引。
    返回：(是否成功, 描述信息)
    """
    user_id = int(user_id)
    chunks = list(chunks)
    target_dir = _user_faiss_dir(user_id)

    if not LANGCHAIN_FAISS_AVAILABLE:
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)
        return False, "LangChain/FAISS 依赖未安装，使用回退检索"

    if not chunks:
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)
        return True, "无可索引分块，已清理 FAISS 索引"

    texts = []
    metadatas = []
    for chunk in chunks:
        texts.append(chunk.chunk_text or "")
        metadatas.append(
            {
                "chunk_id": chunk.id,
                "document_id": chunk.document_id,
                "document_title": getattr(chunk.document, "title", ""),
                "chunk_index": chunk.chunk_index,
            }
        )

    embeddings = HashEmbeddings(n_features=_embedding_features())
    vector_store = FAISS.from_texts(
        texts=texts,
        embedding=embeddings,
        metadatas=metadatas,
    )

    if target_dir.exists():
        shutil.rmtree(target_dir, ignore_errors=True)
    target_dir.mkdir(parents=True, exist_ok=True)
    vector_store.save_local(str(target_dir))
    _write_manifest(user_id=user_id, chunk_count=len(chunks))
    return True, f"FAISS 索引已更新，分块数: {len(chunks)}"


def _similarity_from_faiss_score(raw_score: float) -> float:
    # LangChain FAISS 默认返回的是 L2 距离，距离越小越相似
    score = float(raw_score)
    return 1.0 / (1.0 + max(score, 0.0))


def expand_health_query(question: str) -> str:
    text = (question or "").strip()
    if not text:
        return ""

    terms: List[str] = [text]
    for trigger, expansions in HEALTH_QUERY_EXPANSIONS.items():
        if trigger in text:
            terms.extend(expansions)

    seen: Set[str] = set()
    deduped: List[str] = []
    for term in terms:
        term = str(term or "").strip()
        if term and term not in seen:
            seen.add(term)
            deduped.append(term)
    return " ".join(deduped)


def _active_topic_keywords(expanded_query: str) -> Set[str]:
    active: Set[str] = set()
    for keywords in HEALTH_TOPIC_KEYWORDS.values():
        active.update(
            keyword
            for keyword in keywords
            if keyword in expanded_query
            and keyword not in GENERIC_QUERY_TERMS
            and keyword not in BACKGROUND_ONLY_TERMS
        )
    for term in expanded_query.split():
        if len(term) >= 2 and term not in GENERIC_QUERY_TERMS and term not in BACKGROUND_ONLY_TERMS:
            active.add(term)
    return active


def _detect_query_topics(expanded_query: str) -> Set[str]:
    topics: Set[str] = set()
    for topic, keywords in HEALTH_TOPIC_KEYWORDS.items():
        if any(keyword in expanded_query for keyword in keywords):
            topics.add(topic)
    return topics


def _keyword_score(chunk_text: str, active_keywords: Set[str]) -> float:
    if not active_keywords:
        return 0.0
    text = chunk_text or ""
    question_part = text.split("回答", 1)[0]
    weighted_hits = 0.0
    for keyword in active_keywords:
        if keyword in question_part:
            weighted_hits += 2.0
        elif keyword in text:
            weighted_hits += 1.0
    if weighted_hits <= 0:
        return 0.0
    return min(1.0, weighted_hits / 5.0)


def _topic_boost_score(chunk, query_topics: Set[str], active_keywords: Set[str]) -> float:
    if not query_topics:
        return 0.0

    document = getattr(chunk, "document", None)
    metadata = getattr(document, "metadata", {}) or {}
    topic_text = " ".join(
        str(value or "")
        for value in (
            metadata.get("topic"),
            metadata.get("dataset"),
            getattr(document, "title", ""),
        )
    )
    chunk_text = chunk.chunk_text or ""
    question_part = chunk_text.split("回答", 1)[0]
    score = 0.0

    for topic in query_topics:
        hints = TOPIC_HINTS.get(topic, ())
        if hints and any(hint in topic_text for hint in hints):
            score += 0.45
        if hints and any(hint in question_part for hint in hints):
            score += 0.30

    matched_keywords = sum(1 for keyword in active_keywords if keyword in question_part)
    if matched_keywords:
        score += min(0.25, matched_keywords * 0.08)

    return min(1.0, score)


def _tfidf_scores(expanded_query: str, chunk_texts: List[str]) -> List[float]:
    if not SKLEARN_AVAILABLE or not chunk_texts or not expanded_query.strip():
        return [0.0 for _ in chunk_texts]
    try:
        vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(1, 3))
        matrix = vectorizer.fit_transform([expanded_query] + chunk_texts)
        scores = cosine_similarity(matrix[0:1], matrix[1:]).flatten()  # type: ignore[misc]
        return [float(max(0.0, min(1.0, score))) for score in scores]
    except Exception:
        return [0.0 for _ in chunk_texts]


def relevance_label(score: float) -> str:
    score = float(score or 0.0)
    if score >= 0.70:
        return HIGH_RELEVANCE_LABEL
    if score >= LOW_CONFIDENCE_SCORE:
        return MEDIUM_RELEVANCE_LABEL
    return LOW_RELEVANCE_LABEL


def _chunk_question_text(chunk) -> str:
    text = chunk.chunk_text or ""
    match = re.search(r"问题[:：]\s*(.*?)(?:\n+回答[:：]|回答[:：]|\Z)", text, re.DOTALL)
    if match:
        return re.sub(r"\s+", "", match.group(1)).strip()
    document = getattr(chunk, "document", None)
    title = getattr(document, "title", "") if document else ""
    return str(title or "")


def _normalize_candidate_key(chunk) -> str:
    text = _chunk_question_text(chunk)
    text = re.sub(r"^.*?[：:]", "", text)
    text = re.sub(r"[\s，,。！？!？；;：:（）()【】\\[\\]《》<>、#\\-—_]+", "", text)
    changed = True
    while changed:
        changed = False
        for suffix in QUESTION_SUFFIXES:
            if text.endswith(suffix):
                text = text[: -len(suffix)]
                changed = True
    return text


def _mechanical_question_penalty(chunk) -> float:
    text = _chunk_question_text(chunk)
    compact = re.sub(r"\s+", "", text)
    penalty = 0.0
    for suffix in QUESTION_SUFFIXES:
        if compact.endswith(f"{suffix}怎么办"):
            penalty += 0.04
        if compact.endswith(f"{suffix}正常吗"):
            penalty += 0.03
    if compact.count("怎么办") > 1:
        penalty += 0.05
    return min(0.12, penalty)


def _calibrate_relevance_score(
    *,
    raw_score: float,
    tfidf_score: float,
    keyword_score: float,
    topic_score: float,
) -> float:
    """
    将内部混合分映射成客户更容易理解的 0~1 相关性分。
    只有主题和关键词都明确命中的候选才会进入高相关区间，避免弱相关被抬高。
    """
    raw_score = float(raw_score or 0.0)
    tfidf_score = float(tfidf_score or 0.0)
    keyword_score = float(keyword_score or 0.0)
    topic_score = float(topic_score or 0.0)

    if raw_score >= 0.34 and topic_score >= 0.45 and keyword_score >= 0.20:
        calibrated = (
            0.70
            + min(0.08, max(0.0, raw_score - 0.34) * 0.28)
            + min(0.08, topic_score * 0.08)
            + min(0.06, keyword_score * 0.06)
            + min(0.04, tfidf_score * 0.12)
        )
        return min(0.96, calibrated)

    if raw_score >= 0.24 and topic_score >= 0.45:
        return min(0.69, raw_score + min(0.12, topic_score * 0.12))

    return raw_score


def _is_near_duplicate(candidate_key: str, existing_keys: Sequence[str]) -> bool:
    if not candidate_key:
        return False
    for key in existing_keys:
        if not key:
            continue
        if candidate_key == key:
            return True
        shorter = min(len(candidate_key), len(key))
        if shorter >= 8 and (candidate_key in key or key in candidate_key):
            return True
        if shorter >= 10 and SequenceMatcher(None, candidate_key, key).ratio() >= 0.88:
            return True
    return False


def _dedupe_scored_results(scored: Sequence[Tuple[float, object]], k: int):
    selected = []
    selected_keys: List[str] = []
    for score, chunk in scored:
        key = _normalize_candidate_key(chunk)
        if _is_near_duplicate(key, selected_keys):
            continue
        selected.append((score, chunk))
        selected_keys.append(key)
        if len(selected) >= k:
            break
    return selected


def _retrieve_top_k_simple(question: str, chunks, k: int = 5):
    embedder = SimpleEmbedder(n_features=_embedding_features())
    expanded_query = expand_health_query(question)
    active_keywords = _active_topic_keywords(expanded_query)
    query_topics = _detect_query_topics(expanded_query)
    q_emb = embedder.encode(expanded_query or question)
    chunk_list = list(chunks)
    chunk_texts = [chunk.chunk_text or "" for chunk in chunk_list]
    tfidf_scores = _tfidf_scores(expanded_query or question, chunk_texts)
    scored = []
    for idx, chunk in enumerate(chunk_list):
        # 直接按当前分词策略计算，兼容旧数据库中已经保存的老 embedding。
        hash_score = embedder.similarity(q_emb, embedder.encode(chunk.chunk_text or ""))
        tfidf_score = tfidf_scores[idx] if idx < len(tfidf_scores) else 0.0
        keyword_score = _keyword_score(chunk.chunk_text or "", active_keywords)
        topic_score = _topic_boost_score(chunk, query_topics, active_keywords)
        score = (
            (0.40 * hash_score)
            + (0.30 * tfidf_score)
            + (0.18 * keyword_score)
            + (0.12 * topic_score)
        )
        score = _calibrate_relevance_score(
            raw_score=score,
            tfidf_score=tfidf_score,
            keyword_score=keyword_score,
            topic_score=topic_score,
        )
        score = float(score) - _mechanical_question_penalty(chunk)
        scored.append((min(1.0, max(0.0, score)), chunk))
    scored.sort(key=lambda item: item[0], reverse=True)
    return _dedupe_scored_results(scored, k=k)


def _retrieve_top_k_from_faiss(question: str, user_id: int, k: int = 5):
    if not LANGCHAIN_FAISS_AVAILABLE:
        return []

    target_dir = _user_faiss_dir(user_id)
    if not target_dir.exists():
        return []
    manifest_path = target_dir / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            manifest = {}
        if manifest.get("engine") != EMBEDDING_ENGINE:
            return []

    embeddings = HashEmbeddings(n_features=_embedding_features())
    vector_store = FAISS.load_local(
        str(target_dir),
        embeddings=embeddings,
        allow_dangerous_deserialization=True,
    )
    docs_with_scores = vector_store.similarity_search_with_score(question, k=k)
    if not docs_with_scores:
        return []

    # 延迟导入避免循环依赖
    from ..models import HealthKnowledgeChunk

    ordered_chunk_ids = []
    score_map = {}
    for doc, raw_score in docs_with_scores:
        metadata = getattr(doc, "metadata", {}) or {}
        chunk_id = metadata.get("chunk_id")
        if not chunk_id:
            continue
        chunk_id = int(chunk_id)
        ordered_chunk_ids.append(chunk_id)
        score_map[chunk_id] = _similarity_from_faiss_score(raw_score)

    if not ordered_chunk_ids:
        return []

    chunks = (
        HealthKnowledgeChunk.objects.filter(id__in=ordered_chunk_ids)
        .select_related("document")
        .all()
    )
    chunk_map = {chunk.id: chunk for chunk in chunks}

    results = []
    for chunk_id in ordered_chunk_ids:
        chunk = chunk_map.get(chunk_id)
        if not chunk:
            continue
        results.append((score_map.get(chunk_id, 0.0), chunk))
    return results


def retrieve_top_k(
    question: str,
    chunks=None,
    k: int = 5,
    user_id: int = None,
):
    """
    统一检索入口：
    使用纯本地混合重排：
    1) char n-gram 哈希相似度
    2) 中文字符 TF-IDF
    3) 健康主题关键词命中

    FAISS 索引仍保留用于兼容索引构建和状态展示，但问答侧不再让
    FAISS 先截断候选，避免弱相关片段被提前放大。
    """
    if chunks is None:
        from ..models import HealthKnowledgeChunk

        chunks = (
            HealthKnowledgeChunk.objects.filter(document__status="active")
            .select_related("document")
            .order_by("document_id", "chunk_index")
        )

    return _retrieve_top_k_simple(question=question, chunks=chunks, k=k)


def faiss_runtime_status(user_id: int) -> dict:
    target_dir = _user_faiss_dir(user_id)
    manifest_path = target_dir / "manifest.json"
    manifest = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            manifest = {}
    return {
        "langchain_faiss_available": LANGCHAIN_FAISS_AVAILABLE,
        "index_dir": str(target_dir),
        "index_exists": target_dir.exists(),
        "manifest": manifest,
    }
