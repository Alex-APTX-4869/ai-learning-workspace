from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.outlines import service
from backend.outlines.schemas import OutlineActivationRead, OutlineGenerationRequest, OutlineVersionRead
from backend.courses import service as courses

router = APIRouter(prefix="/courses/{course_id}/outline-versions", tags=["大纲版本"])
Database = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[OutlineVersionRead])
def list_outline_versions(course_id: int, db: Database):
    return service.list_versions(db, course_id)


@router.get("/selected", response_model=OutlineVersionRead)
def get_selected_outline_version(course_id: int, db: Database):
    return service.get_selected_version(db, course_id)


@router.post("/stream")
def generate_outline_version(
    course_id: int, data: OutlineGenerationRequest, db: Database
):
    return StreamingResponse(
        service.stream_new_version(db, course_id, data),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/{version_id}/select", response_model=OutlineVersionRead)
def select_outline_version(course_id: int, version_id: int, db: Database):
    return service.select_version(db, course_id, version_id)


@router.post("/{version_id}/activate", response_model=OutlineActivationRead)
def activate_outline_version(course_id: int, version_id: int, db: Database):
    version = service.select_version(db, course_id, version_id)
    return {"version": version, "course": courses.get_course(db, course_id, outline_version_id=version_id)}
