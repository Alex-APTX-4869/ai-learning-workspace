import json
from contextvars import ContextVar

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.ai.client import generate_json_messages as _client_generate_json_messages
from backend.ai.prompts import outline_messages, points_messages
from backend.ai.schemas import Chapter, ChapterPointsRequest, CourseByAI, CourseRequest
from backend.courses import service as courses
from backend.courses.schemas import CourseRead
from backend.intake.service import get_confirmed_brief
from backend.providers.routing import resolve_routing_snapshot


# 保留 generate_json_messages 这个窄测试/替换边界的三参数接口；真实客户端
# 所需的职责与快照用 ContextVar 在当前请求线程内传递，不会串到并发请求。
_MODEL_CALL_CONTEXT: ContextVar[tuple[str, dict | None] | None] = ContextVar(
    "ai_service_model_call_context", default=None
)
_SAVED_WORKFLOW_SNAPSHOT: ContextVar[dict | None] = ContextVar(
    "ai_service_saved_workflow_snapshot", default=None
)


def generate_json_messages(system_prompt: str, user_payload: str, schema):
    context = _MODEL_CALL_CONTEXT.get()
    if context is None:
        return _client_generate_json_messages(system_prompt, user_payload, schema)
    role, snapshot = context
    return _client_generate_json_messages(
        system_prompt,
        user_payload,
        schema,
        role=role,
        snapshot=snapshot,
    )


def _generate_for_role(
    system_prompt: str,
    user_payload: str,
    schema,
    *,
    role: str,
    routing_snapshot: dict | None,
):
    token = _MODEL_CALL_CONTEXT.set((role, routing_snapshot))
    try:
        return generate_json_messages(system_prompt, user_payload, schema)
    finally:
        _MODEL_CALL_CONTEXT.reset(token)


def generate_outline(
    request: CourseRequest, *, routing_snapshot: dict | None = None
) -> CourseByAI:
    system, human = outline_messages(request)
    return _generate_for_role(
        system,
        human,
        CourseByAI,
        role="outline.generate",
        routing_snapshot=(
            routing_snapshot
            if routing_snapshot is not None
            else _SAVED_WORKFLOW_SNAPSHOT.get()
        ),
    )


def generate_points(
    request: ChapterPointsRequest, *, routing_snapshot: dict | None = None
) -> Chapter:
    system, human = points_messages(request)
    result = _generate_for_role(
        system,
        human,
        Chapter,
        role="points.generate",
        routing_snapshot=(
            routing_snapshot
            if routing_snapshot is not None
            else _SAVED_WORKFLOW_SNAPSHOT.get()
        ),
    )
    if (result.name != request.chapter.name
            or [s.name for s in result.sections] != [s.name for s in request.chapter.sections]
            or any(not s.points for s in result.sections)):
        raise HTTPException(502, "模型修改了原目录或遗漏了知识点，本次未保存，请重试。")
    return result


def generate_saved_outline(course_id: int, db: Session):
    course = courses.get_course(db, course_id)
    if course.chapters:
        return course
    request = CourseRequest(
        topic=course.name,
        intro=course.intro,
        brief=get_confirmed_brief(db, course.id),
    )
    routing_snapshot = resolve_routing_snapshot(
        db,
        ("outline.generate",),
        scope_type="course",
        scope_id=str(course.id),
    )
    # 等待模型期间释放事务，不长期占用数据库锁。
    db.rollback()
    token = _SAVED_WORKFLOW_SNAPSHOT.set(routing_snapshot)
    try:
        # 保持高层生成函数的一参数替换边界，便于测试和未来注入不同实现。
        result = generate_outline(request)
    finally:
        _SAVED_WORKFLOW_SNAPSHOT.reset(token)
    course = courses.get_course(db, course_id, lock=True)
    if (course.name, course.intro) != (request.topic, request.intro):
        raise HTTPException(409, "生成期间课程信息已修改，请使用新信息重新生成。")
    return courses.save_outline(
        db, course, result, routing_snapshot=routing_snapshot
    )


def generate_saved_points(course_id: int, chapter_id: int, db: Session, *,
                          outline_version_id: int | None = None):
    course = courses.get_course(db, course_id, outline_version_id=outline_version_id)
    chapter = courses.find_chapter(course, chapter_id)
    if all(section.points for section in chapter.sections):
        return course
    snapshot = CourseRead.model_validate(course)
    confirmed = get_confirmed_brief(db, course.id)
    version_brief = getattr(course, 'brief_json', None)
    if confirmed and version_brief:
        confirmed = confirmed.model_copy(update=version_brief)
    # 当前阶段传入目录及知识点简介；完整正文不进入这次请求。
    context = {
        "name": snapshot.name,
        "material_basis": (version_brief or {}).get('material_basis'),
        "chapters": [{"name": c.name, "sections": [
            {"name": s.name, "points": [{"name": p.name, "intro": p.intro} for p in s.points]}
            for s in c.sections
        ]} for c in snapshot.chapters],
    }
    request = ChapterPointsRequest(
        course=CourseRequest(
            topic=course.name,
            intro=course.intro,
            brief=confirmed,
        ),
        chapter=Chapter(name=chapter.name, sections=[{"name": s.name} for s in chapter.sections]),
        existing_point_names=[p.name for c in course.chapters for s in c.sections for p in s.points],
        course_context=json.dumps(context, ensure_ascii=False),
    )
    routing_snapshot = resolve_routing_snapshot(
        db,
        ("points.generate",),
        scope_type="course",
        scope_id=str(course.id),
    )
    db.rollback()
    token = _SAVED_WORKFLOW_SNAPSHOT.set(routing_snapshot)
    try:
        result = generate_points(request)
    finally:
        _SAVED_WORKFLOW_SNAPSHOT.reset(token)
    from backend.versions import service as versions
    fixed_outline_id = getattr(course, "outline_version_id", None)
    course = courses.get_course(db, course_id, lock=True, outline_version_id=fixed_outline_id)
    if fixed_outline_id is not None and versions.selected_id(db, course_id) != fixed_outline_id:
        raise HTTPException(409, "生成期间当前目录版本已切换；本次结果未发布，请在原版本重试。")
    chapter = courses.find_chapter(course, chapter_id)
    if ((course.name, course.intro) != (request.course.topic, request.course.intro)
            or chapter.name != request.chapter.name
            or [s.name for s in chapter.sections] != [s.name for s in request.chapter.sections]):
        raise HTTPException(409, "生成期间课程目录已修改，请重试。")
    return courses.save_points(
        db, course, chapter, result, routing_snapshot=routing_snapshot
    )
