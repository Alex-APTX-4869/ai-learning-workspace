"""在目录版本已确认的原文范围内检索；不调用模型或扩大资料范围。"""
from copy import deepcopy
from math import log
import re

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.courses.models import Course
from backend.intake.models import IntakeSession
from backend.materials.models import MaterialBatch, MaterialProcess
from backend.materials import service, adoption
from backend.versions.service import get_manifest
from backend.versions.material_models import DraftMaterialBinding
from backend.versions.models import DirectoryDraft


def course_scope(db: Session, course_id: int, outline_version_id: int | None):
    if db.get(Course, course_id) is None:
        raise HTTPException(404, "课程不存在。")
    intake = db.scalar(select(IntakeSession).where(IntakeSession.course_id == course_id))
    brief = get_manifest(db, course_id, outline_version_id).brief_json if outline_version_id is not None else (intake.brief if intake else None)
    basis = (brief or {}).get("material_basis")
    if not basis:
        return None
    batches = basis.get('batches', [basis])
    files = []
    for part in batches:
        batch = db.get(MaterialBatch, part.get('batch_id'))
        binding = db.get(DraftMaterialBinding, part.get('batch_id'))
        draft = db.get(DirectoryDraft, binding.draft_id) if binding else None
        owned = bool(batch and intake and batch.intake_id == intake.id)
        appended = bool(binding and binding.course_id == course_id and draft and draft.status == 'published')
        if not batch or batch.status != 'linked' or not (owned or appended):
            raise HTTPException(409, '当前版本的资料关联不可用，请核对课程资料。')
        frozen = {f['file_id']: f for f in (batch.manifest_json or {}).get('files', [])}
        for item in part.get('files', []):
            allowed = frozen.get(item.get('file_id'))
            if not allowed or any(item.get(k) != allowed.get(k) for k in ('file_id', 'process_id', 'sha256', 'annotations')):
                raise HTTPException(409, '资料范围与确认记录不一致，已停止检索。')
            if item.get('vision_pages', []) != allowed.get('vision_pages', []):
                raise HTTPException(409, '视觉转录修订与确认记录不一致，已停止检索。')
            files.append({**deepcopy(item), 'batch_id': batch.id})
    return {**deepcopy(batches[0]), 'files': files} if batches else None


def terms(text: str) -> set[str]:
    """保留函数名/错误码；中文双字片段支持基本词组检索。"""
    found = set(re.findall(r"[a-z0-9_]+", text.lower()))
    for run in re.findall(r"[\u4e00-\u9fff]+", text):
        found.update(run[i:i+2] for i in range(max(1, len(run)-1)))
    return found


def read_course_materials(db: Session, course_id: int, outline_version_id: int):
    """展示固定版本的资料元数据，不能用最新解析修订冒充历史依据。"""
    basis = course_scope(db, course_id, outline_version_id)
    if not basis:
        return None
    result = service.read_batch(db, basis['batch_id'])
    files = []
    for item in basis.get('files', []):
        batch_id = item.get('batch_id', basis['batch_id'])
        actual = service.get_file(db, batch_id, item['file_id'])
        if actual.sha256 != item['sha256']:
            raise HTTPException(409, '原文件已变化，无法读取固定资料范围。')
        report = service.scoped_report(db, batch_id, item['file_id'], item['process_id'])
        report = adoption.effective_report(db, batch_id, item, report)
        process = db.get(MaterialProcess, item['process_id'])
        files.append({
            'id': actual.id, 'batch_id': batch_id, 'filename': item['filename'], 'suffix': actual.suffix,
            'byte_size': actual.byte_size, 'revision': actual.revision, 'included': True,
            'annotations': item['annotations'], 'text_only_accepted': item.get('text_only', False),
            'process_id': item['process_id'], 'status': process.status, 'page_count': report.get('page_count'),
            'vision_pages': item.get('vision_pages', []),
            'element_count': len(service.selected_elements(report, item['annotations'])),
            'issues': sorted({issue['code'] for issue in report.get('issues', [])}), 'error': None,
        })
    result.update(files=files, context=basis, completeness=basis.get('completeness', 'partial'))
    return result


