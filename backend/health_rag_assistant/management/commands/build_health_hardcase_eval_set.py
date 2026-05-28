"""
生成健康 RAG hardcase 评测集（JSONL）

默认从当前数据库 active 知识文档中抽样，生成术语型、口语型、长问题、多轮追问样本。
可选 --source csv 使用 cMedQA CSV 作为候选来源（兼容旧流程）。
"""
import csv
import json
import random
import re
from pathlib import Path
from typing import Dict, List

from django.conf import settings
from django.core.management.base import BaseCommand
from health_rag_assistant.models import HealthKnowledgeDocument


HARD_TERMS = (
    "甲亢",
    "甲减",
    "碘131",
    "心绞痛",
    "前列腺",
    "高血压",
    "糖尿病",
    "脑梗",
    "哮喘",
    "痛风",
    "抑郁",
    "失眠",
    "偏头痛",
    "胃食管反流",
)

TOPIC_KEYWORDS: Dict[str, List[str]] = {
    "sleep": ["失眠", "入睡困难", "睡眠", "早醒", "多梦"],
    "cardio": ["心悸", "心绞痛", "胸闷", "高血压", "心率"],
    "digestive": ["胃痛", "反酸", "腹胀", "消化", "便秘"],
    "pediatric": ["发热", "小孩", "宝宝", "儿科", "咳嗽"],
    "female": ["经期", "痛经", "白带", "妇科", "月经"],
}

FOLLOW_UPS = ["那老人呢？", "那女性呢？", "那小孩呢？", "如果症状反复怎么办？"]


def _clean(text: str) -> str:
    return " ".join(str(text or "").strip().split())


def _extract_question_like_text(content: str) -> str:
    text = _clean(content)
    if not text:
        return ""
    # 优先抽取“问题：xxx”
    m = re.search(r"(?:问题|问)[:：]\s*(.+?)(?:$|(?:答[:：]))", text)
    if m:
        return _clean(m.group(1))
    # 否则取首句作为 query 候选
    parts = re.split(r"[。！？!?；;\n]", text)
    for p in parts:
        p = _clean(p)
        if len(p) >= 8:
            return p
    return text[:80]


def _guess_topic(text: str) -> str:
    for topic_name, kws in TOPIC_KEYWORDS.items():
        if any(k in text for k in kws):
            return topic_name
    return "general"


