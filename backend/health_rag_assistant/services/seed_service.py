"""
种子数据服务
- 从 datasets/ 目录加载默认知识语料（cMedQA 抽样 + 手工整理科普）
- 解析 md 格式样本，导入为 HealthKnowledgeDocument
- 构建初始 FAISS 索引
"""
import re
from pathlib import Path
from typing import Dict, List

from django.apps import apps
from django.conf import settings

from ..models import HealthKnowledgeDocument
from .kb_service import rebuild_document_index

DATASET_ROOT = Path(settings.BASE_DIR) / "health_rag_assistant" / "datasets"
DEFAULT_KB_SOURCE = (
    DATASET_ROOT
    / "cMedQA"
    / "health_qa_sample_for_rag.md"
)
CURATED_KB_DIR = DATASET_ROOT / "curated"
DEFAULT_KB_TITLE = "健康问答测试语料（cMedQA抽样）"
DEFAULT_KB_SEED = "default_health_rag_kb"


def _project_root() -> Path:
    return Path(settings.BASE_DIR).parent


def _default_source_prefix() -> str:
    try:
        return str(DEFAULT_KB_SOURCE.relative_to(_project_root()))
    except ValueError:
        return str(DEFAULT_KB_SOURCE)


def _source_prefix(path: Path) -> str:
    try:
        return str(path.relative_to(_project_root()))
    except ValueError:
        return str(path)


def _get_seed_owner_id() -> int:
    HertzUser = apps.get_model("hertz_studio_django_auth", "HertzUser")
    for username in ("hertz", "demo"):
        user = HertzUser.objects.filter(username=username, status=1).first()
        if user:
            return int(user.user_id)
    user = HertzUser.objects.filter(status=1).order_by("user_id").first()
    if not user:
        raise RuntimeError("未找到可用于初始化知识库的用户")
    return int(user.user_id)


def _active_seed_owner_ids() -> List[int]:
    return list(
        HealthKnowledgeDocument.objects.filter(
            status="active",
            metadata__seed=DEFAULT_KB_SEED,
        )
        .order_by("user_id")
        .values_list("user_id", flat=True)
        .distinct()
    )


def _sync_default_seed_indexes() -> Dict[str, object]:
    from .kb_service import sync_user_faiss_index

    owner_ids = _active_seed_owner_ids()
    if not owner_ids:
        owner_ids = [_get_seed_owner_id()]

    results: Dict[str, object] = {}
    for owner_id in owner_ids:
        ok, message = sync_user_faiss_index(owner_id)
        results[str(owner_id)] = {"ok": ok, "message": message}
    return {"owner_ids": owner_ids, "results": results}


