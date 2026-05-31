import argparse
import csv
import json
import random
from collections import defaultdict
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="从筛选后的 cMedQA CSV 构建 50 条 focus 评测集")
    parser.add_argument(
        "--input",
        default="health_rag_assistant/datasets/cMedQA/cmedqa_highfreq_filtered.csv",
    )
    parser.add_argument(
        "--output",
        default="health_rag_assistant/datasets/eval/health_eval_questions_hardcase_v2_focus50.jsonl",
    )
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()

    random.seed(args.seed)
    in_path = Path(args.input)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    buckets = defaultdict(list)
    with in_path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            q = (row.get("question") or "").strip()
            intent = (row.get("intent") or "general").strip()
            if not q:
                continue
            buckets[intent].append(row)

    intents = sorted(buckets.keys())
    for k in intents:
        random.shuffle(buckets[k])

    # 均匀抽样
    selected = []
    i = 0
    while len(selected) < args.limit:
        progressed = False
        for intent in intents:
            if i < len(buckets[intent]):
                selected.append(buckets[intent][i])
                progressed = True
                if len(selected) >= args.limit:
                    break
        if not progressed:
            break
        i += 1

    records = []
    for idx, row in enumerate(selected, 1):
        intent = (row.get("intent") or "general").strip()
        q = (row.get("question") or "").strip()
        sc = (row.get("small_cate") or "").strip()
        bc = (row.get("big_cate") or "").strip()
        records.append(
            {
                "id": f"focus_{idx:04d}",
                "question": q,
                "expected_keywords": [intent, sc] if sc else [intent],
                "expected_topic": intent,
                "expected_source_contains": [sc or bc or intent],
                "source": "cMedQA_filtered",
                "que_id": (row.get("que_id") or "").strip(),
                "difficulty": "hard",
                "case_type": "focus_highfreq",
            }
        )

    with out_path.open("w", encoding="utf-8", newline="\n") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"[OK] output={out_path} total={len(records)}")
    print("intents:", {k: sum(1 for x in selected if (x.get('intent') or '') == k) for k in intents})


if __name__ == "__main__":
    main()
