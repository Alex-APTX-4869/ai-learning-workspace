from hashlib import sha256
from pathlib import Path
import os
import tempfile
import unicodedata
from uuid import UUID, uuid4
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.courses.models import Course
from backend.intake.models import IntakeSession
from backend.materials import service, storage
from backend.materials import retrieval
from backend.materials.models import MaterialBatch, MaterialFile, MaterialProcess
from backend.materials.parser import MAX_FILE_BYTES, FORMATS
from backend.materials.requests import BatchCreate, BatchUpdate, FileUpdate, RevisionRequest, AnalysisStart
from backend.materials.vision_router import router as vision_router

router = APIRouter(prefix="/material-batches", tags=["课程资料"])
router.include_router(vision_router)
Database = Annotated[Session, Depends(get_db)]

@router.post("", status_code=201)
def create(data: BatchCreate, db: Database):
    return service.create_batch(db, data)

@router.get("/for-course/{course_id}")
def for_course(course_id: int, db: Database, outline_version_id: int | None = Query(default=None, ge=1)):
    if outline_version_id is not None:
        return retrieval.read_course_materials(db, course_id, outline_version_id)
    if db.get(Course, course_id) is None:
        raise HTTPException(404, "课程不存在。")
    batch = db.scalar(select(MaterialBatch).join(IntakeSession, MaterialBatch.intake_id == IntakeSession.id)
                      .where(IntakeSession.course_id == course_id))
    return service.read_batch(db, batch.id) if batch else None

@router.get("/for-course/{course_id}/search")
def search_sources(course_id: int, db: Database,
                   q: str = Query(default="", max_length=500),
                   outline_version_id: int | None = Query(default=None, ge=1),
                   file_id: UUID | None = None, page: int | None = Query(default=None, ge=1, le=150),
                   limit: int = Query(default=6, ge=1, le=12)):
    return retrieval.search(db, course_id, outline_version_id, q,
                            file_id=str(file_id) if file_id else None, page=page, limit=limit)

@router.get("/for-course/{course_id}/source")
def read_source(course_id: int, db: Database, file_id: UUID, process_id: UUID,
                element_id: str = Query(min_length=1, max_length=200),
                outline_version_id: int | None = Query(default=None, ge=1),
                offset: int = Query(default=0, ge=0)):
    return retrieval.read_source(db, course_id, outline_version_id, str(file_id), str(process_id), element_id, offset)

@router.get("/{batch_id}")
def read(batch_id: UUID, db: Database):
    return service.read_batch(db, str(batch_id))

@router.patch("/{batch_id}")
def update(batch_id: UUID, data: BatchUpdate, db: Database):
    return service.update_batch(db, str(batch_id), data)

