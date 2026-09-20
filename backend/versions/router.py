from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from backend.courses.schemas import Intro, Name, CourseRead
from backend.courses import service as courses
from backend.database import get_db
from backend.versions import drafts
from backend.versions import expansion

router = APIRouter(prefix="/courses/{course_id}", tags=["目录修订"])
Database = Annotated[Session, Depends(get_db)]


class DraftPoint(BaseModel):
    name: Name
    intro: Intro


class DraftSection(BaseModel):
    name: Name
    points: list[DraftPoint] = Field(default_factory=list)


class DraftChapter(BaseModel):
    name: Name
    sections: list[DraftSection] = Field(min_length=1)


class DraftOperation(BaseModel):
    expected_revision: int = Field(ge=0)


class AppendChapter(DraftOperation):
    chapter: DraftChapter


class DraftRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    course_id: int
    base_version_id: int
    revision: int
    status: str
    additions_json: list[DraftChapter]
    published_version_id: int | None


@router.get("/outline-versions/{version_id}/course", response_model=CourseRead)
def read_version(course_id: int, version_id: int, db: Database):
    # 锁住课程可避免两个首次读取并发创建两套历史节点。
    course = courses.get_course(
        db, course_id, lock=True, outline_version_id=version_id
    )
    # 精确读取可能为迁移前历史版本懒建 manifest；持久化后下次无需重建。
    db.commit()
    return course


@router.post("/directory-drafts", response_model=DraftRead, status_code=201)
def create_draft(course_id: int, db: Database):
    return drafts.create_draft(db, course_id)


@router.get("/directory-drafts/{draft_id}", response_model=DraftRead)
def read_draft(course_id: int, draft_id: str, db: Database):
    return drafts.get_draft(db, course_id, draft_id)


@router.post("/directory-drafts/{draft_id}/chapters", response_model=DraftRead)
def append_chapter(course_id: int, draft_id: str, data: AppendChapter, db: Database):
    return drafts.append_chapter(db, course_id, draft_id, data.expected_revision, data.chapter.model_dump())


@router.post("/directory-drafts/{draft_id}/publish", response_model=DraftRead)
def publish_draft(course_id: int, draft_id: str, data: DraftOperation, db: Database):
    return drafts.publish(db, course_id, draft_id, data.expected_revision)


@router.post('/directory-drafts/{draft_id}/generate-chapter', response_model=DraftRead)
def generate_chapter(course_id: int, draft_id: str, data: expansion.GenerateChapter, db: Database):
    return expansion.generate(db, course_id, draft_id, data)
