from hashlib import sha256
import json
import re
from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from backend.materials import service, storage
from backend.materials.vision_models import PageRecognition
from backend.materials.vision_schemas import RecognitionStart, RecognitionReview, RecognizedPage
from backend.materials.vision_client import PROMPT_VERSION, recognize
from backend.providers.routing import resolve_routing_snapshot
from backend.intake.models import IntakeSession


def page_source(db, batch_id, file_id, process_id, page):
    file = service.get_file(db, batch_id, file_id)
    report = service.scoped_report(db, batch_id, file_id, process_id)
    if file.suffix != ".pdf" or not 1 <= page <= (report.get("page_count") or 0):
        raise HTTPException(422, "请选择有效的 PDF 物理页码。")
    artifact = next((a for a in report["artifacts"] if a["locator"].get("page") == page), None)
    if not artifact or not re.fullmatch(r"[a-z0-9-]+\.png", artifact["path"]):
        raise HTTPException(409, "这一页没有可用原页图片，请重新解析文件。")
    path = storage.process_dir(file_id, process_id) / artifact["path"]
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 8 * 1024 * 1024:
        raise HTTPException(409, "原页图片缺失或超过单页识别预算。")
    text = "\n\n".join(e["text"] for e in report["elements"] if e["locator"].get("page") == page and e.get("text"))
    if len(text) > 24000:
        raise HTTPException(422, "本页文字超过单页识别预算，请拆分资料后重试；没有截断发送。")
    return file, artifact["path"], path.read_bytes(), text


def read_job(job):
    return {"id": job.id, "page": job.page, "process_id": job.process_id, "status": job.status,
            "provider_name": job.route_json["provider_name"], "model": job.route_json["model"],
            "result": job.result_json, "error": job.error, "review": job.review,
            "review_note": job.review_note, "revision": job.revision, "plan_hash": job.input_hash}


def page_view(db, batch_id, file_id, process_id, page):
    file, preview, _, text = page_source(db, batch_id, file_id, process_id, page)
    jobs = db.scalars(select(PageRecognition).where(PageRecognition.file_id == file_id,
        PageRecognition.process_id == process_id, PageRecognition.page == page)
        .order_by(PageRecognition.created_at.desc(), PageRecognition.id.desc()).limit(10)).all()
    from backend.materials.adoption import references
    return {"filename": file.filename, "page": page, "preview": preview, "text": text,
            "file_revision": file.revision, "editable": service.get_batch(db,batch_id).status == 'editing',
            "adoption": next((r for r in references(db,file_id,process_id) if r['page']==page), None),
            "jobs": [read_job(job) for job in jobs]}


def plan(db, batch_id, file_id, process_id, page):
    file, preview, image, text = page_source(db, batch_id, file_id, process_id, page)
    batch = service.get_batch(db, batch_id)
    intake = db.get(IntakeSession, batch.intake_id) if batch.intake_id else None
    course_id = intake.course_id if intake else None
    route = resolve_routing_snapshot(db, ["materials.vision"],
        scope_type="course" if course_id else "global", scope_id=str(course_id) if course_id else None)["routes"]["materials.vision"]
    digest = sha256(json.dumps([batch_id, file_id, process_id, page, file.sha256, sha256(image).hexdigest(),
                               text, route["config_fingerprint"], PROMPT_VERSION], ensure_ascii=False).encode()).hexdigest()
    cached = db.scalar(select(PageRecognition).where(PageRecognition.input_hash == digest)
        .order_by(PageRecognition.created_at.desc()).limit(1))
    if cached and (cached.status not in {"queued", "running", "ready"} or cached.review == "rejected"):
        cached = None
    public = {"plan_hash": digest, "page": page, "provider_name": route["provider_name"], "model": route["model"],
              "base_url": route["base_url"], "image_bytes": len(image), "text_characters": len(text),
              "maximum_calls": 0 if cached else 1, "existing_job_id": cached.id if cached else None}
    return public, route, preview, image, text


def begin(db, batch_id, file_id, process_id, page, data: RecognitionStart):
    service.get_batch(db, batch_id, lock=True)
    existing = db.get(PageRecognition, str(data.request_id))
    if existing:
        if (existing.batch_id, existing.file_id, existing.process_id, existing.page, existing.input_hash) != (batch_id,file_id,process_id,page,data.plan_hash):
            raise HTTPException(409, "该请求标识已用于另一份识别任务。")
        return read_job(existing)
    public, route, preview, image, text = plan(db, batch_id, file_id, process_id, page)
    if public["plan_hash"] != data.plan_hash:
        raise HTTPException(409, "页面或模型配置已变化，请重新核对发送范围。")
    if public["existing_job_id"]:
        return read_job(db.get(PageRecognition, public["existing_job_id"]))
    job = PageRecognition(id=str(data.request_id), batch_id=batch_id, file_id=file_id, process_id=process_id,
                          page=page, input_hash=data.plan_hash, preview=preview, image_hash=sha256(image).hexdigest(),
                          text=text, route_json=route)
    db.add(job); db.commit()
    return read_job(job)


def scoped_job(db, batch_id, file_id, job_id):
    service.get_file(db, batch_id, file_id)
    job = db.get(PageRecognition, job_id)
    if not job or job.batch_id != batch_id or job.file_id != file_id:
        raise HTTPException(404, "当前资料中没有这项识别任务。")
    return job


def review(db, batch_id, file_id, job_id, data: RecognitionReview):
    service.get_batch(db, batch_id, lock=True)
    job = scoped_job(db, batch_id, file_id, job_id)
    if job.status != "ready" or job.revision != data.expected_revision:
        raise HTTPException(409, "结果未就绪或核对状态已变化，请刷新。")
    job.review, job.review_note = data.decision, data.note.strip()
    job.revision += 1
    db.commit()
    return read_job(job)


def recover(bind):
    with Session(bind) as db:
        db.execute(update(PageRecognition).where(PageRecognition.status == "running").values(
            status="interrupted", error="服务在调用期间中断，结果未知；不会自动再次计费。可核对范围后手动重试。"))
        db.commit()


def run(job_id, bind):
    with Session(bind) as db:
        claimed = db.execute(update(PageRecognition).where(PageRecognition.id == job_id,
                             PageRecognition.status == "queued").values(status="running"))
        db.commit()
        if not claimed.rowcount:
            return
        job = db.get(PageRecognition, job_id)
        route, text, image_hash = job.route_json, job.text, job.image_hash
        file_id, process_id, preview = job.file_id, job.process_id, job.preview
    try:
        path = storage.process_dir(file_id, process_id) / preview
        if not path.is_file() or path.is_symlink() or path.stat().st_size > 8 * 1024 * 1024:
            raise ValueError("missing_image")
        image = path.read_bytes()
        if sha256(image).hexdigest() != image_hash:
            raise ValueError("image_changed")
        result = RecognizedPage.model_validate(recognize(route, image, text)).model_dump()
        status, error = "ready", None
    except Exception:
        # 不保存/回显供应商原始异常，避免泄露密钥和资料。
        status, result, error = "failed", None, "本页识别未完成：可能是接口不兼容、超时、输出不完整或原页变化。原文未修改；不会自动重试，可重新核对后再试。"
    with Session(bind) as db:
        job = db.get(PageRecognition, job_id)
        if job.status == "running":
            job.status, job.result_json, job.error = status, result, error
            db.commit()
