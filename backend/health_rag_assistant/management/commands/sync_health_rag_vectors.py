"""
同步现有健康知识库分块到 Qdrant

用于文档和 chunk 已经在 SQLite 中生成，但向量库同步失败或需要单独重建
Qdrant collection 的场景。命令会按 EMBEDDING_BATCH_SIZE 分批生成向量并 upsert。
"""
from django.core.management.base import BaseCommand

from ...models import HealthKnowledgeChunk
from ...services.kb_service import sync_vector_index


class Command(BaseCommand):
    help = "将现有 active chunk 同步到 Qdrant 向量库"

    def add_arguments(self, parser):
        parser.add_argument(
            "--progress-step",
            type=int,
            default=200,
            help="每同步多少个 chunk 打印一次进度，默认 200",
        )

    def handle(self, *args, **options):
        progress_step = max(int(options["progress_step"]), 1)
        total_chunks = HealthKnowledgeChunk.objects.filter(
            document__status="active"
        ).count()
        if total_chunks <= 0:
            self.stdout.write(self.style.WARNING("没有可同步的 active chunk"))
            return

        self.stdout.write(f"开始同步 Qdrant 向量库：chunk 数={total_chunks}")

        last_printed = 0

        def _progress(inserted: int, total: int):
            nonlocal last_printed
            if inserted - last_printed >= progress_step or inserted == total:
                percent = inserted * 100 / max(total, 1)
                last_printed = inserted
                self.stdout.write(
                    f"[Qdrant进度] points={inserted}/{total} ({percent:.1f}%)"
                )

        ok, message = sync_vector_index(user_id=0, progress_callback=_progress)
        if ok:
            self.stdout.write(self.style.SUCCESS(message))
        else:
            self.stdout.write(self.style.ERROR(message))
