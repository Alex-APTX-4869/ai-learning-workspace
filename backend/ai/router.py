from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.ai import service
from backend.ai.schemas import Chapter, ChapterPointsRequest, CourseByAI, CourseRequest
from backend.courses.schemas import CourseRead
from backend.database import get_db

router = APIRouter(tags=["AI 生成"])
Database = Annotated[Session, Depends(get_db)]


@router.post("/courses/{course_id}/outline", response_model=CourseRead)
def generate_course_outline(course_id: int, db: Database):
    return service.generate_saved_outline(course_id, db)


@router.post("/courses/{course_id}/chapters/{chapter_id}/points", response_model=CourseRead)
def generate_chapter_points(course_id: int, chapter_id: int, db: Database,
                            outline_version_id: int | None = Query(default=None, ge=1)):
    return service.generate_saved_points(course_id, chapter_id, db,
                                         outline_version_id=outline_version_id)


# 保留旧接口，便于对照此前的学习代码。新界面使用上方带保存的接口。
@router.post("/ai/course-outline", response_model=CourseByAI)
def preview_outline(request: CourseRequest):
    return service.generate_outline(request)


@router.post("/ai/chapter-points", response_model=Chapter)
def preview_points(request: ChapterPointsRequest):
    return service.generate_points(request)
