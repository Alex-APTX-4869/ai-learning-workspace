from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.courses import service as courses
from backend.courses.models import Chapter, Course, Point, Section
from backend.intake.service import get_confirmed_brief
from backend.learning.models import (
    LearningGenerationJob,
    PointContentSelection,
    PointContentVersion,
)
from backend.learning.schemas import ContentReview, PointContent, PointContentRead
from backend.providers.routing import resolve_routing_snapshot
from backend.versions import service as versions
from backend.versions.models import DirectoryContentSelection


ACTIVE_JOB_STATUSES = ("queued", "planning", "writing", "reviewing", "revising")
BLOCKING_JOB_STATUSES = (*ACTIVE_JOB_STATUSES, "needs_attention")
PROMPT_VERSIONS = {
    "grounding": "v1-frozen-original-excerpts",
    "planner": "v4-prerequisite-bridge",
    "lesson": "v4-concrete-explanation",
    "examples": "v3-concrete-transfer",
    "exercises": "v4-separate-question-types",
    "code_lab": "v3-language-accuracy",
    "reviewer": "v4-comprehension-review",
    "reviser": "v4-repair-explanation",
}
CONTENT_ROLE_KEYS = (
    "content.plan",
    "content.lesson",
    "content.examples",
    "content.exercises",
    "content.code_lab",
    "content.review",
    "content.revise",
)


@dataclass(frozen=True)
class GenerationContext:
    payload: dict
    context_hash: str
    structure_hash: str
    course: Course
    chapter: Chapter
    section: Section
    point: Point
    selected_version_id: int | None


def _digest(value: dict) -> str:
    serialized = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _find_point(
    course: Course, point_id: int
) -> tuple[Chapter, Section, Point]:
    for chapter in course.chapters:
        for section in chapter.sections:
            for point in section.points:
                if point.id == point_id:
                    return chapter, section, point
    raise HTTPException(404, "这门课程中没有找到该知识点。")


def build_generation_context(
    db: Session,
    course_id: int,
    point_id: int,
    *,
    lock: bool = False,
    loaded_course: Course | None = None,
    routing_snapshot: dict | None = None,
) -> GenerationContext:
    course = loaded_course or courses.get_course(db, course_id, lock=lock)
    chapter, section, point = _find_point(course, point_id)
    outline_id = getattr(course, "outline_version_id", None)
    if outline_id is None:
        brief = get_confirmed_brief(db, course_id)
        brief_json = brief.model_dump(mode="json") if brief else None
    else:
        brief_json = course.brief_json

    point_ids = [
        item.id
        for course_chapter in course.chapters
        for course_section in course_chapter.sections
        for item in course_section.points
    ]
    selected_content: dict[int, tuple[dict, str]] = {}
    if point_ids:
        selection_model = DirectoryContentSelection if outline_id is not None else PointContentSelection
        content_id_column = selection_model.content_version_id if outline_id is not None else selection_model.version_id
        rows = db.execute(
            select(
                selection_model.point_id,
                PointContentVersion.content_json,
                PointContentVersion.origin,
            )
            .join(
                PointContentVersion,
                PointContentVersion.id == content_id_column,
            )
            .where(selection_model.point_id.in_(point_ids))
            .where(DirectoryContentSelection.outline_version_id == outline_id if outline_id is not None else True)
        ).all()
        selected_content = {
            row.point_id: (row.content_json, row.origin) for row in rows
        }

    content_summaries = []
    for course_chapter in course.chapters:
        for course_section in course_chapter.sections:
            for item in course_section.points:
                selected = selected_content.get(item.id)
                if selected is not None:
                    structured, origin = selected
                    if origin == "legacy":
                        summary = structured.get("lesson_markdown", "")[:1200]
                        source = "legacy_markdown_excerpt"
                    else:
                        summary = structured.get("summary", "")
                        source = "structured_content"
                elif item.content_markdown:
                    # 旧字段仍参与去重上下文，但不复制成新版本。
                    summary = item.content_markdown[:1200]
                    source = "legacy_markdown_excerpt"
                else:
                    continue
                content_summaries.append(
                    {
                        "point_id": item.id,
                        "point_name": item.name,
                        "summary": summary,
                        "source": source,
                    }
                )

    outline = {
        "course_id": course.id,
        "name": course.name,
        "intro": course.intro,
        "chapters": [
            {
                "id": course_chapter.id,
                "name": course_chapter.name,
                "position": course_chapter.position,
                "sections": [
                    {
                        "id": course_section.id,
                        "name": course_section.name,
                        "position": course_section.position,
                        "points": [
                            {
                                "id": item.id,
                                "name": item.name,
                                "intro": item.intro,
                                "position": item.position,
                            }
                            for item in course_section.points
                        ],
                    }
                    for course_section in course_chapter.sections
                ],
            }
            for course_chapter in course.chapters
        ],
    }
    same_section_points = [
        {
            "id": item.id,
            "name": item.name,
            "intro": item.intro,
            "position": item.position,
        }
        for item in section.points
    ]
    structure = {
        "current_course": {"name": course.name, "intro": course.intro},
        "course_brief": brief_json,
        "course_outline": outline,
        "target_section": {
            "chapter_id": chapter.id,
            "chapter_name": chapter.name,
            "section_id": section.id,
            "section_name": section.name,
            "points": same_section_points,
        },
        "prompt_versions": PROMPT_VERSIONS,
    }
    payload = {
        **structure,
        "target_point": {
            "id": point.id,
            "name": point.name,
            "intro": point.intro,
            "position": point.position,
        },
        "existing_content_summaries": content_summaries,
    }
    if outline_id is not None:
        payload["outline_version_id"] = outline_id
    planner_fingerprint = None
    if routing_snapshot is not None:
        planner_route = routing_snapshot.get("routes", {}).get("content.plan")
        if not isinstance(planner_route, dict) or not planner_route.get(
            "config_fingerprint"
        ):
            raise HTTPException(409, "内容任务的教学规划模型快照不完整。")
        planner_fingerprint = planner_route["config_fingerprint"]
    structure_digest_input = (
        structure
        if planner_fingerprint is None
        else {
            "teaching_structure": structure,
            "planner_route_fingerprint": planner_fingerprint,
        }
    )
    return GenerationContext(
        payload=payload,
        context_hash=_digest(payload),
        # 规划模型发生变化时重新规划本小节，避免静默复用另一模型的分工。
        # 指纹只参与内部哈希，不会被放进发送给模型的课程资料。
        structure_hash=_digest(structure_digest_input),
        course=course,
        chapter=chapter,
        section=section,
        point=point,
        selected_version_id=versions.content_selection_id(db, point.id, outline_id),
    )


