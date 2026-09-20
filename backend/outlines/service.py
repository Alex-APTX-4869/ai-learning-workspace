from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from contextvars import ContextVar

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.ai.client import stream_text_messages as _client_stream_text_messages
from backend.ai.schemas import CourseByAI
from backend.courses import service as courses
from backend.courses.models import Chapter as SavedChapter
from backend.courses.models import Course, Section as SavedSection
from backend.intake.service import get_confirmed_brief
from backend.outlines.models import CourseOutlineSelection, OutlineVersion
from backend.outlines.prompts import outline_stream_messages
from backend.outlines.schemas import OutlineGenerationRequest, OutlineVersionRead
from backend.providers.routing import resolve_routing_snapshot
from backend.providers.schemas import RoutingSnapshot
from backend.versions import service as versions
from backend.outlines.grouping import chapter_key


_STREAM_ROUTING_SNAPSHOT: ContextVar[dict | None] = ContextVar(
    "outline_stream_routing_snapshot", default=None
)


def stream_text_messages(system_prompt: str, user_payload: str):
    """保留两参数的流适配边界，内部仍把冻结路由显式交给 AI 客户端。"""
    return _client_stream_text_messages(
        system_prompt,
        user_payload,
        role="outline.generate",
        snapshot=_STREAM_ROUTING_SNAPSHOT.get(),
    )


def _version_read(
    version: OutlineVersion, selected_version_id: int | None
) -> OutlineVersionRead:
    return OutlineVersionRead(
        id=version.id,
        course_id=version.course_id,
        version_number=version.version_number,
        name=version.name,
        outline=CourseByAI.model_validate(version.outline_json),
        additional_requirements=version.additional_requirements,
        reference_version_id=version.reference_version_id,
        created_at=version.created_at,
        selected=version.id == selected_version_id,
    )


def _selected_id(db: Session, course_id: int) -> int | None:
    return db.scalar(
        select(CourseOutlineSelection.version_id).where(
            CourseOutlineSelection.course_id == course_id
        )
    )


def get_version(db: Session, course_id: int, version_id: int) -> OutlineVersion:
    version = db.scalar(
        select(OutlineVersion).where(
            OutlineVersion.id == version_id,
            OutlineVersion.course_id == course_id,
        )
    )
    if version is None:
        raise HTTPException(404, "这门课程中没有找到该大纲版本。")
    return version


def list_versions(db: Session, course_id: int) -> list[OutlineVersionRead]:
    course = courses.get_course(db, course_id, lock=True)
    _ensure_legacy_version(db, course)
    selected_id = _selected_id(db, course_id)
    versions = db.scalars(
        select(OutlineVersion)
        .where(OutlineVersion.course_id == course_id)
        .order_by(OutlineVersion.version_number.desc())
    ).all()
    return [_version_read(item, selected_id) for item in versions]


def get_selected_version(db: Session, course_id: int) -> OutlineVersionRead:
    course = courses.get_course(db, course_id, lock=True)
    _ensure_legacy_version(db, course)
    version_id = _selected_id(db, course_id)
    if version_id is None:
        raise HTTPException(404, "这门课程尚未选择大纲版本。")
    return _version_read(get_version(db, course_id, version_id), version_id)


def _has_learning_content(course: Course) -> bool:
    """目录名称可安全替换；知识点或讲义一旦存在就绝不隐式删除。"""
    return any(
        section.content_markdown is not None or bool(section.points)
        for chapter in course.chapters
        for section in chapter.sections
    )


def _snapshot_course_outline(course: Course) -> CourseByAI:
    return CourseByAI.model_validate(
        {
            "name": course.name,
            "chapters": [
                {
                    "name": chapter.name,
                    "sections": [
                        {"name": section.name} for section in chapter.sections
                    ],
                }
                for chapter in course.chapters
            ],
        }
    )


