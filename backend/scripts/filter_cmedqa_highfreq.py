import argparse
import csv
import re
from pathlib import Path


ALLOW_SMALL_CATE = {
    "心血管内科",
    "高血压",
    "神经内科",
    "消化内科",
    "呼吸内科",
    "骨科",
    "颈腰椎病",
    "生活起居",
}

DENY_SMALL_CATE = {
    "妇科综合",
    "产科综合",
    "产后妇科",
    "人流",
    "生殖孕育",
    "男科",
}

ALLOW_PATTERNS = [
    r"高血压|血压高|降压|收缩压|舒张压",
    r"失眠|入睡困难|早醒|多梦|睡不好|睡眠不好",
    r"心率|心跳快|心悸|心慌|心动过速|心律",
    r"头痛|偏头痛|头晕|眩晕",
    r"胃痛|胃胀|反酸|烧心|腹痛|消化不良",
    r"腿疼|膝盖痛|关节痛|腰腿痛|坐骨神经痛",
]

DENY_PATTERNS = [
    r"妇科|产科|月经|怀孕|妊娠|阴道|子宫",
    r"前列腺|泌尿|尿频|尿急|阳痿|早泄",
]


def clean(s: str) -> str:
    return " ".join((s or "").strip().split())


def hit_any(text: str, patterns) -> bool:
    return any(re.search(p, text) for p in patterns)


def main():
    parser = argparse.ArgumentParser(description="筛选 cMedQA 高频主诉候选集（排除妇产/泌尿）")
    parser.add_argument("--questions", default="health_rag_assistant/datasets/cMedQA/questions.csv")
    parser.add_argument("--answers", default="health_rag_assistant/datasets/cMedQA/answers.csv")
    parser.add_argument("--output", default="health_rag_assistant/datasets/cMedQA/cmedqa_highfreq_filtered.csv")
    parser.add_argument("--max-per-intent", type=int, default=300, help="每个主诉类别最多保留条数")
    args = parser.parse_args()

    qpath = Path(args.questions)
    apath = Path(args.answers)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)

    answer_map = {}
    with apath.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            qid = clean(row.get("que_id", ""))
            ans = clean(row.get("content", ""))
            if qid and ans and qid not in answer_map:
                answer_map[qid] = ans

    buckets = {
        "hypertension": [],
        "sleep": [],
        "heart_rate": [],
        "headache": [],
        "stomach": [],
        "leg_pain": [],
    }
    intent_rules = {
        "hypertension": r"高血压|血压高|降压|收缩压|舒张压",
        "sleep": r"失眠|入睡困难|早醒|多梦|睡不好|睡眠不好",
        "heart_rate": r"心率|心跳快|心悸|心慌|心动过速|心律",
        "headache": r"头痛|偏头痛|头晕|眩晕",
        "stomach": r"胃痛|胃胀|反酸|烧心|腹痛|消化不良",
        "leg_pain": r"腿疼|膝盖痛|关节痛|腰腿痛|坐骨神经痛",
    }

    seen_q = set()
    with qpath.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            qid = clean(row.get("que_id", ""))
            q = clean(row.get("content", ""))
            big = clean(row.get("big_cate", ""))
            small = clean(row.get("small_cate", ""))
            if not qid or not q:
                continue
            if qid not in answer_map:
                continue
            if len(q) < 8 or len(q) > 120:
                continue
            text = f"{q} {big} {small}"

            if small in DENY_SMALL_CATE:
                continue
            if hit_any(text, DENY_PATTERNS):
                continue
            if small not in ALLOW_SMALL_CATE and not hit_any(text, ALLOW_PATTERNS):
                continue
            if q in seen_q:
                continue

            matched_intent = None
            for intent, pat in intent_rules.items():
                if re.search(pat, text):
                    matched_intent = intent
                    break
            if not matched_intent:
                continue
            if len(buckets[matched_intent]) >= args.max_per_intent:
                continue

            seen_q.add(q)
            buckets[matched_intent].append(
                {
                    "que_id": qid,
                    "question": q,
                    "answer": answer_map[qid],
                    "big_cate": big,
                    "small_cate": small,
                    "intent": matched_intent,
                }
            )

    rows = []
    for intent in buckets:
        rows.extend(buckets[intent])

    with out.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["que_id", "question", "answer", "big_cate", "small_cate", "intent"],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"[OK] output={out} total={len(rows)}")
    for k, v in buckets.items():
        print(f"  - {k}: {len(v)}")


if __name__ == "__main__":
    main()
