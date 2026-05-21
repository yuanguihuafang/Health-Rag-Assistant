"""
知识库服务
- 文档创建/更新/删除 + 分块 + 索引重建
- FAISS 索引同步（用户级 + 全局两份）
- 文件内容提取（utf-8 / gbk 等编码兜底）
"""
from typing import Iterable, Optional, Tuple

from ..models import HealthKnowledgeChunk, HealthKnowledgeDocument
from ..utils.text_splitter import split_text
from .retriever_service import SimpleEmbedder, build_faiss_index_for_user


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
    embedder: Optional[SimpleEmbedder] = None,
) -> int:
    embedder = embedder or SimpleEmbedder()
    HealthKnowledgeChunk.objects.filter(document=document).delete()

    chunks = split_text(
        document.content, chunk_size=chunk_size, chunk_overlap=chunk_overlap
    )
    created = 0
    for idx, chunk_text in enumerate(chunks):
        embedding = embedder.encode(chunk_text)
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
    return created


def sync_user_faiss_index(user_id: int) -> Tuple[bool, str]:
    """
    兼容历史函数名：当前检索使用全局共享候选，但同时维护调用方用户
    的 manifest，避免管理页看到旧的 user_N 索引状态。
    """
    chunks = (
        HealthKnowledgeChunk.objects.filter(document__status="active")
        .select_related("document")
        .order_by("document_id", "chunk_index")
    )
    chunk_list = list(chunks)
    user_id = int(user_id or 0)
    ok, message = build_faiss_index_for_user(user_id=user_id, chunks=chunk_list)
    if user_id == 0:
        return ok, message

    global_ok, global_message = build_faiss_index_for_user(user_id=0, chunks=chunk_list)
    return (
        bool(ok and global_ok),
        f"user_{user_id}: {message}; user_0: {global_message}",
    )


def rebuild_index_for_documents(
    documents: Iterable[HealthKnowledgeDocument],
    chunk_size: int = 500,
    chunk_overlap: int = 80,
) -> int:
    total = 0
    embedder = SimpleEmbedder()
    owner_user_id = None
    for document in documents:
        if owner_user_id is None:
            owner_user_id = document.user_id
        total += rebuild_document_index(
            document=document,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            embedder=embedder,
        )
    if owner_user_id is not None:
        sync_user_faiss_index(owner_user_id)
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
    sync_user_faiss_index(user_id=user_id)
    return document, created_chunks


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
        sync_user_faiss_index(user_id=document.user_id)
    return document, created_chunks