def select_version(
    db: Session, course_id: int, version_id: int
) -> OutlineVersionRead:
    course = courses.get_course(db, course_id, lock=True)
    _ensure_legacy_version(db, course)
    courses.get_course(db, course_id, lock=True)
    version = get_version(db, course_id, version_id)
    selection = db.get(CourseOutlineSelection, course_id)
    # 即使这个版本已经被选中，也必须先补齐旧数据可能缺失的 manifest。
    versions.materialize_snapshot(db, version)
    if selection is not None and selection.version_id == version_id:
        db.commit()
        return _version_read(version, version_id)
    versions.choose(db, course_id, version_id)
    db.commit()
    return _version_read(version, version_id)


def _generation_context(
    db: Session, course_id: int, request: OutlineGenerationRequest
) -> tuple[object, dict, str, str, dict | None, dict]:
    course = courses.get_course(db, course_id)
    _ensure_legacy_version(db, course)
    course = courses.get_course(db, course_id)
    brief = get_confirmed_brief(db, course_id)
    reference = None
    if request.reference_version_id is not None:
        reference_version = get_version(db, course_id, request.reference_version_id)
        reference = reference_version.outline_json
    brief_payload = brief.model_dump(mode="json") if brief else None
    context = {
        "current_course": {"name": course.name, "intro": course.intro},
        # 旧课程没有确认档案时仍明确传入 CourseBrief=null，并以当前课程信息回退。
        "course_brief": brief_payload,
        "additional_requirements": request.additional_requirements,
        "reference_outline": reference,
    }
    # stream_new_version 返回的是惰性迭代器；路由必须在迭代器建立前解析，
    # 否则用户改设置的时点会影响尚未开始消费的同一次请求。
    routing_snapshot = resolve_routing_snapshot(
        db,
        ("outline.generate",),
        scope_type="course",
        scope_id=str(course_id),
    )
    bind = db.get_bind()
    name, intro = course.name, course.intro
    db.rollback()
    return bind, context, name, intro, brief_payload, routing_snapshot


def _ensure_legacy_version(db: Session, course: Course) -> None:
    """旧课程第一次打开版本面板时只建快照，不改原章节、ID 或学习内容。"""
    raw = db.get(Course, course.id)
    if versions.ensure_legacy(db, raw) is not None:
        db.commit()


def _save_version(
    *,
    bind,
    course_id: int,
    expected_name: str,
    expected_intro: str,
    expected_brief: dict | None,
    routing_snapshot: dict,
    request: OutlineGenerationRequest,
    outline: CourseByAI,
) -> OutlineVersionRead:
    with Session(bind) as db:
        course = courses.get_course(db, course_id, lock=True)
        if (course.name, course.intro) != (expected_name, expected_intro):
            raise HTTPException(
                409, "生成期间课程信息已经修改，本次大纲没有保存。"
            )
        current_brief = get_confirmed_brief(db, course_id)
        current_brief_payload = (
            current_brief.model_dump(mode="json") if current_brief else None
        )
        if current_brief_payload != expected_brief:
            raise HTTPException(
                409, "生成期间课程需求档案已经修改，本次大纲没有保存。"
            )
        if request.reference_version_id is not None:
            get_version(db, course_id, request.reference_version_id)
        latest = db.scalar(
            select(func.max(OutlineVersion.version_number)).where(
                OutlineVersion.course_id == course_id
            )
        )
        selection = db.get(CourseOutlineSelection, course_id)
        version = OutlineVersion(
            course_id=course_id,
            version_number=(latest or 0) + 1,
            name=outline.name,
            outline_json=outline.model_dump(mode="json"),
            additional_requirements=request.additional_requirements,
            reference_version_id=request.reference_version_id,
            routing_snapshot_json=RoutingSnapshot.model_validate(
                routing_snapshot
            ).model_dump(mode="json"),
        )
        db.add(version)
        db.flush()
        tree = versions.create_outline_tree(db, course_id, course.name, course.intro, outline)
        versions.capture(db, version, tree)
        if selection is None:
            versions.choose(db, course_id, version.id)
            selected_id = version.id
        else:
            selected_id = selection.version_id
        db.commit()
        db.refresh(version)
        return _version_read(version, selected_id)