@router.put("/{batch_id}/files/{request_id}", status_code=201)
async def upload(batch_id: UUID, request_id: UUID, request: Request, db: Database,
                 filename: str = Query(min_length=1, max_length=240), expected_revision: int = Query(ge=1)):
    bid, rid = str(batch_id), str(request_id)
    filename = unicodedata.normalize("NFC", filename)
    if any(ord(c) < 32 or c in "/\\" for c in filename):
        raise HTTPException(422, "文件名包含非法字符。")
    suffix = Path(filename).suffix.lower()
    if suffix not in FORMATS:
        raise HTTPException(422, "请选择 PDF、DOCX、DOC 或 PNG/JPEG 图片。")
    row = service.get_batch(db, bid)
    if row.status != "editing":
        raise HTTPException(409, "这批资料已进入分析，不能再上传。")
    db.rollback()
    incoming = storage.root() / ".incoming"
    incoming.mkdir(exist_ok=True, mode=0o700)
    fd, tmp_name = tempfile.mkstemp(prefix="upload-", dir=incoming)
    tmp = Path(tmp_name)
    size, digest = 0, sha256()
    try:
        with os.fdopen(fd, "wb") as stream:
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_FILE_BYTES:
                    raise HTTPException(413, "单份资料不能超过 25 MB，请拆分后上传。")
                digest.update(chunk)
                stream.write(chunk)
        if size == 0:
            raise HTTPException(422, "不能上传空文件。")
        row = service.get_batch(db, bid, lock=True)
        existing = db.scalar(select(MaterialFile).where(MaterialFile.batch_id == bid, MaterialFile.request_id == rid))
        if existing:
            if existing.sha256 != digest.hexdigest() or existing.filename != filename:
                raise HTTPException(409, "这次上传标识已用于不同文件。")
            return service.read_batch(db, bid)
        service.editing(row, expected_revision)
        count, total = db.execute(select(func.count(), func.coalesce(func.sum(MaterialFile.byte_size), 0))
                                  .where(MaterialFile.batch_id == bid)).one()
        if count >= 30 or total + size > 200 * 1024 * 1024:
            raise HTTPException(413, "每批最多 30 份、合计 200 MB 资料，请分批处理。")
        file = MaterialFile(id=str(uuid4()), batch_id=bid, request_id=rid, filename=filename,
                            suffix=suffix, sha256=digest.hexdigest(), byte_size=size,
                            annotations_json=[{"role": "auto", "chapter": "", "note": "", "page_start": None, "page_end": None}])
        target = storage.original(file)
        target.parent.mkdir(mode=0o700)
        os.replace(tmp, target)
        db.add(file)
        db.flush()
        db.add(MaterialProcess(id=str(uuid4()), file_id=file.id))
        row.revision += 1
        db.commit()
        return service.read_batch(db, bid)
    finally:
        if tmp.exists():
            tmp.unlink()

@router.patch("/{batch_id}/files/{file_id}")
def annotate(batch_id: UUID, file_id: UUID, data: FileUpdate, db: Database):
    return service.update_file(db, str(batch_id), str(file_id), data)

@router.post("/{batch_id}/files/{file_id}/retry")
def retry(batch_id: UUID, file_id: UUID, data: RevisionRequest, db: Database):
    return service.retry_parse(db, str(batch_id), str(file_id), data)

@router.get("/{batch_id}/files/{file_id}/original")
def original(batch_id: UUID, file_id: UUID, db: Database):
    file = service.get_file(db, str(batch_id), str(file_id))
    path = storage.original(file)
    if not path.is_file():
        raise HTTPException(404, "原文件暂不可用。")
    return FileResponse(path, media_type="application/octet-stream", filename=file.filename,
                        headers={"X-Content-Type-Options": "nosniff"})

@router.get("/{batch_id}/files/{file_id}/processes/{process_id}")
def report(batch_id: UUID, file_id: UUID, process_id: UUID, db: Database,
           offset: int = Query(default=0, ge=0), limit: int = Query(default=50, ge=1, le=100)):
    report = service.scoped_report(db, str(batch_id), str(file_id), str(process_id))
    return {**report, "elements": report["elements"][offset:offset+limit], "element_count": len(report["elements"])}

@router.get("/{batch_id}/files/{file_id}/processes/{process_id}/artifacts/{name}")
def artifact(batch_id: UUID, file_id: UUID, process_id: UUID, name: str, db: Database):
    report = service.scoped_report(db, str(batch_id), str(file_id), str(process_id))
    if name not in {a["path"] for a in report["artifacts"]}:
        raise HTTPException(404, "当前解析结果没有这个预览。")
    path = storage.process_dir(str(file_id), str(process_id)) / name
    if not path.is_file() or path.is_symlink():
        raise HTTPException(404, "预览文件暂不可用。")
    return FileResponse(path, media_type="image/png", headers={"X-Content-Type-Options": "nosniff"})

@router.get("/{batch_id}/analysis-plan")
def analysis_plan(batch_id: UUID, db: Database):
    return service.analysis_plan(db, str(batch_id))

@router.post("/{batch_id}/analyze")
def analyze(batch_id: UUID, data: AnalysisStart, db: Database):
    return service.begin_analysis(db, str(batch_id), data)

@router.post("/{batch_id}/reopen")
def reopen(batch_id: UUID, data: RevisionRequest, db: Database):
    return service.reopen(db, str(batch_id), data)
