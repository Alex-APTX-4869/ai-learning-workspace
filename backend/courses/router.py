from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.courses import service
from backend.courses.schemas import CourseCreate, CourseRead, CourseSummary
from backend.database import get_db
from backend.intake.schemas import CourseBrief

router = APIRouter(prefix="/courses", tags=["课程"])
Database = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[CourseSummary])
def list_courses(db: Database):
    return service.list_courses(db)


@router.post("", response_model=CourseRead, status_code=201)
def create_course(data: CourseCreate, db: Database):
    return service.create_course(db, data)


@router.get("/{course_id}", response_model=CourseRead)
def get_course(course_id: int, db: Database):
    return service.get_course(db, course_id)


@router.get("/{course_id}/brief", response_model=CourseBrief | None)
def get_course_brief(course_id: int, db: Database,
                     outline_version_id: int | None = Query(default=None, ge=1)):
    # 延迟导入避免 courses/intake 的模块加载相互依赖。
    from backend.intake.service import get_confirmed_brief

    course = service.get_course(db, course_id, outline_version_id=outline_version_id)
    if outline_version_id is not None:
        return CourseBrief.model_validate(course.brief_json) if course.brief_json else None
    return get_confirmed_brief(db, course_id)


@router.patch("/{course_id}", response_model=CourseRead)
def update_course(course_id: int, data: CourseCreate, db: Database):
    return service.update_course(db, course_id, data)
