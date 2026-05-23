"""
知识库服务
- 文档创建/更新/删除 + 分块 + 向量索引重建
- Qdrant 向量同步（按 chunk_id 作为 point id）
- 文件内容提取（utf-8 / gbk 等编码兜底）
"""
from typing import Callable, Iterable, Optional, Tuple

from django.conf import settings
from ..models import HealthKnowledgeChunk, HealthKnowledgeDocument
from ..utils.text_splitter import split_text
from .embedding_service import EmbeddingService
from .structured_markdown_service import parse_markdown_entries
from .vector_store import QdrantVectorStore


def _extract_text_from_file(uploaded_file) -> str:
    if not uploaded_file:
        return ""
    content = uploaded_file.read()
    if not content:
        return ""

    # 常见文本编码兜底
    for encoding in ("utf-8", "utf-8-sig", "gbk", "gb2312"):
        try:
            return content.decode(encoding)
        except Exception:
            continue
    return content.decode("utf-8", errors="ignore")


def rebuild_document_index(
    document: HealthKnowledgeDocument,
    chunk_size: int = 500,
    chunk_overlap: int = 80,
    embedder: Optional[EmbeddingService] = None,
    progress_callback: Optional[Callable[[int], None]] = None,
) -> int:
    embedder = embedder or EmbeddingService()
    old_chunk_ids = list(
        HealthKnowledgeChunk.objects.filter(document=document).values_list("id", flat=True)
    )
    if old_chunk_ids:
        QdrantVectorStore().delete_chunks(old_chunk_ids)
    HealthKnowledgeChunk.objects.filter(document=document).delete()

    chunks = split_text(
        document.content, chunk_size=chunk_size, chunk_overlap=chunk_overlap
    )
    if not chunks:
        return 0

    batch_size = max(int(getattr(settings, "EMBEDDING_BATCH_SIZE", 64)), 1)
    vectors = []
    for i in range(0, len(chunks), batch_size):
        batch_texts = chunks[i : i + batch_size]
        vectors.extend(embedder.embed_documents(batch_texts))

    created = 0
    for idx, chunk_text in enumerate(chunks):
        embedding = vectors[idx] if idx < len(vectors) else []
        token_count = len(chunk_text.split())
        HealthKnowledgeChunk.objects.create(
            document=document,
            chunk_index=idx,
            chunk_text=chunk_text,
            token_count=token_count,
            vector_id=idx,
            embedding=embedding,
        )
        created += 1
    if progress_callback:
        progress_callback(created)
    return created


def _build_chunk_payload(chunk: HealthKnowledgeChunk) -> dict:
    return {
        "chunk_id": int(chunk.id),
        "document_id": int(chunk.document_id),
        "document_title": chunk.document.title,
        "source_path": chunk.document.source_path,
        "chunk_index": int(chunk.chunk_index),
    }


