"""
导入 curated Markdown 结构化语料

按 `## 条目 xxx` 解析项目内置 curated Markdown 文件，跳过文件标题和说明。
每个条目导入为一篇知识文档，并生成一个独立 chunk，metadata 保留主题、关键词、
来源文件和条目编号，便于 RAG 检索和引用溯源。
"""
import re
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand

from ...models import HealthKnowledgeChunk, HealthKnowledgeDocument
from ...services.embedding_service import EmbeddingService
from ...services.kb_service import sync_vector_index


ENTRY_RE = re.compile(
    r"^##\s*条目\s*(?P<entry_no>\d+)\s*$"
    r"(?P<body>.*?)(?=^##\s*条目\s*\d+\s*$|\Z)",
    re.MULTILINE | re.DOTALL,
)


def _resolve_owner_user_id() -> int:
    HertzUser = apps.get_model("hertz_studio_django_auth", "HertzUser")
    for username in ("hertz", "demo"):
        user = HertzUser.objects.filter(username=username, status=1).first()
        if user:
            return int(user.user_id)
    user = HertzUser.objects.filter(status=1).order_by("user_id").first()
    if not user:
        raise RuntimeError("未找到可用于导入数据的有效用户")
    return int(user.user_id)


def _field(body: str, name: str) -> str:
    pattern = re.compile(rf"^{re.escape(name)}[:：]\s*(.+?)\s*$", re.MULTILINE)
    match = pattern.search(body)
    return match.group(1).strip() if match else ""


def _parse_entries(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    entries = []
    for match in ENTRY_RE.finditer(text):
        entry_no = match.group("entry_no").strip().zfill(3)
        body = match.group("body").strip()
        topic = _field(body, "主题")
        question = _field(body, "问题")
        answer = _field(body, "回答")
        keywords_text = _field(body, "关键词")
        keywords = [
            item.strip()
            for item in re.split(r"[、,，]", keywords_text)
            if item.strip()
        ]
        if not question or not answer:
            continue
        content = "\n".join(
            [
                f"主题：{topic}",
                "",
                f"问题：{question}",
                "",
                f"回答：{answer}",
                "",
                f"关键词：{keywords_text}",
            ]
        ).strip()
        entries.append(
            {
                "entry_no": entry_no,
                "topic": topic,
                "question": question,
                "answer": answer,
                "keywords": keywords,
                "keywords_text": keywords_text,
                "content": content,
            }
        )
    return entries


class Command(BaseCommand):
    help = "导入 curated Markdown 结构化健康语料"

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            action="append",
            default=[],
            help="指定导入文件名，可重复传；默认导入 curated 目录全部 md",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="已存在 source_path 时仍重新导入",
        )
        parser.add_argument(
            "--sync-qdrant",
            action="store_true",
            help="导入完成后同步 active chunk 到 Qdrant",
        )
        parser.add_argument(
            "--progress-step",
            type=int,
            default=100,
            help="同步 Qdrant 时每多少个 point 打印一次进度",
        )

    def handle(self, *args, **options):
        curated_dir = (
            Path(settings.BASE_DIR)
            / "health_rag_assistant"
            / "datasets"
            / "curated"
        )
        if not curated_dir.exists():
            raise FileNotFoundError(f"未找到 curated 目录: {curated_dir}")

        names = [str(item).strip() for item in options.get("file") or [] if str(item).strip()]
        if names:
            paths = [curated_dir / name for name in names]
        else:
            paths = sorted(curated_dir.glob("*.md"))

        for path in paths:
            if not path.exists():
                raise FileNotFoundError(f"未找到文件: {path}")

        owner_user_id = _resolve_owner_user_id()
        force = bool(options.get("force"))
        imported = 0
        skipped = 0
        created_chunks = 0
        embedder = EmbeddingService()

        existing_paths = set()
        if not force:
            existing_paths = set(
                HealthKnowledgeDocument.objects.filter(
                    source_type="file",
                    source_path__startswith="curated/",
                ).values_list("source_path", flat=True)
            )

        for path in paths:
            entries = _parse_entries(path)
            self.stdout.write(f"解析 {path.name}: 条目数={len(entries)}")
            for entry in entries:
                source_path = f"curated/{path.name}#entry={entry['entry_no']}"
                if not force and source_path in existing_paths:
                    skipped += 1
                    continue
                title = f"{path.stem} 条目 {entry['entry_no']}：{entry['question'][:40]}"
                metadata = {
                    "dataset": "curated_health",
                    "source_file": path.name,
                    "entry_no": entry["entry_no"],
                    "topic": entry["topic"],
                    "keywords": entry["keywords"],
                    "seed": "curated_markdown_import",
                }
                doc = HealthKnowledgeDocument.objects.create(
                    user_id=owner_user_id,
                    title=title,
                    source_type="file",
                    source_path=source_path,
                    content=entry["content"],
                    status="active",
                    metadata=metadata,
                )
                vector = embedder.embed_query(entry["content"])
                HealthKnowledgeChunk.objects.create(
                    document=doc,
                    chunk_index=0,
                    chunk_text=entry["content"],
                    token_count=len(entry["content"].split()),
                    vector_id=0,
                    embedding=vector,
                )
                imported += 1
                created_chunks += 1

        result = {
            "imported_documents": imported,
            "created_chunks": created_chunks,
            "skipped_existing": skipped,
            "owner_user_id": owner_user_id,
            "sync_qdrant": bool(options.get("sync_qdrant")),
        }

        if options.get("sync_qdrant"):
            progress_step = max(int(options.get("progress_step") or 100), 1)
            last_printed = 0

            def _progress(inserted: int, total: int):
                nonlocal last_printed
                if inserted - last_printed >= progress_step or inserted == total:
                    percent = inserted * 100 / max(total, 1)
                    last_printed = inserted
                    self.stdout.write(
                        f"[Qdrant进度] points={inserted}/{total} ({percent:.1f}%)"
                    )

            ok, message = sync_vector_index(user_id=owner_user_id, progress_callback=_progress)
            result["qdrant_sync_ok"] = ok
            result["qdrant_message"] = message

        self.stdout.write(self.style.SUCCESS(str(result)))
