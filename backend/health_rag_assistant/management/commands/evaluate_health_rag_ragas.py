"""
RAGAS 评估命令

用途：
1. 读取 datasets/eval 下的 JSONL 评测集。
2. 使用 ask_with_rag 生成回答，结合检索上下文构造 RAGAS 数据集。
3. 输出 faithfulness / answer_relevancy / context_precision / context_recall。
"""
import json
from datetime import datetime
from pathlib import Path
from typing import List

from django.conf import settings
from django.core.management.base import BaseCommand

from ...services.rag_service import ask_with_rag, retrieve_hybrid


class Command(BaseCommand):
    help = "使用 RAGAS 评估健康 RAG（faithfulness/relevancy/precision/recall）"

    def add_arguments(self, parser):
        parser.add_argument(
            "--input",
            type=str,
            default="health_eval_questions_cmedqa_v1.jsonl",
            help="评测文件名（位于 datasets/eval）",
        )
        parser.add_argument("--top-k", type=int, default=5, help="检索 topK")
        parser.add_argument("--limit", type=int, default=20, help="评测条数上限")
        parser.add_argument(
            "--user-id",
            type=int,
            default=1,
            help="调用 ask_with_rag 时使用的用户 ID",
        )

    def handle(self, *args, **options):
        try:
            from datasets import Dataset
            from ragas import evaluate
            from ragas.metrics import (
                answer_relevancy,
                context_precision,
                context_recall,
                faithfulness,
            )
            from langchain_openai import ChatOpenAI, OpenAIEmbeddings
        except Exception as exc:
            raise RuntimeError(
                "未安装 RAGAS 依赖。请先执行：\n"
                "pip install ragas datasets langchain-openai\n"
                f"原始错误: {exc}"
            ) from exc

        top_k = max(int(options.get("top_k") or 5), 1)
        limit = max(int(options.get("limit") or 20), 1)
        user_id = int(options.get("user_id") or 1)
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
        rows = rows[:limit]
        if not rows:
            raise ValueError("评测文件为空")

        self.stdout.write(f"开始 RAGAS 评估：样本数={len(rows)} top_k={top_k}")

        questions: List[str] = []
        answers: List[str] = []
        contexts: List[List[str]] = []
        ground_truths: List[str] = []

        for idx, item in enumerate(rows, start=1):
            question = str(item.get("question") or "").strip()
            if not question:
                continue

            answer, _sources = ask_with_rag(
                user_id=user_id,
                question=question,
                k=top_k,
                llm_config=None,
                conversation_history=None,
            )
            retrieval = retrieve_hybrid(
                question=question,
                conversation_history=None,
                vector_k=max(top_k, int(getattr(settings, "RAG_VECTOR_TOP_K", 30))),
                sparse_k=max(top_k, int(getattr(settings, "RAG_VECTOR_TOP_K", 30))),
                fused_k=max(top_k, 20),
            )
            hit_contexts = retrieval.get("contexts") or []
            context_texts = [str(x.get("chunk_text") or "") for x in hit_contexts[:top_k] if str(x.get("chunk_text") or "").strip()]

            expected_keywords = [
                str(x).strip()
                for x in (item.get("expected_keywords") or [])
                if str(x).strip()
            ]
            expected_source_contains = [
                str(x).strip()
                for x in (item.get("expected_source_contains") or [])
                if str(x).strip()
            ]
            if expected_source_contains:
                gt = "；".join(expected_source_contains)
            elif expected_keywords:
                gt = "；".join(expected_keywords)
            else:
                gt = question

            questions.append(question)
            answers.append(str(answer or ""))
            contexts.append(context_texts if context_texts else [""])
            ground_truths.append(gt)

            if idx % 10 == 0 or idx == len(rows):
                self.stdout.write(f"[进度] {idx}/{len(rows)}")

        if not questions:
            raise ValueError("评测样本无有效 question")

        dataset = Dataset.from_dict(
            {
                "question": questions,
                "answer": answers,
                "contexts": contexts,
                "ground_truth": ground_truths,
            }
        )

        llm_api_key = str(getattr(settings, "LLM_API_KEY", "") or "").strip()
        llm_base_url = str(getattr(settings, "LLM_BASE_URL", "") or "").strip()
        llm_model = str(getattr(settings, "LLM_MODEL", "") or "").strip()
        embedding_api_key = str(getattr(settings, "EMBEDDING_API_KEY", "") or "").strip()
        embedding_base_url = str(getattr(settings, "EMBEDDING_BASE_URL", "") or "").strip()
        embedding_model = str(getattr(settings, "EMBEDDING_MODEL", "") or "").strip()

        if not llm_api_key:
            raise RuntimeError("RAGAS 评估缺少 LLM_API_KEY，请在 .env 中配置后重试")
        if not llm_model:
            raise RuntimeError("RAGAS 评估缺少 LLM_MODEL，请在 .env 中配置后重试")
        if not embedding_api_key:
            raise RuntimeError("RAGAS 评估缺少 EMBEDDING_API_KEY，请在 .env 中配置后重试")
        if not embedding_model:
            raise RuntimeError("RAGAS 评估缺少 EMBEDDING_MODEL，请在 .env 中配置后重试")

        evaluator_llm = ChatOpenAI(
            model=llm_model,
            api_key=llm_api_key,
            base_url=llm_base_url or None,
            timeout=int(getattr(settings, "LLM_TIMEOUT", 60)),
        )
        evaluator_embeddings = OpenAIEmbeddings(
            model=embedding_model,
            api_key=embedding_api_key,
            base_url=embedding_base_url or None,
            request_timeout=int(getattr(settings, "EMBEDDING_TIMEOUT", 30)),
        )

        result = evaluate(
            dataset=dataset,
            metrics=[
                faithfulness,
                answer_relevancy,
                context_precision,
                context_recall,
            ],
            llm=evaluator_llm,
            embeddings=evaluator_embeddings,
        )

        scores = result.to_pandas().mean(numeric_only=True).to_dict()
        metrics = {
            "sample_count": len(questions),
            "top_k": top_k,
            "faithfulness": round(float(scores.get("faithfulness", 0.0)), 4),
            "answer_relevancy": round(float(scores.get("answer_relevancy", 0.0)), 4),
            "context_precision": round(float(scores.get("context_precision", 0.0)), 4),
            "context_recall": round(float(scores.get("context_recall", 0.0)), 4),
        }

        result_dir = base_dir / "results"
        result_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        result_path = result_dir / f"eval_ragas_{ts}.json"
        result_path.write_text(
            json.dumps(
                {
                    "input_file": str(input_path),
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "metrics": metrics,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        self.stdout.write(self.style.SUCCESS(f"Faithfulness: {metrics['faithfulness']}"))
        self.stdout.write(self.style.SUCCESS(f"Answer Relevancy: {metrics['answer_relevancy']}"))
        self.stdout.write(self.style.SUCCESS(f"Context Precision: {metrics['context_precision']}"))
        self.stdout.write(self.style.SUCCESS(f"Context Recall: {metrics['context_recall']}"))
        self.stdout.write(self.style.SUCCESS(f"结果文件: {result_path}"))
