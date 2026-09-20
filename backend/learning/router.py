from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.learning import service
from backend.learning.schemas import LearningJobRead, PointContentRead
from backend.workflows.content import run_learning_job

router = APIRouter(tags=["学习内容"])
Database = Annotated[Session, Depends(get_db)]


@router.post(
    "/courses/{course_id}/points/{point_id}/content/jobs",
    response_model=LearningJobRead,
    status_code=202,
)
def create_content_job(
    course_id: int,
    point_id: int,
    background_tasks: BackgroundTasks,
    response: Response,
    request: Request,
    db: Database,
    outline_version_id: int | None = Query(default=None, ge=1),
):
    bind = db.get_bind()
    job, created = service.create_or_get_job(db, course_id, point_id, outline_version_id=outline_version_id)
    response.headers["Location"] = f"/learning-jobs/{job.id}"
    if created and request.app.state.inline_jobs:
        background_tasks.add_task(run_learning_job, job.id, bind)
    return job


@router.get("/learning-jobs/{job_id}", response_model=LearningJobRead)
def get_learning_job(job_id: int, db: Database):
    return service.get_job(db, job_id)


@router.post("/learning-jobs/{job_id}/cancel", response_model=LearningJobRead)
def cancel_learning_job(job_id: int, db: Database):
    return service.cancel_job(db, job_id)


@router.post("/learning-jobs/{job_id}/retry", response_model=LearningJobRead)
def retry_learning_job(job_id: int, request: Request, background_tasks: BackgroundTasks, db: Database):
    job = service.retry_job(db, job_id)
    if request.app.state.inline_jobs:
        background_tasks.add_task(run_learning_job, job.id, db.get_bind())
    return job


@router.get(
    "/courses/{course_id}/points/{point_id}/content/jobs/active",
    response_model=LearningJobRead | None,
)
def get_active_learning_job(course_id: int, point_id: int, db: Database,
                            outline_version_id: int | None = Query(default=None, ge=1)):
    return service.get_active_job(db, course_id, point_id, outline_version_id=outline_version_id)


@router.get(
    "/courses/{course_id}/points/{point_id}/content",
    response_model=PointContentRead,
)
def get_point_content(course_id: int, point_id: int, db: Database,
                      outline_version_id: int | None = Query(default=None, ge=1)):
    return service.get_current_content(db, course_id, point_id, outline_version_id=outline_version_id)
