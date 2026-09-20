from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, Path, Request
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.materials import vision_service as service
from backend.materials.vision_schemas import RecognitionStart, RecognitionReview, RecognitionAdopt
from backend.materials.adoption import select_page

router = APIRouter(prefix="/{batch_id}/files/{file_id}")
Database = Annotated[Session, Depends(get_db)]
Page = Annotated[int, Path(ge=1, le=150)]


@router.post('/vision-jobs/{job_id}/adoption')
def adopt(batch_id: UUID, file_id: UUID, job_id: UUID, data: RecognitionAdopt, db: Database):
    return select_page(db, str(batch_id), str(file_id), str(job_id), data)


@router.get("/processes/{process_id}/pages/{page}/vision")
def page_view(batch_id: UUID, file_id: UUID, process_id: UUID, page: Page, db: Database):
    return service.page_view(db, str(batch_id), str(file_id), str(process_id), page)


@router.get("/processes/{process_id}/pages/{page}/vision-plan")
def plan(batch_id: UUID, file_id: UUID, process_id: UUID, page: Page, db: Database):
    return service.plan(db, str(batch_id), str(file_id), str(process_id), page)[0]


@router.post("/processes/{process_id}/pages/{page}/vision", status_code=202)
def begin(batch_id: UUID, file_id: UUID, process_id: UUID, page: Page, data: RecognitionStart, db: Database, request: Request):
    job = service.begin(db, str(batch_id), str(file_id), str(process_id), page, data)
    if request.app.state.inline_jobs:
        service.run(job["id"], db.get_bind())
        db.expire_all()
        job = service.read_job(service.scoped_job(db, str(batch_id), str(file_id), job["id"]))
    return job


@router.get("/vision-jobs/{job_id}")
def read(batch_id: UUID, file_id: UUID, job_id: UUID, db: Database):
    return service.read_job(service.scoped_job(db, str(batch_id), str(file_id), str(job_id)))


@router.patch("/vision-jobs/{job_id}/review")
def review(batch_id: UUID, file_id: UUID, job_id: UUID, data: RecognitionReview, db: Database):
    return service.review(db, str(batch_id), str(file_id), str(job_id), data)
