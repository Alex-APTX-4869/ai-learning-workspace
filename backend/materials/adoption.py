"""草稿选择与不可变课程依据分离；不使用最新识别结果替换旧版本。"""
from hashlib import sha256
import json
from fastapi import HTTPException
from sqlalchemy import select
from backend.materials.vision_models import PageAdoption, PageRecognition
from backend.materials.vision_schemas import RecognizedPage


def digest(result):
    return sha256(json.dumps(result, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def selected_pages(report, annotations):
    return {p for p in range(1, (report.get('page_count') or 0) + 1)
            if any(a['page_start'] is None or a['page_start'] <= p <= a['page_end'] for a in annotations)}


def references(db, file_id, process_id):
    return [{'page':r.page, 'recognition_id':r.recognition_id,
             'recognition_revision':r.recognition_revision, 'result_hash':r.result_hash}
            for r in db.scalars(select(PageAdoption).where(PageAdoption.file_id == file_id,
                PageAdoption.process_id == process_id).order_by(PageAdoption.page))]


def checked_job(db, batch_id, file_id, process_id, ref, *, current=False):
    job = db.get(PageRecognition, ref['recognition_id'])
    if (not job or (job.batch_id, job.file_id, job.process_id, job.page) !=
        (batch_id, file_id, process_id, ref['page']) or job.status != 'ready'
        or digest(job.result_json) != ref['result_hash']):
        raise HTTPException(409, '已采用的识别修订无法校验，已停止使用；请重新核对资料。')
    if current and (job.review != 'accepted' or job.revision != ref['recognition_revision']):
        raise HTTPException(409, '已采用页面的核对状态已变化，请重新核对并采用，或取消采用。')
    return job


def select_page(db, batch_id, file_id, job_id, data):
    from backend.materials import service, vision_service
    batch = service.get_batch(db, batch_id, lock=True)
    if batch.status != 'editing' or batch.intake_id:
        raise HTTPException(409, '资料范围已固定，不能加入旧课程；请使用新的资料草稿。')
    file = service.get_file(db, batch_id, file_id)
    if file.revision != data.expected_file_revision:
        raise HTTPException(409, '文件标注或采用记录已变化，请刷新后重试。')
    job = vision_service.scoped_job(db, batch_id, file_id, job_id)
    row = db.get(PageAdoption, (file_id, job.page))
    if data.selected:
        process = service.latest_process(db, file_id)
        if not process or process.id != job.process_id or not file.included:
            raise HTTPException(409, '只能采用当前解析版本中已纳入资料的页面。')
        if job.page not in selected_pages(process.report_json, file.annotations_json):
            raise HTTPException(409, '本页不在已标注的范围内，请先调整页段标注。')
        if job.status != 'ready' or job.review != 'accepted' or job.revision != data.expected_recognition_revision:
            raise HTTPException(409, '请先核对通过当前识别结果，再采用这一修订。')
        _, _, image, _ = vision_service.page_source(db,batch_id,file_id,job.process_id,job.page)
        if sha256(image).hexdigest() != job.image_hash:
            raise HTTPException(409, '识别后的原页图片已变化，请重新识别和核对。')
        result = RecognizedPage.model_validate(job.result_json)
        if not result.blocks or result.issues or any(b.uncertain or not b.content.strip() for b in result.blocks):
            raise HTTPException(409, '本页仍有存疑或不完整内容，暂不能完整采用；请重新识别或限定为可用文字。')
        if row is None:
            row = PageAdoption(file_id=file_id, page=job.page)
            db.add(row)
        row.process_id, row.recognition_id = job.process_id, job.id
        row.recognition_revision, row.result_hash = job.revision, digest(job.result_json)
    elif row:
        if row.recognition_id != job.id:
            raise HTTPException(409, '当前采用的是另一份修订，请刷新后操作。')
        db.delete(row)
    file.revision += 1
    batch.revision += 1
    db.commit()
    return service.read_batch(db, batch_id)


def effective_report(db, batch_id, file, report, *, current=False):
    refs = file.get('vision_pages', [])
    if not refs:
        return report
    pages = [r['page'] for r in refs]
    if len(set(pages)) != len(pages) or not set(pages) <= selected_pages(report, file['annotations']):
        raise HTTPException(409, '采用页重复或超出确认范围，已停止使用。')
    elements = [e for e in report['elements'] if e['locator'].get('page') not in pages]
    for ref in refs:
        job = checked_job(db, batch_id, file['file_id'], file['process_id'], ref, current=current)
        for index, block in enumerate(RecognizedPage.model_validate(job.result_json).blocks):
            elements.append({'id':f'vision:{job.id}:{index}', 'kind':block.kind,
                'text':f'【视觉转录，已人工核对；{block.kind}】\n{block.title}\n{block.content}',
                'locator':{'type':'pdf_page','page':job.page,'recognition_id':job.id,
                           'recognition_revision':ref['recognition_revision'],'source_kind':'vision_transcription'},
                'preview':job.preview})
    elements.sort(key=lambda e:e['locator'].get('page') or 0)
    issues = [i for i in report.get('issues', []) if (i.get('locator') or {}).get('page') not in pages]
    return {**report, 'elements':elements, 'issues':issues}
