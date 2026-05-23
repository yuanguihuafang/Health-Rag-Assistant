"""
健康知识库去重命令

按 question_id 和正文 hash 识别重复文档，保留每组中最适合溯源的一条。
重复文档会标记为 deleted，重复 chunk 会从 SQLite 删除，并同步删除 Qdrant point。
"""
import hashlib
import re
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from ...models import HealthKnowledgeChunk, HealthKnowledgeDocument
from ...services.vector_store import QdrantVectorStore


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "")).strip().lower()


def content_hash(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def keep_priority(doc: HealthKnowledgeDocument) -> tuple:
    metadata = doc.metadata or {}
    has_chunks = doc.chunks.count() > 0
    is_structured_markdown = metadata.get("split_mode") == "markdown_entry"
    is_cmedqa = metadata.get("dataset") == "cMedQA"
    has_source_id = bool(metadata.get("que_id") or metadata.get("question_id"))
    return (
        0 if has_chunks else 1,
        0 if is_structured_markdown else 1,
        0 if is_cmedqa else 1,
        0 if has_source_id else 1,
        doc.id,
    )


class Command(BaseCommand):
    help = "按 question_id 和正文 hash 清理健康知识库重复数据"

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="真正执行清理；不加该参数只做 dry-run 统计",
        )
        parser.add_argument(
            "--hard-delete-docs",
            action="store_true",
            help="物理删除重复文档；默认只把文档标记为 deleted",
        )

    def handle(self, *args, **options):
        apply_changes = bool(options["apply"])
        hard_delete_docs = bool(options["hard_delete_docs"])
        docs = list(
            HealthKnowledgeDocument.objects.filter(status="active")
            .prefetch_related("chunks")
            .order_by("id")
        )

        by_question_id = defaultdict(list)
        by_hash = defaultdict(list)
        for doc in docs:
            metadata = doc.metadata or {}
            qid = metadata.get("que_id") or metadata.get("question_id")
            if qid:
                by_question_id[str(qid)].append(doc)
            normalized = normalize_text(doc.content)
            if normalized:
                by_hash[content_hash(doc.content)].append(doc)

        duplicate_doc_ids = set()
        groups = []

        def add_groups(source: str, grouped: dict):
            for key, items in grouped.items():
                if len(items) <= 1:
                    continue
                sorted_items = sorted(items, key=keep_priority)
                keep = sorted_items[0]
                duplicates = sorted_items[1:]
                groups.append((source, key, keep, duplicates))
                duplicate_doc_ids.update(doc.id for doc in duplicates)

        add_groups("question_id", by_question_id)
        add_groups("content_hash", by_hash)

        duplicate_docs = list(
            HealthKnowledgeDocument.objects.filter(id__in=duplicate_doc_ids).order_by("id")
        )
        duplicate_chunk_ids = list(
            HealthKnowledgeChunk.objects.filter(document_id__in=duplicate_doc_ids)
            .values_list("id", flat=True)
            .order_by("id")
        )

        self.stdout.write(
            {
                "active_docs": len(docs),
                "duplicate_groups": len(groups),
                "duplicate_docs": len(duplicate_docs),
                "duplicate_chunks": len(duplicate_chunk_ids),
                "mode": "apply" if apply_changes else "dry-run",
                "hard_delete_docs": hard_delete_docs,
            }.__str__()
        )

        for source, key, keep, duplicates in groups[:10]:
            dup_ids = [doc.id for doc in duplicates]
            self.stdout.write(
                f"[样例] {source}={str(key)[:20]} keep={keep.id} delete={dup_ids}"
            )

        if not apply_changes:
            self.stdout.write(self.style.WARNING("dry-run 完成；加 --apply 才会执行清理"))
            return

        with transaction.atomic():
            if duplicate_chunk_ids:
                HealthKnowledgeChunk.objects.filter(id__in=duplicate_chunk_ids).delete()
            if hard_delete_docs:
                HealthKnowledgeDocument.objects.filter(id__in=duplicate_doc_ids).delete()
            else:
                HealthKnowledgeDocument.objects.filter(id__in=duplicate_doc_ids).update(
                    status="deleted",
                    updated_at=timezone.now(),
                )

        if duplicate_chunk_ids:
            QdrantVectorStore().delete_chunks(duplicate_chunk_ids)

        self.stdout.write(
            self.style.SUCCESS(
                f"去重完成：文档={len(duplicate_docs)}，chunk/Qdrant points={len(duplicate_chunk_ids)}"
            )
        )