def _split_default_samples(content: str) -> List[Dict[str, str]]:
    pattern = re.compile(
        r"^##\s*样本\s*(?P<number>\d+)\s*\n(?P<body>.*?)(?=^##\s*样本\s*\d+\s*\n|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    samples: List[Dict[str, str]] = []
    for match in pattern.finditer(content):
        number = match.group("number").strip()
        body = match.group("body").strip()
        question_match = re.search(r"问题[:：]\s*(.+?)(?=\n回答[:：])", body, re.DOTALL)
        answer_match = re.search(r"回答[:：]\s*(.+)$", body, re.DOTALL)
        question = re.sub(r"\s+", " ", question_match.group(1)).strip() if question_match else ""
        answer = re.sub(r"\s+", " ", answer_match.group(1)).strip() if answer_match else ""
        if not question and not answer:
            continue
        title_question = question[:36] + ("..." if len(question) > 36 else "")
        samples.append(
            {
                "number": number,
                "title": f"健康问答样本 {number}：{title_question}",
                "content": f"问题：{question}\n\n回答：{answer}".strip(),
            }
        )
    return samples


def _extract_labeled_field(body: str, label: str) -> str:
    match = re.search(
        rf"^{label}[:：]\s*(?P<value>.*?)(?=^\S+[:：]|\Z)",
        body,
        re.MULTILINE | re.DOTALL,
    )
    if not match:
        return ""
    return re.sub(r"\s+", " ", match.group("value")).strip()


def _split_curated_entries(path: Path) -> List[Dict[str, object]]:
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        return []

    pattern = re.compile(
        r"^##\s*条目\s*(?P<number>\d+)\s*\n(?P<body>.*?)(?=^##\s*条目\s*\d+\s*\n|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    entries: List[Dict[str, object]] = []
    dataset_name = path.stem
    for match in pattern.finditer(content):
        number = match.group("number").strip()
        body = match.group("body").strip()
        topic = _extract_labeled_field(body, "主题")
        question = _extract_labeled_field(body, "问题")
        answer = _extract_labeled_field(body, "回答")
        keywords_text = _extract_labeled_field(body, "关键词")
        keywords = [
            item.strip()
            for item in re.split(r"[、,，/|]", keywords_text)
            if item.strip()
        ]
        if not question and not answer:
            continue
        title_question = question[:36] + ("..." if len(question) > 36 else "")
        entries.append(
            {
                "number": number,
                "title": f"{topic or '健康科普'} {number}：{title_question}",
                "content": (
                    f"主题：{topic}\n\n"
                    f"问题：{question}\n\n"
                    f"回答：{answer}\n\n"
                    f"关键词：{'、'.join(keywords)}"
                ).strip(),
                "metadata": {
                    "seed": DEFAULT_KB_SEED,
                    "dataset": dataset_name,
                    "curated_no": int(number),
                    "topic": topic,
                    "keywords": keywords,
                    "purpose": "Windows client curated health knowledge base",
                },
                "source_path": f"{_source_prefix(path)}#entry-{number}",
            }
        )
    return entries


def _load_seed_entries() -> List[Dict[str, object]]:
    entries: List[Dict[str, object]] = []

    if DEFAULT_KB_SOURCE.exists():
        content = DEFAULT_KB_SOURCE.read_text(encoding="utf-8").strip()
        for sample in _split_default_samples(content):
            entries.append(
                {
                    "title": sample["title"],
                    "content": sample["content"],
                    "metadata": {
                        "seed": DEFAULT_KB_SEED,
                        "dataset": "cMedQA sample",
                        "sample_no": int(sample["number"]),
                        "purpose": "Windows client default knowledge base",
                    },
                    "source_path": f"{_default_source_prefix()}#sample-{sample['number']}",
                }
            )

    if CURATED_KB_DIR.exists():
        for path in sorted(CURATED_KB_DIR.glob("*.md")):
            entries.extend(_split_curated_entries(path))

    return entries


def seed_default_health_kb_if_empty(*, force: bool = False) -> Dict[str, object]:
    active_count = HealthKnowledgeDocument.objects.filter(status="active").count()
    seed_count = HealthKnowledgeDocument.objects.filter(
        status="active",
        metadata__seed=DEFAULT_KB_SEED,
    ).count()
    entries = _load_seed_entries()
    if active_count > 0 and seed_count == 0 and not force:
        return {
            "created": False,
            "message": "健康知识库已有文档，跳过默认语料初始化",
            "active_document_count": active_count,
        }
    if not entries:
        return {
            "created": False,
            "message": "默认健康知识库语料不存在或为空，跳过初始化",
            "active_document_count": active_count,
        }

    existing_source_paths = set(
        HealthKnowledgeDocument.objects.filter(
            status="active",
            metadata__seed=DEFAULT_KB_SEED,
        ).values_list("source_path", flat=True)
    )
    missing_entries = [
        entry for entry in entries if str(entry["source_path"]) not in existing_source_paths
    ]
    if not force and not missing_entries:
        index_sync = _sync_default_seed_indexes()
        return {
            "created": False,
            "message": "默认健康知识库样本文档已存在，跳过初始化",
            "active_document_count": active_count,
            "seed_document_count": seed_count,
            "expected_document_count": len(entries),
            "index_sync": index_sync,
        }

    if force:
        docs = list(
            HealthKnowledgeDocument.objects.filter(
                status="active",
                metadata__seed=DEFAULT_KB_SEED,
            )
        )
        doc_ids = [doc.id for doc in docs]
        if doc_ids:
            HealthKnowledgeDocument.objects.filter(id__in=doc_ids).update(status="deleted")
            for doc in docs:
                doc.chunks.all().delete()
        missing_entries = entries

    owner_id = _get_seed_owner_id()
    created_count = 0
    chunk_count = 0
    dataset_counts: Dict[str, int] = {}
    for entry in missing_entries:
        document = HealthKnowledgeDocument.objects.create(
            user_id=owner_id,
            title=str(entry["title"]),
            source_type="file",
            source_path=str(entry["source_path"]),
            content=str(entry["content"]),
            metadata=dict(entry["metadata"]),
            status="active",
        )
        created_chunks = rebuild_document_index(
            document=document,
            chunk_size=500,
            chunk_overlap=80,
        )
        created_count += 1
        chunk_count += created_chunks
        dataset = str(dict(entry["metadata"]).get("dataset", "unknown"))
        dataset_counts[dataset] = dataset_counts.get(dataset, 0) + 1

    index_sync = _sync_default_seed_indexes()
    active_after = HealthKnowledgeDocument.objects.filter(status="active").count()
    return {
        "created": True,
        "message": "默认健康知识库样本文档初始化完成",
        "document_count": created_count,
        "chunk_count": chunk_count,
        "active_document_count": active_after,
        "expected_document_count": len(entries),
        "dataset_counts": dataset_counts,
        "index_sync": index_sync,
    }


def normalize_default_health_kb_source_paths() -> Dict[str, object]:
    entries = _load_seed_entries()
    entry_map = {
        (
            (entry.get("metadata") or {}).get("dataset"),
            (entry.get("metadata") or {}).get("sample_no"),
            (entry.get("metadata") or {}).get("curated_no"),
        ): str(entry["source_path"])
        for entry in entries
    }
    docs = HealthKnowledgeDocument.objects.filter(
        status="active",
        metadata__seed=DEFAULT_KB_SEED,
    )
    updated_count = 0
    for doc in docs:
        metadata = doc.metadata or {}
        key = (
            metadata.get("dataset"),
            metadata.get("sample_no"),
            metadata.get("curated_no"),
        )
        expected_path = entry_map.get(key)
        if not expected_path:
            continue
        if doc.source_path != expected_path:
            doc.source_path = expected_path
            doc.save(update_fields=["source_path", "updated_at"])
            updated_count += 1
    return {
        "updated": updated_count,
        "expected_document_count": len(entries),
        "active_seed_document_count": docs.count(),
    }
