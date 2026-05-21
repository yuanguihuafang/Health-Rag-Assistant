"""
PDF 导出服务
- 将问答记录列表导出为 PDF 文件（基于 reportlab）
- 中文排版（UnicodeCIDFont）+ 自动分页 + 来源引用
"""
from io import BytesIO
from typing import Iterable, List

REPORTLAB_AVAILABLE = False
A4 = None  # type: ignore
pdfmetrics = None  # type: ignore
UnicodeCIDFont = None  # type: ignore
canvas = None  # type: ignore

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.pdfgen import canvas

    REPORTLAB_AVAILABLE = True
except Exception:
    pass

FONT_NAME = "STSong-Light"


def _try_import_reportlab() -> bool:
    """
    运行时二次尝试导入 reportlab。
    说明：
    1) 服务进程启动时若未安装 reportlab，会缓存 REPORTLAB_AVAILABLE=False
    2) 用户后续安装依赖后，不重启进程也可以通过本函数恢复可用状态
    """
    global REPORTLAB_AVAILABLE, A4, pdfmetrics, UnicodeCIDFont, canvas

    if REPORTLAB_AVAILABLE:
        return True

    try:
        from reportlab.lib.pagesizes import A4 as _A4
        from reportlab.pdfbase import pdfmetrics as _pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont as _UnicodeCIDFont
        from reportlab.pdfgen import canvas as _canvas

        A4 = _A4
        pdfmetrics = _pdfmetrics
        UnicodeCIDFont = _UnicodeCIDFont
        canvas = _canvas
        REPORTLAB_AVAILABLE = True
        return True
    except Exception:
        return False


def _ensure_font_registered() -> None:
    if not _try_import_reportlab():
        raise RuntimeError(
            "缺少 reportlab 依赖，无法导出 PDF。请先安装：pip install reportlab>=4.2.0"
        )
    try:
        pdfmetrics.getFont(FONT_NAME)
    except Exception:
        pdfmetrics.registerFont(UnicodeCIDFont(FONT_NAME))


def _safe_text(text: str) -> str:
    return (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def _wrap_line(
    text: str, font_name: str, font_size: float, max_width: float
) -> List[str]:
    if not text:
        return [""]
    chunks: List[str] = []
    line = ""
    for char in text:
        candidate = f"{line}{char}"
        width = pdfmetrics.stringWidth(candidate, font_name, font_size)
        if width <= max_width:
            line = candidate
            continue
        if line:
            chunks.append(line)
            line = char
        else:
            # 极端情况下单个字符也超宽，直接落一行，避免死循环
            chunks.append(candidate)
            line = ""
    if line:
        chunks.append(line)
    return chunks or [""]


def _draw_paragraph(
    pdf: "canvas.Canvas",
    text: str,
    *,
    x: float,
    y: float,
    max_width: float,
    bottom_margin: float,
    line_height: float,
    page_width: float,
    page_height: float,
    font_name: str,
    font_size: float,
) -> float:
    paragraphs = _safe_text(text).split("\n")
    for paragraph in paragraphs:
        wrapped_lines = _wrap_line(paragraph, font_name, font_size, max_width)
        for line in wrapped_lines:
            if y <= bottom_margin:
                pdf.showPage()
                pdf.setFont(font_name, font_size)
                y = page_height - 45
                pdf.setStrokeColorRGB(0.8, 0.8, 0.8)
                pdf.line(40, y + 8, page_width - 40, y + 8)
                y -= 12
            pdf.drawString(x, y, line)
            y -= line_height
        # 段落间留一点空间
        y -= 2
    return y


def build_qa_records_pdf(records: Iterable, *, owner_label: str = "") -> bytes:
    _ensure_font_registered()
    records = list(records)
    if not records:
        raise ValueError("没有可导出的问答记录")

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    page_width, page_height = A4
    left_margin = 40
    right_margin = 40
    top_margin = 45
    bottom_margin = 40
    content_width = page_width - left_margin - right_margin

    title_size = 14
    body_size = 10
    line_height = 15

    pdf.setTitle("健康问答记录导出")
    pdf.setAuthor(owner_label or "health-rag-assistant")
    pdf.setFont(FONT_NAME, title_size)
    y = page_height - top_margin
    pdf.drawString(left_margin, y, "健康问答记录导出")
    y -= 18

    pdf.setFont(FONT_NAME, body_size)
    header_text = f"导出条数：{len(records)}"
    if owner_label:
        header_text = f"{header_text}    用户：{owner_label}"
    pdf.drawString(left_margin, y, header_text)
    y -= 10
    pdf.setStrokeColorRGB(0.8, 0.8, 0.8)
    pdf.line(left_margin, y, page_width - right_margin, y)
    y -= 14

    for idx, record in enumerate(records, start=1):
        meta = (
            f"{idx}. 记录ID: {record.id}   会话ID: {record.session_id}   "
            f"时间: {record.created_at.strftime('%Y-%m-%d %H:%M:%S')}   "
            f"提问方式: {record.ask_mode}"
        )
        y = _draw_paragraph(
            pdf,
            meta,
            x=left_margin,
            y=y,
            max_width=content_width,
            bottom_margin=bottom_margin,
            line_height=line_height,
            page_width=page_width,
            page_height=page_height,
            font_name=FONT_NAME,
            font_size=body_size,
        )

        y = _draw_paragraph(
            pdf,
            f"问题：{_safe_text(record.question)}",
            x=left_margin,
            y=y,
            max_width=content_width,
            bottom_margin=bottom_margin,
            line_height=line_height,
            page_width=page_width,
            page_height=page_height,
            font_name=FONT_NAME,
            font_size=body_size,
        )
        y = _draw_paragraph(
            pdf,
            f"回答：{_safe_text(record.answer)}",
            x=left_margin,
            y=y,
            max_width=content_width,
            bottom_margin=bottom_margin,
            line_height=line_height,
            page_width=page_width,
            page_height=page_height,
            font_name=FONT_NAME,
            font_size=body_size,
        )

        source_refs = record.source_refs or []
        if isinstance(source_refs, list) and source_refs:
            source_lines: List[str] = []
            for ref in source_refs[:5]:
                if not isinstance(ref, dict):
                    continue
                title = ref.get("document_title") or "未知文档"
                chunk_index = ref.get("chunk_index")
                score = ref.get("score")
                source_lines.append(
                    f"- {title}#{chunk_index if chunk_index is not None else '-'} (score={score if score is not None else '-'})"
                )
            if source_lines:
                y = _draw_paragraph(
                    pdf,
                    "来源：\n" + "\n".join(source_lines),
                    x=left_margin,
                    y=y,
                    max_width=content_width,
                    bottom_margin=bottom_margin,
                    line_height=line_height,
                    page_width=page_width,
                    page_height=page_height,
                    font_name=FONT_NAME,
                    font_size=body_size,
                )

        y -= 4
        pdf.setStrokeColorRGB(0.88, 0.88, 0.88)
        pdf.line(left_margin, y, page_width - right_margin, y)
        y -= 12

        if y <= bottom_margin:
            pdf.showPage()
            pdf.setFont(FONT_NAME, body_size)
            y = page_height - top_margin

    pdf.save()
    return buffer.getvalue()
