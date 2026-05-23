"""
结构化 Markdown 解析服务

支持按 `## 条目 xxx` 将健康 FAQ 类 Markdown 拆成独立条目，
保留主题、问题、回答、关键词字段，跳过文件标题和说明。
"""
import re
from typing import List


ENTRY_RE = re.compile(
    r"^##\s*条目\s*(?P<entry_no>\d+)\s*$"
    r"(?P<body>.*?)(?=^##\s*条目\s*\d+\s*$|\Z)",
    re.MULTILINE | re.DOTALL,
)


def _field(body: str, name: str) -> str:
    pattern = re.compile(rf"^{re.escape(name)}[:：]\s*(.+?)\s*$", re.MULTILINE)
    match = pattern.search(body)
    return match.group(1).strip() if match else ""


def parse_markdown_entries(text: str) -> List[dict]:
    entries = []
    for match in ENTRY_RE.finditer(str(text or "")):
        entry_no = match.group("entry_no").strip().zfill(3)
        body = match.group("body").strip()
        topic = _field(body, "主题")
        question = _field(body, "问题")
        answer = _field(body, "回答")
        keywords_text = _field(body, "关键词")
        keywords = [
            item.strip()
            for item in re.split(r"[、,，]", keywords_text)
            if item.strip()
        ]
        if not question or not answer:
            continue
        content = "\n".join(
            [
                f"主题：{topic}",
                "",
                f"问题：{question}",
                "",
                f"回答：{answer}",
                "",
                f"关键词：{keywords_text}",
            ]
        ).strip()
        entries.append(
            {
                "entry_no": entry_no,
                "topic": topic,
                "question": question,
                "answer": answer,
                "keywords": keywords,
                "keywords_text": keywords_text,
                "content": content,
            }
        )
    return entries
