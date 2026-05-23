"""
从 cMedQA 生成评测集（JSONL）

用途：
1. 从 questions.csv / answers.csv 抽样生成固定评测题集。
2. 输出到 datasets/eval 目录，用于回归评测，不参与知识库导入。
"""
import csv
import json
import random
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "从 cMedQA 抽样生成评测集 JSONL"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100, help="抽样条数，默认100")
        parser.add_argument(
            "--seed",
            type=int,
            default=2026,
            help="随机种子，默认2026，保证可复现",
        )
        parser.add_argument(
            "--output",
            type=str,
            default="health_eval_questions_cmedqa_v1.jsonl",
            help="输出文件名（默认写入 datasets/eval 目录）",
        )

    def handle(self, *args, **options):
        limit = max(int(options["limit"]), 1)
        seed = int(options["seed"])
        output_name = str(options["output"]).strip() or "health_eval_questions_cmedqa_v1.jsonl"

        base_dir = Path(settings.BASE_DIR)
        dataset_dir = base_dir / "health_rag_assistant" / "datasets" / "cMedQA"
        questions_path = dataset_dir / "questions.csv"
        answers_path = dataset_dir / "answers.csv"
        eval_dir = base_dir / "health_rag_assistant" / "datasets" / "eval"
        eval_dir.mkdir(parents=True, exist_ok=True)
        output_path = eval_dir / output_name

        if not questions_path.exists():
            raise FileNotFoundError(f"未找到 questions.csv: {questions_path}")
        if not answers_path.exists():
            raise FileNotFoundError(f"未找到 answers.csv: {answers_path}")

        answer_map = {}
        with answers_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                que_id = str(row.get("que_id", "")).strip()
                content = str(row.get("content", "")).strip()
                if not que_id or not content:
                    continue
                # 仅保留首条回答，减少重复噪声
                if que_id not in answer_map:
                    answer_map[que_id] = content

        candidates = []
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
                    continue
                candidates.append(
                    {
                        "que_id": que_id,
                        "question": question,
                        "big_cate": big_cate,
                        "small_cate": small_cate,
                        "answer": answer,
                    }
                )

        if not candidates:
            raise ValueError("未找到可用的问答样本，请检查 cMedQA 数据")

        if limit >= len(candidates):
            sampled = candidates
        else:
            random.seed(seed)
            sampled = random.sample(candidates, limit)

        with output_path.open("w", encoding="utf-8", newline="\n") as f:
            for idx, item in enumerate(sampled, start=1):
                record = {
                    "id": f"cmedqa_{idx:04d}",
                    "question": item["question"],
                    "expected_keywords": [kw for kw in [item["big_cate"], item["small_cate"]] if kw],
                    "expected_topic": item["small_cate"] or item["big_cate"] or "general",
                    "source": "cMedQA",
                    "que_id": item["que_id"],
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

        self.stdout.write(
            self.style.SUCCESS(
                f"评测集生成成功: {output_path}，样本数={len(sampled)}，seed={seed}"
            )
        )