def _event(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"


def _consume_line(line: str, state: dict) -> list[dict]:
    line = line.strip()
    if not line or line.startswith("```"):
        return []
    value = json.loads(line)
    event_type = value.get("type")
    if event_type == "course":
        if state["name"] is not None or state["chapters"] or state["done"]:
            raise ValueError("课程名称事件位置错误")
        name = value.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("课程名称为空")
        state["name"] = name.strip()
        return []
    if event_type == "chapter":
        if state["name"] is None or state["done"]:
            raise ValueError("章节事件位置错误")
        name = value.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("章节名称为空")
        key = chapter_key(name)
        previous = next((i for i, c in enumerate(state['chapters']) if key and chapter_key(c['name']) == key), None)
        if previous is not None:
            state['current_chapter'] = previous
            state['chapters'][previous]['name'] = f'第{key}章'
            return [{'type': 'chapter', 'chapter': {'index': previous, 'name': f'第{key}章'}}]
        chapter = {"name": name.strip(), "sections": []}
        state["chapters"].append(chapter)
        state['current_chapter'] = len(state['chapters']) - 1
        return [
            {
                "type": "chapter",
                "chapter": {
                    "index": len(state["chapters"]) - 1,
                    "name": chapter["name"],
                },
            }
        ]
    if event_type == "section":
        if not state["chapters"] or state["done"]:
            raise ValueError("小节事件位置错误")
        name = value.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("小节名称为空")
        current = state.get('current_chapter', len(state['chapters']) - 1)
        sections = state["chapters"][current]["sections"]
        section = {"name": name.strip()}
        sections.append(section)
        return [
            {
                "type": "section",
                "section": {
                    "chapter_index": current,
                    "index": len(sections) - 1,
                    "name": section["name"],
                },
            }
        ]
    if event_type == "done":
        if state["done"]:
            raise ValueError("重复完成事件")
        state["done"] = True
        return []
    raise ValueError("未知大纲事件")


def stream_new_version(
    db: Session, course_id: int, request: OutlineGenerationRequest
) -> Iterator[str]:
    (
        bind,
        context,
        expected_name,
        expected_intro,
        expected_brief,
        routing_snapshot,
    ) = _generation_context(db, course_id, request)
    system, human = outline_stream_messages(context)

    def generate() -> Iterator[str]:
        yield _event({"type": "start"})
        state = {"name": None, "chapters": [], "done": False}
        buffer = ""
        try:
            token = _STREAM_ROUTING_SNAPSHOT.set(routing_snapshot)
            try:
                chunks = stream_text_messages(system, human)
            finally:
                _STREAM_ROUTING_SNAPSHOT.reset(token)
            for chunk in chunks:
                buffer += chunk
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    for event in _consume_line(line, state):
                        yield _event(event)
            if buffer.strip():
                for event in _consume_line(buffer, state):
                    yield _event(event)
            if not state["done"]:
                raise ValueError("模型没有发出完成事件")
            outline = CourseByAI.model_validate(
                {"name": state["name"], "chapters": state["chapters"]}
            )
            version = _save_version(
                bind=bind,
                course_id=course_id,
                expected_name=expected_name,
                expected_intro=expected_intro,
                expected_brief=expected_brief,
                routing_snapshot=routing_snapshot,
                request=request,
                outline=outline,
            )
            yield _event(
                {"type": "completed", "version": version.model_dump(mode="json")}
            )
        except HTTPException as error:
            yield _event({"type": "error", "detail": str(error.detail)})
        except (json.JSONDecodeError, ValidationError, ValueError):
            yield _event(
                {
                    "type": "error",
                    "detail": "模型返回的大纲流格式不完整，本次没有保存。",
                }
            )
        except SQLAlchemyError:
            logging.getLogger(__name__).error(
                "Outline stream database operation failed"
            )
            yield _event(
                {"type": "error", "detail": "数据库暂时不可用，本次大纲没有保存。"}
            )
        except Exception as error:
            # 流开始后 HTTP 状态码已无法更改，因此用最后一个脱敏事件告知前端。
            logging.getLogger(__name__).error(
                "Outline stream failed: %s", type(error).__name__
            )
            yield _event(
                {"type": "error", "detail": "AI 生成失败，本次大纲没有保存。"}
            )

    return generate()
