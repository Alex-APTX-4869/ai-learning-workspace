from pathlib import Path
import math

from pypdf import PdfReader
import pypdfium2 as pdfium

from materials_runtime.common import MAX_PAGES, ParseFailure, Report


def parse_pdf(source: Path, output: Path) -> Report:
    reader = PdfReader(source, strict=True)
    if reader.is_encrypted:
        raise ParseFailure("encrypted_document")
    page_count = len(reader.pages)
    if not 0 < page_count <= MAX_PAGES:
        raise ParseFailure("page_limit_exceeded")
    report = Report(source, "pdf", output)
    report.data["page_count"] = page_count
    document = pdfium.PdfDocument(source)
    text_pages = 0
    try:
        for index in range(page_count):
            locator = {"type": "pdf_page", "page": index + 1}
            page = document[index]
            try:
                width, height = page.get_size()
                if not all(math.isfinite(v) and 0 < v <= 20000 for v in (width, height)):
                    raise ParseFailure("invalid_page_dimensions")
                # 原页预览保留公式和图表，不把纯文本视为全部内容。
                bitmap = page.render(scale=min(1.5, 1600 / max(width, height)))
                preview = f"page-{index + 1}.png"
                try:
                    bitmap.to_pil().save(output / preview)
                finally:
                    bitmap.close()
                report.artifact(preview, "image/png", locator)
                try:
                    text = reader.pages[index].extract_text() or ""
                except Exception:
                    text = ""
                    report.issue("page_text_extraction_failed", locator)
                if text.strip():
                    text_pages += 1
                    # 页内段落不冒充精确 bbox；引用至少能回到完整原页。
                    for paragraph in text.split("\n\n"):
                        if paragraph.strip():
                            report.add("paragraph", paragraph.strip(), locator, preview=preview)
                else:
                    report.add("page_image", "", locator, preview=preview)
                    report.issue("ocr_required", locator)
                report.issue("page_visual_review_pending", locator)
            finally:
                page.close()
    finally:
        document.close()
    # 读取原生目录，而非根据 Top-K 检索片段猜测整份文件包含哪些章节。
    def visit(items, depth=0):
        if depth > 12:
            return
        for item in items:
            if len(report.data["outline"]) >= 2000:
                report.issue("outline_limit_exceeded")
                return
            if isinstance(item, list):
                visit(item, depth + 1)
            else:
                number = reader.get_destination_page_number(item)
                if number is not None:
                    report.data["outline"].append({"title": str(item.title)[:500], "level": depth + 1,
                                                   "locator": {"type": "pdf_page", "page": number + 1}})
    try:
        visit(reader.outline)
    except Exception:
        report.issue("outline_unreadable")
    report.data["coverage"] = {"text": "extracted" if text_pages == page_count else "partial" if text_pages else "missing",
                               "visual": "pending_review", "pages_with_text": text_pages,
                               "pages_rendered": page_count}
    return report
