from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.courses.models import Chapter, Course, Point, Section
from backend.learning.models import PointContentSelection, PointContentVersion
from backend.outlines.models import CourseOutlineSelection, OutlineVersion
from backend.providers.schemas import RoutingSnapshot
from backend.versions.models import DirectoryContentSelection, DirectoryManifest

_USE_CURRENT_BRIEF = object()


def selected_id(db: Session, course_id: int) -> int | None:
    return db.scalar(select(CourseOutlineSelection.version_id).where(CourseOutlineSelection.course_id == course_id))


def _revision(node: dict) -> str:
    return hashlib.sha256(json.dumps(node, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def snapshot_tree(course) -> dict:
    def node(item, children_key=None, children=None):
        result = {"id": item.id, "name": item.name, "position": item.position}
        if hasattr(item, "intro"):
            result["intro"] = item.intro
        if hasattr(item, "content_markdown"):
            result["content_markdown"] = item.content_markdown
        if children_key:
            result[children_key] = children
        # 数据库 ID 是稳定身份；修订指纹包含字段及子节点，不靠标题猜测关联。
        result["revision"] = _revision(result)
        return result

    return {
        "id": course.id, "name": course.name, "intro": course.intro,
        "chapters": [node(chapter, "sections", [
            node(section, "points", [node(point) for point in section.points])
            for section in chapter.sections
        ]) for chapter in course.chapters],
    }


def point_ids(tree: dict) -> set[int]:
    return {point["id"] for chapter in tree["chapters"] for section in chapter["sections"] for point in section["points"]}


def as_view(manifest: DirectoryManifest):
    def convert(value):
        if isinstance(value, dict):
            return SimpleNamespace(**{key: convert(item) for key, item in value.items()})
        if isinstance(value, list):
            return [convert(item) for item in value]
        return value
    view = convert(deepcopy(manifest.tree_json))
    view.outline_version_id = manifest.version_id
    view.brief_json = deepcopy(manifest.brief_json)
    view.directory_origin = manifest.origin
    # 旧 OutlineVersion 没保存 intro；snapshot_only 只能明确回退到当前课程简介。
    view.intro_is_fallback = manifest.origin == "snapshot_only"
    return view


def get_manifest(db: Session, course_id: int, version_id: int) -> DirectoryManifest:
    manifest = db.get(DirectoryManifest, version_id)
    if manifest is None or manifest.course_id != course_id:
        raise HTTPException(404, "这个目录版本尚无可读取的内容树。")
    return manifest


def capture(
    db: Session,
    version: OutlineVersion,
    course,
    *,
    base_id=None,
    origin="generated",
    inherit_legacy=False,
    brief_override=_USE_CURRENT_BRIEF,
):
    existing = db.get(DirectoryManifest, version.id)
    if existing:
        return existing
    from backend.intake.service import get_confirmed_brief
    brief = get_confirmed_brief(db, version.course_id)
    base = get_manifest(db, version.course_id, base_id) if base_id else None
    if brief_override is _USE_CURRENT_BRIEF:
        brief_json = (
            deepcopy(base.brief_json)
            if base
            else (brief.model_dump(mode="json") if brief else None)
        )
    else:
        brief_json = deepcopy(brief_override)
    manifest = DirectoryManifest(
        version_id=version.id, course_id=version.course_id, base_version_id=base_id,
        tree_json=snapshot_tree(course), origin=origin,
        brief_json=brief_json,
    )
    db.add(manifest)
    db.flush()
    ids = point_ids(manifest.tree_json)
    if base:
        selections = db.scalars(select(DirectoryContentSelection).where(DirectoryContentSelection.outline_version_id == base_id)).all()
        pairs = [(row.point_id, row.content_version_id) for row in selections]
    elif inherit_legacy:
        pairs = [(row.point_id, row.version_id) for row in db.scalars(select(PointContentSelection).where(PointContentSelection.point_id.in_(ids))).all()]
    else:
        pairs = []
    for point_id, content_id in pairs:
        if point_id in ids:
            # 继承也必须经过与普通选择相同的归属/状态校验。
            select_content(db, point_id, content_id, version.id)
    db.flush()
    return manifest


def outline_payload(course) -> dict:
    return {"name": course.name, "chapters": [
        {"name": chapter.name, "sections": [{"name": section.name} for section in chapter.sections]}
        for chapter in course.chapters
    ]}


def _validated_routing_snapshot(snapshot: dict | None) -> dict | None:
    """只允许公开路由结构进入持久层，额外字段（含凭据）直接拒绝。"""
    if snapshot is None:
        return None
    return RoutingSnapshot.model_validate(snapshot).model_dump(mode="json")


def new_version(
    db: Session,
    course,
    *,
    base_id=None,
    reason="",
    origin="structure",
    routing_snapshot: dict | None = None,
) -> OutlineVersion:
    latest = db.scalar(select(func.max(OutlineVersion.version_number)).where(OutlineVersion.course_id == course.id)) or 0
    version = OutlineVersion(course_id=course.id, version_number=latest + 1, name=course.name,
                             outline_json=outline_payload(course), additional_requirements=reason,
                             reference_version_id=base_id,
                             routing_snapshot_json=_validated_routing_snapshot(routing_snapshot))
    db.add(version)
    db.flush()
    capture(db, version, course, base_id=base_id, origin=origin, inherit_legacy=origin == "legacy")
    return version


def choose(db: Session, course_id: int, version_id: int):
    get_manifest(db, course_id, version_id)
    selection = db.get(CourseOutlineSelection, course_id)
    if selection is None:
        db.add(CourseOutlineSelection(course_id=course_id, version_id=version_id))
    else:
        selection.version_id = version_id


def ensure_legacy(db: Session, course: Course) -> DirectoryManifest | None:
    """只将真实树归入被证实对应的快照，绝不按同名标题分发旧内容。"""
    selected = selected_id(db, course.id)
    if selected and (manifest := db.get(DirectoryManifest, selected)):
        return manifest
    if not course.chapters:
        return None
    version = db.get(OutlineVersion, selected) if selected else None
    if version and version.outline_json == outline_payload(course):
        return capture(db, version, course, origin="legacy", inherit_legacy=True)
    version = new_version(db, course, reason="保留迁移时的实际目录与学习内容", origin="legacy")
    choose(db, course.id, version.id)
    return db.get(DirectoryManifest, version.id)


def create_outline_tree(db: Session, course_id: int, name: str, intro: str, outline):
    chapters = []
    for i, chapter in enumerate(outline.chapters):
        saved = Chapter(course_id=course_id, name=chapter.name, position=i, sections=[
            Section(name=section.name, position=j) for j, section in enumerate(chapter.sections)
        ])
        db.add(saved)
        chapters.append(saved)
    db.flush()
    return SimpleNamespace(id=course_id, name=name, intro=intro, chapters=chapters)


def materialize_snapshot(db: Session, version: OutlineVersion) -> DirectoryManifest:
    existing = db.get(DirectoryManifest, version.id)
    if existing:
        return existing
    from backend.ai.schemas import CourseByAI
    # 同一历史版本第一次并发读取时，用 course 行串行化；锁后必须再次检查。
    raw = db.scalar(
        select(Course).where(Course.id == version.course_id).with_for_update()
    )
    existing = db.get(DirectoryManifest, version.id)
    if existing:
        return existing
    tree = create_outline_tree(db, raw.id, version.name, raw.intro, CourseByAI.model_validate(version.outline_json))
    # 历史快照没有可证实的点内容，只创建独立空目录，不嫁接其他版本的学习记录。
    # OutlineVersion 也没有冻结历史 brief；None 比冒充当前需求档案更诚实。
    return capture(
        db, version, tree, origin="snapshot_only", brief_override=None
    )


def content_selection_id(db: Session, point_id: int, outline_id: int | None) -> int | None:
    if outline_id is not None:
        row = db.get(DirectoryContentSelection, (outline_id, point_id))
        return row.content_version_id if row else None
    row = db.get(PointContentSelection, point_id)
    return row.version_id if row else None


def select_content(db: Session, point_id: int, content_id: int, outline_id: int | None):
    content = db.get(PointContentVersion, content_id)
    if content is None or content.point_id != point_id or content.status != "ready":
        # 两个独立外键只能证明记录分别存在，不能证明正文属于这个知识点。
        # 在唯一写入口校验归属与发布状态，防止跨知识点挂错正文。
        raise HTTPException(409, "只能选择属于该知识点且已经就绪的内容版本。")
    if outline_id is not None:
        manifest = db.get(DirectoryManifest, outline_id)
        if manifest is None or point_id not in point_ids(manifest.tree_json):
            raise HTTPException(409, "知识点不属于本次内容对应的目录。")
        row = db.get(DirectoryContentSelection, (outline_id, point_id))
        if row:
            row.content_version_id = content_id
        else:
            db.add(DirectoryContentSelection(outline_version_id=outline_id, point_id=point_id, content_version_id=content_id))
    else:
        row = db.get(PointContentSelection, point_id)
        if row:
            row.version_id = content_id
        else:
            db.add(PointContentSelection(point_id=point_id, version_id=content_id))


def save_points_revision(
    db: Session,
    course,
    chapter,
    generated,
    *,
    routing_snapshot: dict | None = None,
):
    tree = deepcopy(course)
    target = next(item for item in tree.chapters if item.id == chapter.id)
    for section, result in zip(target.sections, generated.sections, strict=True):
        if section.points:
            continue
        for i, point in enumerate(result.points or []):
            row = Point(section_id=section.id, name=point.name, intro=point.intro, position=i)
            db.add(row)
            db.flush()
            section.points.append(SimpleNamespace(id=row.id, name=row.name, intro=row.intro,
                                                 position=i, content_markdown=None))
    version = new_version(
        db,
        tree,
        base_id=course.outline_version_id,
        reason=f"展开知识点：{chapter.name}",
        routing_snapshot=routing_snapshot,
    )
    choose(db, course.id, version.id)
    db.commit()
    return as_view(get_manifest(db, course.id, version.id))