def planning_context(payload: dict) -> dict:
    """规划整个小节，不让首个触发任务的知识点获得特殊权重。"""
    return {
        key: value
        for key, value in payload.items()
        if key not in ("target_point", "material_evidence")
    }


def create_or_get_job(
    db: Session, course_id: int, point_id: int, *, outline_version_id: int | None = None
) -> tuple[LearningGenerationJob, bool]:
    course = courses.get_course(db, course_id, lock=True, outline_version_id=outline_version_id)
    _, section, _ = _find_point(course, point_id)
    active = db.scalar(
        select(LearningGenerationJob)
        .where(
            LearningGenerationJob.section_id == section.id,
            LearningGenerationJob.outline_version_id == getattr(course, "outline_version_id", None),
            LearningGenerationJob.status.in_(BLOCKING_JOB_STATUSES),
        )
        .with_for_update()
    )
    if active is not None:
        if active.point_id == point_id:
            return active, False
        raise HTTPException(409, "同一小节的另一个知识点正在制作内容。")

    routing_snapshot = resolve_routing_snapshot(
        db,
        CONTENT_ROLE_KEYS,
        scope_type="course",
        scope_id=str(course_id),
    )
    context = build_generation_context(
        db,
        course_id,
        point_id,
        loaded_course=course,
        routing_snapshot=routing_snapshot,
    )

    job = LearningGenerationJob(
        course_id=course_id,
        section_id=context.section.id,
        point_id=point_id,
        outline_version_id=getattr(course, "outline_version_id", None),
        status="queued",
        context_hash=context.context_hash,
        structure_hash=context.structure_hash,
        context_json=context.payload,
        routing_snapshot_json=routing_snapshot,
        expected_selected_version_id=context.selected_version_id,
    )
    db.add(job)
    try:
        db.commit()
    except IntegrityError:
        # PostgreSQL 的 Course 行锁会串行化并发请求；部分测试/轻量数据库
        # 不实现 FOR UPDATE，由部分唯一索引兜底后在这里回读。
        db.rollback()
        active = db.scalar(
            select(LearningGenerationJob).where(
                LearningGenerationJob.section_id == context.section.id,
                LearningGenerationJob.outline_version_id == getattr(course, "outline_version_id", None),
                LearningGenerationJob.status.in_(BLOCKING_JOB_STATUSES),
            )
        )
        if active is None:
            raise
        if active.point_id == point_id:
            return active, False
        raise HTTPException(409, "同一小节的另一个知识点正在制作内容。")
    db.refresh(job)
    return job, True


def recover_interrupted_jobs(bind) -> int:
    """重启后保留检查点；已发出的未知模型调用必须由用户明确重试。"""
    from backend.learning.models import LearningJobStep
    with Session(bind) as db:
        jobs = db.scalars(
            select(LearningGenerationJob).where(
                LearningGenerationJob.status.in_(ACTIVE_JOB_STATUSES)
            )
        ).all()
        recovered = 0
        for job in jobs:
            unknown = db.scalar(select(LearningJobStep.id).where(
                LearningJobStep.job_id == job.id, LearningJobStep.status == "running"
            ))
            if unknown is not None:
                db.query(LearningJobStep).filter(
                    LearningJobStep.job_id == job.id, LearningJobStep.status == "running"
                ).update({LearningJobStep.status: "result_unknown"}, synchronize_session=False)
                job.status = "needs_attention"
                job.error_code = "provider_result_unknown"
                job.error = "服务重启时模型调用可能已经执行。为避免自动重复计费，请确认后再重试。"
            else:
                job.status = "queued"
                job.error_code = None
                job.error = None
            recovered += 1
        if jobs:
            db.commit()
        return recovered


