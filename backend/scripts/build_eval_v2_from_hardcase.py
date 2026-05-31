import argparse
import json
import random
import re
from pathlib import Path


INTENT_PATTERNS = {
    "hypertension": r"高血压|血压高|降压|收缩压|舒张压",
    "sleep": r"失眠|入睡困难|早醒|多梦|睡不好|睡眠不好",
    "heart_rate": r"心率|心跳快|心悸|心慌|心动过速|心律",
    "headache": r"头痛|偏头痛|头晕|眩晕",
    "stomach": r"胃痛|胃胀|反酸|烧心|腹痛|消化不良",
    "leg_pain": r"腿疼|膝盖痛|关节痛|腰腿痛|坐骨神经痛|颈椎|腰椎",
}

DENY_PATTERN = re.compile(
    r"妇科|产科|月经|怀孕|妊娠|阴道|子宫|前列腺|泌尿|尿频|尿急|阳痿|早泄|人流|生殖"
)


def detect_intent(text: str) -> str | None:
    for intent, pat in INTENT_PATTERNS.items():
        if re.search(pat, text):
            return intent
    return None


def main():
    parser = argparse.ArgumentParser(description="从 hardcase_v1 清洗重建覆盖型评测集 v2")
    parser.add_argument(
        "--input",
        default="health_rag_assistant/datasets/eval/health_eval_questions_hardcase_v1.jsonl",
    )
    parser.add_argument(
        "--output",
        default="health_rag_assistant/datasets/eval/health_eval_questions_hardcase_v2_focus50.jsonl",
    )
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--max-per-intent", type=int, default=10)
    args = parser.parse_args()

    random.seed(args.seed)
    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    with input_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))

    buckets = {k: [] for k in INTENT_PATTERNS.keys()}
    seen = set()
    for r in rows:
        q = (r.get("question") or "").strip()
        if not q or q in seen:
            continue
        if DENY_PATTERN.search(q):
            continue
        intent = detect_intent(q)
        if not intent:
            continue
        seen.add(q)
        r["expected_topic"] = intent
        r["expected_keywords"] = [intent]
        r["expected_source_contains"] = [intent]
        r["case_type"] = "focused_hardcase"
        buckets[intent].append(r)

    # 先按每类上限抽，保证覆盖均衡
    selected = []
    for intent, items in buckets.items():
        random.shuffle(items)
        selected.extend(items[: args.max_per_intent])

    # 不够则从全体候选补齐
    if len(selected) < args.limit:
        pool = []
        picked_q = {x.get("question", "") for x in selected}
        for items in buckets.values():
            for x in items:
                q = x.get("question", "")
                if q and q not in picked_q:
                    pool.append(x)
        random.shuffle(pool)
        selected.extend(pool[: args.limit - len(selected)])

    random.shuffle(selected)
    selected = selected[: args.limit]

    # 重排 id
    for i, r in enumerate(selected, 1):
        r["id"] = f"hard_v2_{i:04d}"

    with output_path.open("w", encoding="utf-8", newline="\n") as f:
        for r in selected:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"[OK] output={output_path} total={len(selected)}")
    for intent, items in buckets.items():
        print(f"  - {intent}: {len(items)} candidates")


if __name__ == "__main__":
    main()