def upsert_chunks_to_vector_store(
    chunks: Iterable[HealthKnowledgeChunk],
    *,
    embedder: Optional[EmbeddingService] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> int:
    """
    增量同步本次新增/更新的 chunk 到 Qdrant。

    管理后台上传文档时不再重建整库，只补齐缺失 embedding 并 upsert 当前 chunk，
    用于降低超时概率，也让 SQLite 与 Qdrant 更容易保持一致。
    """
    chunk_list = list(chunks)
    if not chunk_list:
        return 0

    embedder = embedder or EmbeddingService()
    vector_store = QdrantVectorStore()
    batch_size = max(int(getattr(settings, "EMBEDDING_BATCH_SIZE", 10)), 1)
    inserted = 0
    total = len(chunk_list)

    for start in range(0, total, batch_size):
        batch_chunks = chunk_list[start : start + batch_size]
        vectors = []
        missing_chunks = []
        missing_positions = []
        for idx, chunk in enumerate(batch_chunks):
            embedding = chunk.embedding or []
            if embedding:
                vectors.append(embedding)
                continue
            vectors.append([])
            missing_chunks.append(chunk)
            missing_positions.append(idx)

        if missing_chunks:
            texts = [chunk.chunk_text or "" for chunk in missing_chunks]
            missing_vectors = embedder.embed_documents(texts)
            for pos, vector in zip(missing_positions, missing_vectors):
                vectors[pos] = vector
            for chunk, vector in zip(missing_chunks, missing_vectors):
                chunk.embedding = vector
                chunk.save(update_fields=["embedding"])

        payloads = [_build_chunk_payload(chunk) for chunk in batch_chunks]
        inserted += vector_store.upsert_chunks(
            chunk_ids=[int(chunk.id) for chunk in batch_chunks],
            vectors=vectors,
            payloads=payloads,
        )
        if progress_callback:
            progress_callback(inserted, total)

    return inserted


def sync_vector_index(
    user_id: int,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> Tuple[bool, str]:
    """
    兼容历史函数名：将 active chunk 同步到 Qdrant。
    """
    _ = int(user_id or 0)
    chunks_qs = (
        HealthKnowledgeChunk.objects.filter(document__status="active")
        .select_related("document")
        .order_by("document_id", "chunk_index")
    )
    chunks = list(chunks_qs)
    if not chunks:
        QdrantVectorStore().clear_collection()
        return True, "无可索引分块，已清空向量索引"

    embedder = EmbeddingService()
    vector_store = QdrantVectorStore()

    batch_size = max(int(getattr(settings, "EMBEDDING_BATCH_SIZE", 10)), 1)
    inserted = 0
    collection_ready = False
    total_chunks = len(chunks)
    for start in range(0, total_chunks, batch_size):
        batch_chunks = chunks[start : start + batch_size]
        vectors = []
        missing_chunks = []
        missing_positions = []
        for idx, chunk in enumerate(batch_chunks):
            embedding = chunk.embedding or []
            if embedding:
                vectors.append(embedding)
                continue
            vectors.append([])
            missing_chunks.append(chunk)
            missing_positions.append(idx)
        if missing_chunks:
            texts = [chunk.chunk_text or "" for chunk in missing_chunks]
            missing_vectors = embedder.embed_documents(texts)
            for pos, vector in zip(missing_positions, missing_vectors):
                vectors[pos] = vector
            for chunk, vector in zip(missing_chunks, missing_vectors):
                chunk.embedding = vector
                chunk.save(update_fields=["embedding"])
        if not vectors:
            continue
        if not collection_ready:
            vector_store.recreate_collection(vector_size=len(vectors[0]))
            collection_ready = True
        payloads = [_build_chunk_payload(chunk) for chunk in batch_chunks]
        inserted += vector_store.upsert_chunks(
            chunk_ids=[int(chunk.id) for chunk in batch_chunks],
            vectors=vectors,
            payloads=payloads,
        )
        if progress_callback:
            progress_callback(inserted, total_chunks)
    return True, f"Qdrant 索引已同步，分块数: {inserted}"


def rebuild_index_for_documents(
    documents: Iterable[HealthKnowledgeDocument],
    chunk_size: int = 500,
    chunk_overlap: int = 80,
    progress_callback: Optional[Callable[[int, int, int], None]] = None,
) -> int:
    total = 0
    embedder = EmbeddingService()
    owner_user_id = None
    document_list = list(documents)
    total_docs = len(document_list)
    for idx, document in enumerate(document_list, start=1):
        if owner_user_id is None:
            owner_user_id = document.user_id
        created = rebuild_document_index(
            document=document,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            embedder=embedder,
        )
        total += created
        if progress_callback:
            progress_callback(idx, total_docs, total)
    if owner_user_id is not None:
        sync_vector_index(owner_user_id)
    return total


def create_document_and_index(
    *,
    user_id: int,
    title: str,
    source_type: str,
    source_path: str = "",
    content: str = "",
    metadata: Optional[dict] = None,
    uploaded_file=None,
    chunk_size: int = 500,
    chunk_overlap: int = 80,
    split_mode: str = "fixed",
) -> Tuple[HealthKnowledgeDocument, int]:
    text_content = (content or "").strip()
    if uploaded_file and not text_content:
        text_content = _extract_text_from_file(uploaded_file).strip()

    document = HealthKnowledgeDocument.objects.create(
        user_id=user_id,
        title=title.strip(),
        source_type=source_type,
        source_path=(source_path or "").strip(),
        content=text_content,
        status="active",
        metadata=metadata or {},
    )
    created_chunks = rebuild_document_index(
        document=document,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    upsert_chunks_to_vector_store(
        document.chunks.select_related("document").order_by("chunk_index")
    )
    return document, created_chunks


def create_structured_markdown_documents_and_index(
    *,
    user_id: int,
    title: str,
    source_path: str,
    content: str = "",
    metadata: Optional[dict] = None,
    uploaded_file=None,
) -> Tuple[HealthKnowledgeDocument, int, int, int]:
    text_content = (content or "").strip()
    if uploaded_file and not text_content:
        text_content = _extract_text_from_file(uploaded_file).strip()

    entries = parse_markdown_entries(text_content)
    if not entries:
        raise ValueError("未解析到 `## 条目 xxx` 结构，请确认 Markdown 排版")

    first_document = None
    created_documents = 0
    created_chunks = 0
    skipped_existing = 0
    created_chunk_objects = []
    base_metadata = metadata or {}
    source_label = (source_path or "").strip()
    title_prefix = (title or source_label or "结构化知识").strip()
    entry_source_paths = [
        f"{source_label}#entry={entry['entry_no']}" if source_label else f"entry={entry['entry_no']}"
        for entry in entries
    ]
    existing_by_source_path = {
        doc.source_path: doc
        for doc in HealthKnowledgeDocument.objects.filter(
            status="active", source_path__in=entry_source_paths
        )
    }

    for entry in entries:
        entry_source_path = f"{source_label}#entry={entry['entry_no']}" if source_label else f"entry={entry['entry_no']}"
        existing_document = existing_by_source_path.get(entry_source_path)
        if existing_document:
            if first_document is None:
                first_document = existing_document
            skipped_existing += 1
            continue
        entry_title = f"{title_prefix} 条目 {entry['entry_no']}：{entry['question'][:40]}"
        entry_metadata = {
            **base_metadata,
            "split_mode": "markdown_entry",
            "source_file": source_label,
            "entry_no": entry["entry_no"],
            "topic": entry["topic"],
            "keywords": entry["keywords"],
        }
        document = HealthKnowledgeDocument.objects.create(
            user_id=user_id,
            title=entry_title,
            source_type="file",
            source_path=entry_source_path,
            content=entry["content"],
            status="active",
            metadata=entry_metadata,
        )
        chunk = HealthKnowledgeChunk.objects.create(
            document=document,
            chunk_index=0,
            chunk_text=entry["content"],
            token_count=len(entry["content"].split()),
            vector_id=0,
            embedding=[],
        )
        created_chunk_objects.append(chunk)
        if first_document is None:
            first_document = document
        created_documents += 1
        created_chunks += 1

    upsert_chunks_to_vector_store(created_chunk_objects)
    return first_document, created_documents, created_chunks, skipped_existing


def update_document_and_index(
    *,
    document: HealthKnowledgeDocument,
    title: Optional[str] = None,
    source_path: Optional[str] = None,
    content: Optional[str] = None,
    metadata: Optional[dict] = None,
    reindex: bool = False,
    chunk_size: int = 500,
    chunk_overlap: int = 80,
) -> Tuple[HealthKnowledgeDocument, int]:
    if title is not None:
        document.title = title.strip()
    if source_path is not None:
        document.source_path = source_path.strip()
    if content is not None:
        document.content = content.strip()
    if metadata is not None:
        document.metadata = metadata

    document.save()

    created_chunks = 0
    if reindex:
        created_chunks = rebuild_document_index(
            document=document,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        upsert_chunks_to_vector_store(
            document.chunks.select_related("document").order_by("chunk_index")
        )
    return document, created_chunks
