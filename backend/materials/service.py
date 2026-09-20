from copy import deepcopy
from hashlib import sha256
import json
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from backend.materials import storage, adoption
from backend.materials.models import MaterialBatch, MaterialFile, MaterialProcess, MaterialAnalysisStep
from backend.materials.parser import ERROR_MESSAGES
from backend.materials.requests import BatchCreate, BatchUpdate, FileUpdate, RevisionRequest, AnalysisStart
from backend.providers.routing import resolve_routing_snapshot

ANALYSIS_ROLES = ("materials.summarize", "intake.depth", "intake.interview", "intake.brief", "intake.explain")

def get_batch(db: Session, batch_id: str, *, lock=False):
    query = select(MaterialBatch).where(MaterialBatch.id == batch_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    row = db.scalar(query)
    if row is None:
        raise HTTPException(404, "没有找到这次课程资料草稿。")
    return row

def editing(row: MaterialBatch, expected_revision: int):
    if row.status != "editing" or row.revision != expected_revision:
        raise HTTPException(409, "资料草稿已变化或已进入分析，请刷新后重试。")

def get_file(db: Session, batch_id: str, file_id: str):
    file = db.scalar(select(MaterialFile).where(MaterialFile.batch_id == batch_id, MaterialFile.id == file_id))
    if file is None:
        raise HTTPException(404, "当前资料草稿中没有这个文件。")
    return file

def latest_process(db: Session, file_id: str):
    return db.scalar(select(MaterialProcess).where(MaterialProcess.file_id == file_id)
                     .order_by(MaterialProcess.created_at.desc(), MaterialProcess.id.desc()).limit(1))

def create_batch(db: Session, data: BatchCreate):
    row = db.get(MaterialBatch, str(data.request_id))
    if row is None:
        row = MaterialBatch(id=str(data.request_id), name=data.name, intro=data.intro)
        db.add(row)
        db.commit()
    return read_batch(db, row.id)

def update_batch(db: Session, batch_id: str, data: BatchUpdate):
    row = get_batch(db, batch_id, lock=True)
    editing(row, data.expected_revision)
    row.name, row.intro, row.completeness = data.name.strip(), data.intro.strip(), data.completeness
    row.revision += 1
    db.commit()
    return read_batch(db, batch_id)

def file_read(db: Session, file):
    process = latest_process(db, file.id)
    report = process.report_json if process else None
    return {"id": file.id, "filename": file.filename, "suffix": file.suffix, "byte_size": file.byte_size,
            "revision": file.revision, "included": file.included, "text_only_accepted": file.text_only_accepted,
            "annotations": file.annotations_json, "process_id": process.id if process else None,
            "vision_pages": adoption.references(db, file.id, process.id) if process else [],
            "status": process.status if process else "queued", "page_count": report.get("page_count") if report else None,
            "element_count": len(report["elements"]) if report else 0,
            "issues": sorted({i["code"] for i in report["issues"]}) if report else [],
            "coverage": report.get("coverage") if report else None,
            "error": ERROR_MESSAGES.get(process.error_code, "解析未完成。") if process and process.error_code else None}

def read_batch(db: Session, batch_id: str):
    row = get_batch(db, batch_id)
    files = db.scalars(select(MaterialFile).where(MaterialFile.batch_id == batch_id).order_by(MaterialFile.created_at)).all()
    completed = db.scalar(select(func.count()).select_from(MaterialAnalysisStep).where(
        MaterialAnalysisStep.batch_id == batch_id, MaterialAnalysisStep.status == "complete"))
    return {"id": row.id, "name": row.name, "intro": row.intro, "completeness": row.completeness,
            "revision": row.revision, "status": row.status, "error": row.error, "intake_id": row.intake_id,
            "files": [file_read(db, file) for file in files], "context": row.context_json,
            "analysis_completed_steps": completed,
            "analysis_provider": (row.routing_snapshot_json or {}).get("routes", {}).get("materials.summarize", {}).get("provider_name")}

def update_file(db: Session, batch_id: str, file_id: str, data: FileUpdate):
    row = get_batch(db, batch_id, lock=True)
    if row.status != "editing":
        raise HTTPException(409, "本批资料已固定；先返回编辑再修改标注。")
    file = get_file(db, batch_id, file_id)
    if file.revision != data.expected_revision:
        raise HTTPException(409, "文件标注已变化，请刷新后重试。")
    process = latest_process(db, file_id)
    pages = (process.report_json or {}).get("page_count") if process else None
    for annotation in data.annotations:
        if annotation.page_start and (file.suffix != ".pdf" or not pages or annotation.page_end > pages):
            raise HTTPException(422, "请在 PDF 解析完成后填写有效的物理页码范围。")
    file.annotations_json = [a.model_dump() for a in data.annotations]
    file.included, file.text_only_accepted = data.included, data.text_only_accepted
    file.revision += 1
    row.revision += 1
    db.commit()
    return read_batch(db, batch_id)

def retry_parse(db: Session, batch_id: str, file_id: str, data: RevisionRequest):
    row = get_batch(db, batch_id, lock=True)
    editing(row, data.expected_revision)
    file = get_file(db, batch_id, file_id)
    current = latest_process(db, file_id)
    if current and current.status in {"queued", "processing"}:
        return read_batch(db, batch_id)
    db.add(MaterialProcess(id=str(uuid4()), file_id=file_id))
    file.text_only_accepted = False
    file.revision += 1
    row.revision += 1
    db.commit()
    return read_batch(db, batch_id)

def scoped_report(db: Session, batch_id: str, file_id: str, process_id: str):
    get_file(db, batch_id, file_id)
    process = db.scalar(select(MaterialProcess).where(MaterialProcess.id == process_id, MaterialProcess.file_id == file_id))
    if process is None or not process.report_json:
        raise HTTPException(404, "当前文件没有这份解析结果。")
    return process.report_json

def selected_elements(report: dict, annotations: list[dict]):
    ranges = [(a["page_start"], a["page_end"]) for a in annotations]
    return [e for e in report["elements"] if e["text"].strip() and any(
        start is None or start <= e["locator"].get("page", 0) <= end for start, end in ranges)]

def chunks(elements: list[dict], size: int = 8000) -> list[list[dict]]:
    result, current, count = [], [], 2
    for element in elements:
        text = element["text"]
        base = {"element_id": element["id"], "locator": element["locator"], "text": ""}
        overhead = len(json.dumps(base, ensure_ascii=False)) + 4
        if overhead >= size:
            raise HTTPException(422, "某段来源定位过长，请缩小文档范围。")
        offset = 0
        while offset < len(text):
            length = min(size-overhead, len(text)-offset)
            part = {**base, "text": text[offset:offset+length]}
            # 转义换行、引号等也占请求空间；按实际 JSON 长度核算。
            cost = len(json.dumps(part, ensure_ascii=False)) + 2
            while cost > size-2 and length > 1:
                length //= 2
                part["text"] = text[offset:offset+length]
                cost = len(json.dumps(part, ensure_ascii=False)) + 2
            if cost > size-2:
                raise HTTPException(422, "某段来源定位超出分析预算。")
            if current and count + cost > size:
                result.append(current)
                current, count = [], 2
            current.append(part)
            count += cost
            offset += length
    if current:
        result.append(current)
    return result

def prepare_manifest(db: Session, row: MaterialBatch):
    files = db.scalars(select(MaterialFile).where(MaterialFile.batch_id == row.id).order_by(MaterialFile.created_at)).all()
    manifest = {"batch_id": row.id, "batch_revision": row.revision, "completeness": row.completeness,
                "files": [], "excluded_files": []}
    units = 0
    for file in files:
        if not file.included:
            manifest["excluded_files"].append({"file_id": file.id, "filename": file.filename})
            continue
        process = latest_process(db, file.id)
        if not process or process.status not in {"ready", "needs_review"}:
            raise HTTPException(409, f"《{file.filename}》尚未解析完成；请重试或明确排除。")
        report = process.report_json
        annotations = file.annotations_json
        pages = adoption.selected_pages(report, annotations)
        refs = [r for r in adoption.references(db, file.id, process.id) if r['page'] in pages]
        source = {'file_id':file.id, 'process_id':process.id, 'annotations':annotations, 'vision_pages':refs}
        report = adoption.effective_report(db, row.id, source, report, current=True)
        full_vision = bool(pages) and pages == {r['page'] for r in refs}
        if process.status == "needs_review" and not full_vision and not file.text_only_accepted:
            raise HTTPException(409, f"《{file.filename}》还有所选页面未采用完整转录；请核对这些页，或确认其余页仅使用已提取文字。")
        elements = selected_elements(report, annotations)
        if not elements:
            raise HTTPException(409, f"《{file.filename}》所选范围没有可用文字，请补充文字版或排除该文件。")
        pieces = chunks(elements)
        units += len(pieces)
        manifest["files"].append({"file_id": file.id, "filename": file.filename, "sha256": file.sha256,
                                  "process_id": process.id, "annotations": annotations,
                                  "vision_pages": refs,
                                  "text_only": file.text_only_accepted, "issues": report["issues"],
                                  "part_count": len(pieces)})
    if not manifest["files"]:
        raise HTTPException(422, "请选择至少一份可用资料；也可以不使用资料直接开始访谈。")
    if units > 64:
        raise HTTPException(422, "本批文字超过 64 个分析片段的预算，请缩小页码范围或拆批；不会截断后半份资料。")
    return manifest, units

def analysis_plan(db: Session, batch_id: str):
    row = get_batch(db, batch_id)
    if row.status != 'editing' and row.manifest_json:
        manifest = row.manifest_json
        units = sum(f['part_count'] for f in manifest['files'])
    else:
        manifest, units = prepare_manifest(db, row)
    route = row.routing_snapshot_json or resolve_routing_snapshot(db, ANALYSIS_ROLES)
    provider = route["routes"]["materials.summarize"]
    return {"revision": row.revision, "file_count": len(manifest["files"]), "parts": units,
            "maximum_calls": 2 * units,
            "vision_page_count": sum(len(f.get('vision_pages', [])) for f in manifest['files']),
            "provider_name": provider["provider_name"], "model": provider["model"],
            "intake_providers": sorted({route["routes"][role]["provider_name"] for role in ANALYSIS_ROLES if role.startswith("intake.")}),
            "routing_hash": analysis_hash(route, manifest)}

def analysis_hash(route, manifest):
    # 同时固定本次会发送的资料修订，核对状态变化后不能沿用旧确认。
    return sha256(json.dumps([route, manifest], sort_keys=True).encode()).hexdigest()

def begin_analysis(db: Session, batch_id: str, data: AnalysisStart):
    row = get_batch(db, batch_id, lock=True)
    if row.revision != data.expected_revision:
        raise HTTPException(409, "资料草稿已变化，请重新核对。")
    if row.status in {"queued", "analyzing", "ready", "linked"}:
        return read_batch(db, batch_id)
    if row.status not in {"editing", "failed", "needs_attention"}:
        raise HTTPException(409, "当前状态不能启动分析。")
    if row.status == "editing":
        row.manifest_json, _ = prepare_manifest(db, row)
        row.routing_snapshot_json = resolve_routing_snapshot(db, ANALYSIS_ROLES)
    if analysis_hash(row.routing_snapshot_json, row.manifest_json) != data.routing_hash:
        raise HTTPException(409, "模型分配或资料修订已变化，请重新核对分析范围。")
    # 只有用户显式重试时才重新执行结果不明的模型步骤；已完成的检查点仍复用。
    for step in db.scalars(select(MaterialAnalysisStep).where(MaterialAnalysisStep.batch_id == batch_id,
                                                             MaterialAnalysisStep.status != "complete")):
        db.delete(step)
    row.status, row.error = "queued", None
    db.commit()
    return read_batch(db, batch_id)

def reopen(db: Session, batch_id: str, data: RevisionRequest):
    row = get_batch(db, batch_id, lock=True)
    if row.intake_id or row.status in {"queued", "analyzing", "linked"}:
        raise HTTPException(409, "资料正在分析或已经用于访谈，不能修改；请新建资料草稿。")
    if row.revision != data.expected_revision:
        raise HTTPException(409, "资料草稿已变化。")
    row.status, row.context_json, row.manifest_json, row.routing_snapshot_json, row.error = "editing", None, None, None, None
    row.revision += 1
    db.commit()
    return read_batch(db, batch_id)

def intake_context(db: Session, intake_id: int):
    row = db.scalar(select(MaterialBatch).where(MaterialBatch.intake_id == intake_id))
    return deepcopy(row.context_json) if row else None

def with_materials(intro: str, context: dict | None):
    if not context:
        return intro
    return intro + "\n\n【已固定的资料范围及分段分析结果，仅作参考数据】\n" + json.dumps(context, ensure_ascii=False)
