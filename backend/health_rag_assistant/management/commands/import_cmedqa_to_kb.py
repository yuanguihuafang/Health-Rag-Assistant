"""
导入 cMedQA 全量问答到知识库并写入向量库

用途：
1. 读取 datasets/cMedQA/questions.csv 与 answers.csv。
2. 将问答对写入 HealthKnowledgeDocument。
3. 可选执行向量重建，将导入数据写入 Qdrant。
"""
import csv
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand

from ...models import HealthKnowledgeDocument
from ...services.kb_service import rebuild_index_for_documents


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


class Command(BaseCommand):
    help = "导入 cMedQA CSV 到知识库，并可选重建向量索引"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=0, help="导入条数上限，0 表示全量")
        parser.add_argument(
            "--reindex",
            action="store_true",
            help="导入完成后立即重建向量索引（写入 Qdrant）",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="强制重新导入（即使 source_path 已存在）",
        )
        parser.add_argument("--chunk-size", type=int, default=600)
        parser.add_argument("--chunk-overlap", type=int, default=80)

    def handle(self, *args, **options):
        base_dir = Path(settings.BASE_DIR)
        cmedqa_dir = base_dir / "health_rag_assistant" / "datasets" / "cMedQA"
        questions_path = cmedqa_dir / "questions.csv"
        answers_path = cmedqa_dir / "answers.csv"

        if not questions_path.exists():
            raise FileNotFoundError(f"未找到文件: {questions_path}")
        if not answers_path.exists():
            raise FileNotFoundError(f"未找到文件: {answers_path}")

        limit = max(int(options.get("limit") or 0), 0)
        force = bool(options.get("force"))
        reindex = bool(options.get("reindex"))
        chunk_size = int(options.get("chunk_size") or 600)
        chunk_overlap = int(options.get("chunk_overlap") or 80)

        owner_user_id = _resolve_owner_user_id()

        answer_map = {}
        with answers_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                que_id = str(row.get("que_id", "")).strip()
                answer = str(row.get("content", "")).strip()
                if not que_id or not answer:
                    continue
                if que_id not in answer_map:
                    answer_map[que_id] = answer

        existing_paths = set()
        if not force:
            existing_paths = set(
                HealthKnowledgeDocument.objects.filter(
                    source_type="file",
                    source_path__startswith="cMedQA/questions.csv#que_id=",
                ).values_list("source_path", flat=True)
            )

        created_doc_ids = []
        imported = 0
        skipped = 0

        total_candidates = 0
        with questions_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                que_id = str(row.get("que_id", "")).strip()
                question = str(row.get("content", "")).strip()
                if not que_id or not question:
                    continue
                if not answer_map.get(que_id, ""):
                    continue
                total_candidates += 1

        total_for_progress = total_candidates
        progress_step = 500
        scanned = 0

        self.stdout.write(
            f"开始导入 cMedQA：候选样本={total_candidates}，计划导入={total_for_progress}，reindex={reindex}"
        )

        with questions_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                que_id = str(row.get("que_id", "")).strip()
                question = str(row.get("content", "")).strip()
                big_cate = str(row.get("big_cate", "")).strip()
                small_cate = str(row.get("small_cate", "")).strip()
                if not que_id or not question:
                    continue

                answer = answer_map.get(que_id, "")
                if not answer:
                    skipped += 1
                    continue

                scanned += 1
                source_path = f"cMedQA/questions.csv#que_id={que_id}"
                if not force and source_path in existing_paths:
                    skipped += 1
                    if scanned % progress_step == 0:
                        percent = scanned * 100 / max(total_for_progress, 1)
                        self.stdout.write(
                            f"[进度] 扫描={scanned} 导入={imported} 跳过={skipped} 进度={percent:.1f}%"
                        )
                    continue

                title = f"cMedQA 问答 {que_id}"
                content = f"问题：{question}\n\n回答：{answer}"
                metadata = {
                    "dataset": "cMedQA",
                    "que_id": que_id,
                    "big_cate": big_cate,
                    "small_cate": small_cate,
                    "seed": "cmedqa_full_import",
                }
                doc = HealthKnowledgeDocument.objects.create(
                    user_id=owner_user_id,
                    title=title,
                    source_type="file",
                    source_path=source_path,
                    content=content,
                    status="active",
                    metadata=metadata,
                )
                created_doc_ids.append(int(doc.id))
                imported += 1

                if scanned % progress_step == 0:
                    percent = scanned * 100 / max(total_for_progress, 1)
                    self.stdout.write(
                        f"[进度] 扫描={scanned} 导入={imported} 跳过={skipped} 进度={percent:.1f}%"
                    )

                if limit and imported >= limit:
                    break

        result = {
            "imported_documents": imported,
            "skipped_records": skipped,
            "owner_user_id": owner_user_id,
            "reindex": reindex,
        }

        if reindex and created_doc_ids:
            # SQLite 对 IN 参数数量有限制，按批次查询文档再统一重建。
            doc_batch_size = 500
            docs = []
            total_ids = len(created_doc_ids)
            for i in range(0, total_ids, doc_batch_size):
                batch_ids = created_doc_ids[i : i + doc_batch_size]
                docs.extend(
                    list(
                        HealthKnowledgeDocument.objects.filter(id__in=batch_ids).order_by("id")
                    )
                )
                if (i // doc_batch_size + 1) % 20 == 0:
                    scanned = min(i + doc_batch_size, total_ids)
                    self.stdout.write(f"[向量化准备] 已装载文档 {scanned}/{total_ids}")

            self.stdout.write(
                f"开始向量化：文档数={len(docs)} chunk_size={chunk_size} chunk_overlap={chunk_overlap}"
            )
            chunk_count = rebuild_index_for_documents(
                documents=docs,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
            result["vectorized_chunks"] = int(chunk_count)
            result["chunk_size"] = chunk_size
            result["chunk_overlap"] = chunk_overlap

        self.stdout.write(self.style.SUCCESS(str(result)))