class Command(BaseCommand):
    help = "生成术语/口语/多轮 hardcase 评测集（JSONL）"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=50, help="输出样本总数，默认 50")
        parser.add_argument("--seed", type=int, default=2026, help="随机种子，默认 2026")
        parser.add_argument(
            "--output",
            type=str,
            default="health_eval_questions_hardcase_v1.jsonl",
            help="输出文件名（写入 datasets/eval）",
        )
        parser.add_argument(
            "--multi-turn-ratio",
            type=float,
            default=0.2,
            help="多轮追问样本占比，默认 0.2（20%%）",
        )
        parser.add_argument(
            "--source",
            type=str,
            choices=["db", "csv"],
            default="db",
            help="候选样本来源：db(默认) 或 csv",
        )

    def handle(self, *args, **options):
        limit = max(int(options["limit"]), 10)
        seed = int(options["seed"])
        output_name = str(options["output"]).strip() or "health_eval_questions_hardcase_v1.jsonl"
        multi_turn_ratio = float(options.get("multi_turn_ratio") or 0.2)
        source = options.get("source", "db")
        multi_turn_ratio = min(max(multi_turn_ratio, 0.0), 0.6)

        random.seed(seed)

        base_dir = Path(settings.BASE_DIR)
        eval_dir = base_dir / "health_rag_assistant" / "datasets" / "eval"
        eval_dir.mkdir(parents=True, exist_ok=True)
        output_path = eval_dir / output_name

        candidates = []
        if source == "db":
            docs = HealthKnowledgeDocument.objects.filter(status="active").only("id", "title", "content", "metadata")
            for d in docs.iterator():
                title = _clean(d.title)
                content = _clean(d.content)
                if not content and not title:
                    continue
                question = _extract_question_like_text(content or title)
                if len(question) < 6:
                    continue
                meta = d.metadata or {}
                expected_keywords = []
                for k in ("topic", "category", "department"):
                    v = _clean(meta.get(k, ""))
                    if v:
                        expected_keywords.append(v)
                topic = _guess_topic(question + " " + title)
                candidates.append(
                    {
                        "que_id": f"doc_{d.id}",
                        "question": question,
                        "big_cate": expected_keywords[0] if expected_keywords else topic,
                        "small_cate": expected_keywords[1] if len(expected_keywords) > 1 else topic,
                        "answer": "",
                        "source": "knowledge_db",
                    }
                )
        else:
            dataset_dir = base_dir / "health_rag_assistant" / "datasets" / "cMedQA"
            questions_path = dataset_dir / "questions.csv"
            answers_path = dataset_dir / "answers.csv"
            if not questions_path.exists() or not answers_path.exists():
                raise FileNotFoundError("cMedQA questions.csv / answers.csv 不存在")

            answer_map: Dict[str, str] = {}
            with answers_path.open("r", encoding="utf-8", newline="") as f:
                for row in csv.DictReader(f):
                    qid = _clean(row.get("que_id", ""))
                    ans = _clean(row.get("content", ""))
                    if qid and ans and qid not in answer_map:
                        answer_map[qid] = ans

            with questions_path.open("r", encoding="utf-8", newline="") as f:
                for row in csv.DictReader(f):
                    qid = _clean(row.get("que_id", ""))
                    q = _clean(row.get("content", ""))
                    big = _clean(row.get("big_cate", ""))
                    small = _clean(row.get("small_cate", ""))
                    if not qid or not q:
                        continue
                    if qid not in answer_map:
                        continue
                    candidates.append(
                        {
                            "que_id": qid,
                            "question": q,
                            "big_cate": big,
                            "small_cate": small,
                            "answer": answer_map[qid],
                            "source": "cMedQA",
                        }
                    )

        if not candidates:
            raise ValueError(f"未找到可用候选样本，source={source}")

        # 三类 hardcase 候选：术语型、口语型（较短/含口语词）、长问题
        term_pool = [x for x in candidates if any(t in x["question"] for t in HARD_TERMS)]
        colloquial_pool = [
            x
            for x in candidates
            if any(k in x["question"] for k in ("怎么办", "咋办", "怎么回事", "是不是", "能不能", "要不要"))
        ]
        long_pool = [x for x in candidates if len(x["question"]) >= 40]

        def pick(pool: List[dict], n: int) -> List[dict]:
            if not pool or n <= 0:
                return []
            if n >= len(pool):
                return random.sample(pool, len(pool))
            return random.sample(pool, n)

        multi_turn_n = int(limit * multi_turn_ratio)
        base_n = limit - multi_turn_n

        term_n = int(base_n * 0.45)
        colloquial_n = int(base_n * 0.30)
        long_n = base_n - term_n - colloquial_n

        selected = pick(term_pool, term_n) + pick(colloquial_pool, colloquial_n) + pick(long_pool, long_n)
        if len(selected) < base_n:
            remain = [x for x in candidates if x not in selected]
            selected += pick(remain, base_n - len(selected))

        random.shuffle(selected)
        selected = selected[:base_n]

        records = []
        idx = 1
        for item in selected:
            keywords = [kw for kw in [item["big_cate"], item["small_cate"]] if kw]
            records.append(
                {
                    "id": f"hard_{idx:04d}",
                    "question": item["question"],
                    "expected_keywords": keywords,
                    "expected_topic": item["small_cate"] or item["big_cate"] or "general",
                    "expected_source_contains": keywords[:2],
                    "source": item.get("source", source),
                    "que_id": item["que_id"],
                    "difficulty": "hard",
                    "case_type": "term_or_colloquial_or_long",
                }
            )
            idx += 1

        # 生成多轮追问样本（构造为“主问题 + 短追问”）
        topic_seeds = []
        for topic_name, kws in TOPIC_KEYWORDS.items():
            pool = [x for x in candidates if any(k in x["question"] for k in kws)]
            if pool:
                topic_seeds.append((topic_name, random.choice(pool), kws))

        while len(records) < limit and topic_seeds:
            topic_name, seed_item, kws = random.choice(topic_seeds)
            follow = random.choice(FOLLOW_UPS)
            question = f"{seed_item['question']} {follow}"
            records.append(
                {
                    "id": f"hard_{idx:04d}",
                    "question": question,
                    "expected_keywords": kws[:3],
                    "expected_topic": topic_name,
                    "expected_source_contains": kws[:2],
                    "source": seed_item.get("source", source),
                    "que_id": seed_item["que_id"],
                    "difficulty": "hard",
                    "case_type": "multi_turn_follow_up",
                }
            )
            idx += 1

        with output_path.open("w", encoding="utf-8", newline="\n") as f:
            for r in records[:limit]:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

        self.stdout.write(
            self.style.SUCCESS(
                f"hardcase 评测集生成成功: {output_path}，样本数={min(len(records), limit)}，seed={seed}，source={source}"
            )
        )
