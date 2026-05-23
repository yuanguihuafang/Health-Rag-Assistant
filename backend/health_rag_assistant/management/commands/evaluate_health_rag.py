"""
RAG 评估命令

用途：
1. 读取 datasets/eval 下的 JSONL 评测集。
2. 执行检索评估并输出 Recall@K、MRR、引用命中率、平均耗时。
3. 保存评估结果到 datasets/eval/results 目录。
"""
import json
import time
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from ...services.rag_service import LOW_CONFIDENCE_SCORE, retrieve_hybrid


class Command(BaseCommand):
    help = "评估健康 RAG 检索效果（Recall/MRR/Citation/Latency）"

    def add_arguments(self, parser):
        parser.add_argument(
            "--input",
            type=str,
            default="health_eval_questions_cmedqa_v1.jsonl",
            help="评测文件名（位于 datasets/eval）",
        )
        parser.add_argument("--top-k", type=int, default=5, help="命中评估 topK")
        parser.add_argument("--limit", type=int, default=0, help="评测条数上限，0 为全量")

    def handle(self, *args, **options):
        top_k = max(int(options.get("top_k") or 5), 1)
        limit = max(int(options.get("limit") or 0), 0)
        input_name = str(options.get("input") or "").strip()

        base_dir = Path(settings.BASE_DIR) / "health_rag_assistant" / "datasets" / "eval"
        input_path = base_dir / input_name
        if not input_path.exists():
            raise FileNotFoundError(f"未找到评测文件: {input_path}")

        rows = []
        with input_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rows.append(json.loads(line))
        if limit:
            rows = rows[:limit]
        if not rows:
            raise ValueError("评测文件为空")

        self.stdout.write(f"开始评估：样本数={len(rows)} top_k={top_k}")

        recall_hit = 0
        mrr_total = 0.0
        citation_hit = 0
        low_confidence_count = 0
        latency_total = 0
        details = []

        for idx, item in enumerate(rows, start=1):
            question = str(item.get("question") or "").strip()
            expected_keywords = [str(x).strip() for x in (item.get("expected_keywords") or []) if str(x).strip()]
            expected_source_contains = [
                str(x).strip() for x in (item.get("expected_source_contains") or []) if str(x).strip()
            ]
            if not question:
                continue

            started = time.perf_counter()
            retrieval = retrieve_hybrid(
                question=question,
                conversation_history=None,
                vector_k=max(top_k, int(getattr(settings, "RAG_VECTOR_TOP_K", 30))),
                sparse_k=max(top_k, int(getattr(settings, "RAG_VECTOR_TOP_K", 30))),
                fused_k=max(top_k, 20),
            )
            latency_ms = int((time.perf_counter() - started) * 1000)
            latency_total += latency_ms

            final_hits = retrieval.get("final_hits") or []
            contexts = retrieval.get("contexts") or []

            rank = 0
            citation_ok = False
            for hit_idx, hit in enumerate(final_hits[:top_k], start=1):
                chunk_id = int(hit.get("chunk_id") or 0)
                target_text = ""
                for ctx in contexts:
                    if int(ctx.get("chunk_index", -1)) == int(hit.get("chunk_index", -2)) and ctx.get("document_title") == hit.get("document_title"):
                        target_text = str(ctx.get("chunk_text") or "")
                        break
                doc_title = str(hit.get("document_title") or "")
                merged_text = f"{doc_title} {target_text}"
                if expected_keywords and any(keyword in merged_text for keyword in expected_keywords):
                    rank = hit_idx
                    break

            if rank > 0:
                recall_hit += 1
                mrr_total += 1.0 / rank

            for src in contexts[:top_k]:
                source_text = f"{src.get('document_title', '')} {src.get('chunk_text', '')}"
                if expected_source_contains and any(token in source_text for token in expected_source_contains):
                    citation_ok = True
                    break
                if (not expected_source_contains) and expected_keywords and any(token in source_text for token in expected_keywords):
                    citation_ok = True
                    break
            if citation_ok:
                citation_hit += 1

            top_score = 0.0
            if contexts:
                top_score = float(contexts[0].get("score") or 0.0)
            if top_score < LOW_CONFIDENCE_SCORE:
                low_confidence_count += 1

            details.append(
                {
                    "id": item.get("id", f"row_{idx}"),
                    "question": question,
                    "latency_ms": latency_ms,
                    "hit_rank": rank,
                    "top_score": top_score,
                    "citation_hit": citation_ok,
                    "top_context_titles": [ctx.get("document_title", "") for ctx in contexts[:top_k]],
                }
            )
            if idx % 20 == 0 or idx == len(rows):
                self.stdout.write(f"[进度] {idx}/{len(rows)}")

        total = len(rows)
        metrics = {
            "sample_count": total,
            "top_k": top_k,
            "recall_at_k": round(recall_hit / total, 4),
            "mrr": round(mrr_total / total, 4),
            "citation_hit_rate": round(citation_hit / total, 4),
            "avg_latency_ms": round(latency_total / total, 2),
            "low_confidence_ratio": round(low_confidence_count / total, 4),
        }

        result_dir = base_dir / "results"
        result_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        result_path = result_dir / f"eval_{ts}.json"
        payload = {
            "input_file": str(input_path),
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "metrics": metrics,
            "details": details,
        }
        result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        self.stdout.write(self.style.SUCCESS(f"Recall@{top_k}: {metrics['recall_at_k']}"))
        self.stdout.write(self.style.SUCCESS(f"MRR: {metrics['mrr']}"))
        self.stdout.write(self.style.SUCCESS(f"Citation Hit Rate: {metrics['citation_hit_rate']}"))
        self.stdout.write(self.style.SUCCESS(f"Avg Latency(ms): {metrics['avg_latency_ms']}"))
        self.stdout.write(self.style.SUCCESS(f"Low Confidence Ratio: {metrics['low_confidence_ratio']}"))
        self.stdout.write(self.style.SUCCESS(f"结果文件: {result_path}"))
