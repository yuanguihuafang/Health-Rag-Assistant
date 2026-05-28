# 健康 RAG 评测集说明

本目录用于保存**固定评测集**，只用于评测，不参与知识库导入与向量化入库。

## 目的

1. 保证每次修改检索/Prompt/模型后，都能和同一批问题对比效果。
2. 避免“训练数据与评测数据混用”导致评测结果虚高。

## 文件

- `health_eval_questions_v1.jsonl`：V1 固定评测问题（每行一个 JSON）。

## 字段说明

- `id`: 问题唯一标识
- `question`: 评测问题
- `expected_keywords`: 期望答案包含的关键词（用于粗评）
- `expected_topic`: 期望主题标签（用于分类命中观察）

## 使用建议

1. 不要把本目录文件导入知识库。
2. 先固定使用 `v1` 跑基线，再在后续版本中新增 `v2`。
3. 每次评测保留结果文件（命中率、关键词覆盖、平均耗时）。

## 生成命令

1. 常规抽样评测集（cMedQA）

```bash
python manage.py build_cmedqa_eval_set --limit 100 --seed 2026 --output health_eval_questions_cmedqa_v1.jsonl
```

2. hardcase 评测集（术语 / 口语 / 多轮，默认从当前数据库 active 知识文档抽样）

```bash
python manage.py build_health_hardcase_eval_set --limit 50 --seed 2026 --output health_eval_questions_hardcase_v1.jsonl --multi-turn-ratio 0.2
```

3. hardcase 评测集（如需兼容旧流程，可显式改为 cMedQA CSV 来源）

```bash
python manage.py build_health_hardcase_eval_set --source csv --limit 50 --seed 2026 --output health_eval_questions_hardcase_csv_v1.jsonl --multi-turn-ratio 0.2
```