def get_job(db: Session, job_id: int) -> LearningGenerationJob:
    job = db.get(LearningGenerationJob, job_id)
    if job is None:
        raise HTTPException(404, "没有找到这个内容生成任务。")
    return job


def get_active_job(
    db: Session, course_id: int, point_id: int, *, outline_version_id: int | None = None
) -> LearningGenerationJob | None:
    course = courses.get_course(db, course_id, outline_version_id=outline_version_id)
    _find_point(course, point_id)
    return db.scalar(
        select(LearningGenerationJob)
        .where(
            LearningGenerationJob.course_id == course_id,
            LearningGenerationJob.point_id == point_id,
            LearningGenerationJob.outline_version_id == getattr(course, "outline_version_id", None),
            LearningGenerationJob.status.in_(BLOCKING_JOB_STATUSES),
        )
        .order_by(LearningGenerationJob.id.desc())
        .limit(1)
    )


def cancel_job(db: Session, job_id: int) -> LearningGenerationJob:
    peek = db.get(LearningGenerationJob, job_id)
    if peek is None:
        raise HTTPException(404, "没有找到这个内容生成任务。")
    # 与工作流保持 Course -> Job 的锁顺序。
    courses.get_course(db, peek.course_id, lock=True)
    job = db.scalar(
        select(LearningGenerationJob)
        .where(LearningGenerationJob.id == job_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if job is None:
        raise HTTPException(404, "没有找到这个内容生成任务。")
    if job.status in BLOCKING_JOB_STATUSES:
        job.status = "cancelled"
        job.error_code = "cancelled_by_user"
        job.error = "已按你的操作停止本次生成，已有内容保持不变。"
        db.commit()
        db.refresh(job)
    return job


def retry_job(db: Session, job_id: int) -> LearningGenerationJob:
    from backend.learning.models import LearningJobStep
    peek = get_job(db, job_id)
    courses.get_course(db, peek.course_id, lock=True, outline_version_id=peek.outline_version_id)
    job = db.scalar(select(LearningGenerationJob).where(LearningGenerationJob.id == job_id).with_for_update())
    if job.status != "needs_attention":
        raise HTTPException(409, "只有结果不确定的任务需要由你确认重试。")
    # 只重做结果未知的那个步骤，已完成步骤继续复用。
    db.query(LearningJobStep).filter(
        LearningJobStep.job_id == job.id, LearningJobStep.status == "result_unknown"
    ).update({LearningJobStep.status: "retry_authorized", LearningJobStep.output_json: None}, synchronize_session=False)
    job.status = "queued"
    job.error_code = None
    job.error = None
    db.commit()
    db.refresh(job)
    return job


def get_current_content(
    db: Session, course_id: int, point_id: int, *, outline_version_id: int | None = None
) -> PointContentRead:
    course = courses.get_course(db, course_id, lock=True, outline_version_id=outline_version_id)
    _, _, point = _find_point(course, point_id)
    outline_id = getattr(course, "outline_version_id", None)
    selected_content_id = versions.content_selection_id(db, point_id, outline_id)
    if selected_content_id is None:
        if not point.content_markdown:
            raise HTTPException(404, "这个知识点尚未生成详细内容。")
        # 不伪造练习或审查结果：旧正文以 legacy 版本原样可读。
        context = build_generation_context(
            db, course_id, point_id, loaded_course=course
        )
        latest = db.scalar(
            select(func.max(PointContentVersion.version_number)).where(
                PointContentVersion.point_id == point_id
            )
        )
        version = PointContentVersion(
            point_id=point_id,
            plan_id=None,
            version_number=(latest or 0) + 1,
            status="ready",
            origin="legacy",
            content_json=PointContent(
                lesson_markdown=point.content_markdown,
                examples=[],
                exercises=[],
                summary=point.intro,
            ).model_dump(mode="json"),
            review_json=ContentReview(
                approved=False,
                issues=["这是早期保存的正文，尚未经过新内容 Agent 审查。"],
                revision_instructions=[],
            ).model_dump(mode="json"),
            revision_count=0,
            context_hash=context.context_hash,
        )
        db.add(version)
        db.flush()
        versions.select_content(db, point_id, version.id, outline_id)
        db.commit()
    else:
        version = None
    version = version or db.get(PointContentVersion, selected_content_id)
    if version is None or version.point_id != point_id or version.status != "ready":
        raise HTTPException(409, "当前内容版本状态异常，暂时无法阅读。")
    return PointContentRead(
        id=version.id,
        point_id=version.point_id,
        outline_version_id=outline_id,
        version_number=version.version_number,
        origin=version.origin,
        content=PointContent.model_validate(version.content_json),
        review=ContentReview.model_validate(version.review_json),
        created_at=version.created_at,
    )
