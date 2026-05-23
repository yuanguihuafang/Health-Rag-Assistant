"""
重建健康知识库向量索引命令

用途：
1. 将当前 active 文档重新切分并写入向量索引。
2. 与后台“重建索引”使用同一套服务逻辑，避免结果不一致。
"""
from django.core.management.base import BaseCommand

from ...models import HealthKnowledgeDocument
from ...services.kb_service import rebuild_index_for_documents


class Command(BaseCommand):
    help = "重建健康知识库向量索引（Qdrant）"

    def add_arguments(self, parser):
        parser.add_argument("--chunk-size", type=int, default=500)
        parser.add_argument("--chunk-overlap", type=int, default=80)
        parser.add_argument(
            "--progress-step",
            type=int,
            default=200,
            help="每处理多少篇文档打印一次进度，默认 200",
        )

    def handle(self, *args, **options):
        chunk_size = int(options["chunk_size"])
        chunk_overlap = int(options["chunk_overlap"])
        progress_step = max(int(options["progress_step"]), 1)
        docs = list(HealthKnowledgeDocument.objects.filter(status="active").order_by("id"))
        if not docs:
            self.stdout.write(self.style.WARNING("没有可重建的 active 文档"))
            return

        self.stdout.write(
            f"开始重建向量索引：文档数={len(docs)}，chunk_size={chunk_size}，chunk_overlap={chunk_overlap}"
        )

        def _progress(current_doc_index: int, total_docs: int, total_chunks: int):
            if current_doc_index % progress_step == 0 or current_doc_index == total_docs:
                percent = current_doc_index * 100 / max(total_docs, 1)
                self.stdout.write(
                    f"[进度] 文档={current_doc_index}/{total_docs} ({percent:.1f}%) 累计分块={total_chunks}"
                )

        chunk_count = rebuild_index_for_documents(
            documents=docs,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            progress_callback=_progress,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"重建完成：文档数={len(docs)}，分块数={chunk_count}，chunk_size={chunk_size}，chunk_overlap={chunk_overlap}"
            )
        )