def passages(db: Session, basis: dict, file_id: str | None = None, page: int | None = None):
    files = basis.get("files", [])
    if file_id is not None and file_id not in {f["file_id"] for f in files}:
        raise HTTPException(404, "该文件未纳入当前课程版本。")
    for file in files:
        if file_id is not None and file["file_id"] != file_id:
            continue
        batch_id = file.get('batch_id', basis['batch_id'])
        actual = service.get_file(db, batch_id, file["file_id"])
        if actual.sha256 != file["sha256"]:
            raise HTTPException(409, "原文件校验值已变化，不能继续使用旧引用。")
        report = service.scoped_report(db, batch_id, file["file_id"], file["process_id"])
        report = adoption.effective_report(db, batch_id, file, report)
        for element in service.selected_elements(report, file["annotations"]):
            if page is not None and element["locator"].get("page") != page:
                continue
            yield file, element, report


def search(db: Session, course_id: int, outline_version_id: int | None, query: str,
           *, file_id: str | None = None, page: int | None = None, limit: int = 6):
    query = query.strip()
    query_terms = terms(query)
    if not query_terms and not (file_id and page):
        raise HTTPException(422, "请输入关键词，或同时选择文件和页码。")
    basis = course_scope(db, course_id, outline_version_id)
    result = {"method": "keyword", "hits": [], "total": 0,
              "scope_available": bool(basis), "outline_version_id": outline_version_id}
    if not basis:
        if file_id:
            raise HTTPException(404, "当前课程版本没有这份资料。")
        return result
    candidates = []
    for file, element, _ in passages(db, basis, file_id, page):
        # 长段分窗，保留原始字符偏移；查中后可读取完整上下文。
        for offset in range(0, len(element["text"]), 700):
            text = element["text"][offset:offset+900]
            tokens = terms(text)
            if not query_terms or tokens & query_terms:
                candidates.append((file, element, offset, text, tokens))
    counts = {term: sum(term in row[4] for row in candidates) for term in query_terms}
    scored = []
    for file, element, offset, text, tokens in candidates:
        score = sum(1 + log(1 + len(candidates)/(1+counts[t])) for t in query_terms & tokens)
        if query and query.lower() in text.lower():
            score += 4
        scored.append((score, {"file_id": file["file_id"], "filename": file["filename"],
            "batch_id": file.get('batch_id', basis["batch_id"]), "process_id": file["process_id"], "element_id": element["id"],
            "locator": element["locator"], "offset": offset, "excerpt": text,
            "text_only": file.get("text_only", False)}))
    scored.sort(key=lambda row: -row[0])
    result["total"] = len(scored)
    result["hits"] = [row[1] for row in scored[:limit]]
    return result


def read_source(db: Session, course_id: int, outline_version_id: int | None,
                file_id: str, process_id: str, element_id: str, offset: int = 0):
    basis = course_scope(db, course_id, outline_version_id)
    if not basis:
        raise HTTPException(404, "当前版本没有可读取的资料。")
    for file, element, report in passages(db, basis, file_id):
        if file["process_id"] != process_id or element["id"] != element_id:
            continue
        preview = element.get("preview")
        if preview not in {a["path"] for a in report.get("artifacts", [])}:
            preview = None
        text = element["text"]
        if offset > len(text):
            raise HTTPException(422, "原文位置超出范围。")
        return {"filename": file["filename"], "locator": element["locator"],
                "text": text[offset:offset+6000], "offset": offset,
                "total_characters": len(text), "next_offset": offset+6000 if offset+6000 < len(text) else None,
                "preview": preview, "batch_id": file.get('batch_id', basis["batch_id"]), "file_id": file_id,
                "process_id": process_id, "element_id": element_id,
                "text_only": file.get('text_only', False)}
    raise HTTPException(404, "这段原文未纳入当前版本，或引用的解析版本不匹配。")
