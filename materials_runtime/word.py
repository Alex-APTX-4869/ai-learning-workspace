from pathlib import Path, PurePosixPath
import zipfile

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph
from lxml import etree

from materials_runtime.common import MAX_UNPACKED_BYTES, ParseFailure, Report


def inspect_package(source: Path):
    with zipfile.ZipFile(source) as archive:
        items = archive.infolist()
        if len(items) > 5000 or sum(item.file_size for item in items) > MAX_UNPACKED_BYTES:
            raise ParseFailure("archive_expansion_limit")
        names = {item.filename for item in items}
        if len(names) != len(items):
            raise ParseFailure("duplicate_archive_entries")
        if "word/document.xml" not in names or "[Content_Types].xml" not in names:
            raise ParseFailure("format_mismatch")
        for item in items:
            path = PurePosixPath(item.filename)
            if path.is_absolute() or ".." in path.parts or "\\" in item.filename or item.flag_bits & 1:
                raise ParseFailure("unsafe_archive_entry")
            lowered = item.filename.lower()
            if "vbaproject" in lowered or lowered.startswith("word/embeddings/"):
                raise ParseFailure("active_content_not_supported")
            if lowered.endswith((".xml", ".rels")):
                raw = archive.read(item)
                if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
                    raise ParseFailure("unsafe_xml")
        types = archive.read("[Content_Types].xml").lower()
        if b"macroenabled" in types:
            raise ParseFailure("active_content_not_supported")


def parse_docx(source: Path, output: Path) -> Report:
    inspect_package(source)
    document = Document(source)
    report = Report(source, "docx", output)
    heading_path: list[str] = []
    paragraph_number = 0
    table_number = 0
    # 遍历 body 子元素，保持段落/表格的原始交错顺序。
    for node in document.element.body:
        if node.tag == qn("w:p"):
            paragraph_number += 1
            paragraph = Paragraph(node, document)
            locator = {"type": "word_paragraph", "paragraph": paragraph_number, "heading_path": list(heading_path)}
            text = paragraph.text.strip()
            style = paragraph.style.name if paragraph.style else ""
            kind = "paragraph"
            if style.startswith("Heading ") and style[8:].isdigit():
                level = int(style[8:])
                heading_path = heading_path[:max(0, level - 1)] + [text]
                locator["heading_path"] = list(heading_path)
                kind = "heading"
                report.data["outline"].append({"title": text, "level": level, "locator": locator})
            if text:
                report.add(kind, text, locator)
            for equation in node.xpath(".//m:oMath"):
                raw = etree.tostring(equation, encoding="unicode")
                # 按节点拼字会把分数 1/2 变成 12，不能冒充可用表达式。
                report.add("formula", "", locator, original_omml=raw, expression_status="unverified")
                report.issue("formula_conversion_pending", locator)
            if node.xpath(".//w:drawing | .//w:pict | .//w:object"):
                report.add("visual", "", locator, description_status="pending")
                report.issue("figure_or_chart_review_pending", locator)
            if node.xpath(".//w:fldSimple | .//w:instrText"):
                report.issue("dynamic_field_not_evaluated", locator)
            if node.xpath(".//w:ins | .//w:del | .//w:moveFrom | .//w:moveTo"):
                report.issue("tracked_changes_require_decision", locator)
        elif node.tag == qn("w:tbl"):
            table_number += 1
            table = Table(node, document)
            locator = {"type": "word_table", "table": table_number, "heading_path": list(heading_path)}
            rows = [[cell.text for cell in row.cells] for row in table.rows]
            report.add("table", "\n".join(" | ".join(row) for row in rows), locator, rows=rows)
            if node.xpath(".//w:vMerge | .//w:gridSpan | .//w:tbl | .//m:oMath | .//w:drawing"):
                # 行列文本可用，但合并单元格和嵌套内容不能假装已完整理解。
                report.issue("complex_table_review_pending", locator)
        elif node.tag != qn("w:sectPr"):
            report.issue("unsupported_word_body_element")
    with zipfile.ZipFile(source) as archive:
        names = archive.namelist()
        if any(name.startswith(("word/header", "word/footer", "word/footnotes", "word/endnotes", "word/comments")) for name in names):
            report.issue("secondary_word_parts_not_indexed")
        if any(name.startswith("word/charts/") for name in names):
            report.issue("chart_data_review_pending")
    if not report.data["elements"]:
        report.issue("no_readable_content")
    report.data["coverage"] = {"text": "extracted" if report.data["elements"] else "missing",
                               "visual": "pending_review" if report.data["issues"] else "no_visual_elements_detected"}
    return report
