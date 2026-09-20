from copy import deepcopy
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.courses import service as courses
from backend.courses.models import Chapter, Point, Section
from backend.versions import service
from backend.versions.models import DirectoryDraft


def create_draft(db: Session, course_id: int) -> DirectoryDraft:
    course = courses.get_course(db, course_id, lock=True)
    outline_id = getattr(course, "outline_version_id", None)
    if outline_id is None:
        raise HTTPException(409, "请先确认课程目录，再创建局部修改草稿。")
    draft = DirectoryDraft(
        id=str(uuid4()), course_id=course_id, base_version_id=outline_id
    )
    db.add(draft)
    # 人工建立草稿不调用模型；后续 AI 操作开始时再冻结用户选好的草稿级路由。
    db.commit()
    return draft


def get_draft(db: Session, course_id: int, draft_id: str, *, lock=False):
    if lock:
        courses.get_course(db, course_id, lock=True)
    query = select(DirectoryDraft).where(DirectoryDraft.id == draft_id, DirectoryDraft.course_id == course_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    draft = db.scalar(query)
    if draft is None:
        raise HTTPException(404, "这门课程没有该草稿。")
    return draft


def append_chapter(db: Session, course_id: int, draft_id: str, expected_revision: int, chapter: dict):
    draft = get_draft(db, course_id, draft_id, lock=True)
    if draft.status != "editing" or draft.revision != expected_revision:
        raise HTTPException(409, "草稿已被修改或发布，请重新读取后确认。")
    draft.additions_json = [*draft.additions_json, deepcopy(chapter)]
    draft.revision += 1
    db.commit()
    return draft


def publish(db: Session, course_id: int, draft_id: str, expected_revision: int):
    draft = get_draft(db, course_id, draft_id, lock=True)
    # 同一次发布重试返回既有结果，不因网络重试再次生成版本。
    if draft.status == "published":
        if draft.revision != expected_revision:
            raise HTTPException(409, "发布请求不是同一次草稿修订。")
        return draft
    if draft.status != "editing" or draft.revision != expected_revision:
        raise HTTPException(409, "草稿已经变化，请重新确认。")
    if service.selected_id(db, course_id) != draft.base_version_id:
        raise HTTPException(409, "课程已选择另一目录版本；草稿仍保留，请核对基线后再发布。")
    if not draft.additions_json:
        raise HTTPException(422, "草稿没有新增内容，无需发布空版本。")
    course = service.as_view(service.get_manifest(db, course_id, draft.base_version_id))
    for addition in draft.additions_json:
        chapter = Chapter(course_id=course_id, name=addition["name"], position=len(course.chapters), sections=[
            Section(name=section["name"], position=i, points=[
                Point(name=point["name"], intro=point["intro"], position=j)
                for j, point in enumerate(section["points"])
            ]) for i, section in enumerate(addition["sections"])
        ])
        db.add(chapter)
        db.flush()
        course.chapters.append(chapter)
    version = service.new_version(
        db,
        course,
        base_id=draft.base_version_id,
        reason="用户确认新增章节",
        routing_snapshot=draft.routing_snapshot_json,
    )
    from backend.versions.expansion import extended_brief
    service.get_manifest(db, course_id, version.id).brief_json = extended_brief(db, draft)
    service.choose(db, course_id, version.id)
    draft.status = "published"
    draft.published_version_id = version.id
    db.commit()
    return draft
