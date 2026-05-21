from django.core.management.base import BaseCommand

from health_rag_assistant.services.seed_service import (
    normalize_default_health_kb_source_paths,
    seed_default_health_kb_if_empty,
)


class Command(BaseCommand):
    help = "初始化默认健康 RAG 知识库语料"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="即使已有文档也重新导入一份默认语料",
        )
        parser.add_argument(
            "--normalize-paths",
            action="store_true",
            help="把默认语料来源路径同步为项目根目录相对路径",
        )

    def handle(self, *args, **options):
        result = seed_default_health_kb_if_empty(force=bool(options.get("force")))
        if options.get("normalize_paths"):
            result["path_normalize"] = normalize_default_health_kb_source_paths()
        self.stdout.write(self.style.SUCCESS(str(result)))
