from fastapi import HTTPException
from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session, selectinload

from backend.courses.models import Chapter, Course, Point, Section
from backend.courses.schemas import CourseCreate


def course_query():
    return select(Course).options(
        selectinload(Course.chapters).selectinload(Chapter.sections).selectinload(Section.points)
    )


def list_courses(db: Session):
    # 旧表保留所有历史节点，不能把它们都统计为“当前课程”。
    from backend.versions.models import DirectoryManifest
    from backend.outlines.models import CourseOutlineSelection
    query = (
        select(
            Course.id,
            Course.name,
            Course.intro,
            func.count(distinct(Chapter.id)).label("chapter_count"),
            func.count(distinct(Section.id)).label("section_count"),
            func.count(distinct(Point.id)).label("point_count"),
        )
        .outerjoin(Chapter, Chapter.course_id == Course.id)
        .outerjoin(Section, Section.chapter_id == Chapter.id)
        .outerjoin(Point, Point.section_id == Section.id)
        .group_by(Course.id)
        .order_by(Course.id.desc())
    )
    summaries = [dict(row) for row in db.execute(query).mappings().all()]
    manifests = {row.course_id: row.tree_json for row in db.scalars(
        select(DirectoryManifest).join(CourseOutlineSelection, CourseOutlineSelection.version_id == DirectoryManifest.version_id)
    ).all()}
    for row in summaries:
        if tree := manifests.get(row["id"]):
            sections = [section for chapter in tree["chapters"] for section in chapter["sections"]]
            row.update(chapter_count=len(tree["chapters"]), section_count=len(sections),
                       point_count=sum(len(section["points"]) for section in sections))
    return summaries


def get_course(db: Session, course_id: int, *, lock: bool = False, outline_version_id: int | None = None) -> Course:
    from backend.versions import service as versions
    from backend.versions.models import DirectoryManifest
    query = select(Course).where(Course.id == course_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    course = db.scalar(query)
    if course is None:
        raise HTTPException(404, "这门课程不存在。")
    version_id = outline_version_id if outline_version_id is not None else versions.selected_id(db, course_id)
    if version_id is not None:
        manifest = db.get(DirectoryManifest, version_id)
        if manifest is not None and manifest.course_id == course_id:
            return versions.as_view(manifest)
        if outline_version_id is not None:
            # 迁移前的历史 OutlineVersion 没有 manifest。首次精确读取时给它
            # 建一棵独立空内容树；不能把当前目录的正文按同名节点猜过去。
            from backend.outlines.models import OutlineVersion
            version = db.get(OutlineVersion, outline_version_id)
            if version is None or version.course_id != course_id:
                raise HTTPException(404, "这门课程没有该可读取目录版本。")
            manifest = versions.materialize_snapshot(db, version)
            return versions.as_view(manifest)
    return course


def create_course(db: Session, data: CourseCreate) -> Course:
    course = Course(**data.model_dump())
    db.add(course)
    db.commit()
    return get_course(db, course.id)


def update_course(db: Session, course_id: int, data: CourseCreate) -> Course:
    course = get_course(db, course_id, lock=True)
    raw = db.get(Course, course_id)
    raw.name, raw.intro = data.name, data.intro
    if getattr(course, "outline_version_id", None) is not None:
        from backend.versions import service as versions
        course.name, course.intro = data.name, data.intro
        version = versions.new_version(db, course, base_id=course.outline_version_id, reason="更新课程信息")
        versions.choose(db, course_id, version.id)
    db.commit()
    return get_course(db, course_id)


def find_chapter(course: Course, chapter_id: int) -> Chapter:
    chapter = next((item for item in course.chapters if item.id == chapter_id), None)
    if chapter is None:
        raise HTTPException(404, "这门课程中没有找到该章节。")
    return chapter


def save_outline(
    db: Session,
    course: Course,
    outline,
    *,
    routing_snapshot: dict | None = None,
) -> Course:
    # 调用方已锁住课程行，重复请求不插入第二份目录或覆盖旧内容。
    if not course.chapters:
        from backend.versions import service as versions
        tree = versions.create_outline_tree(db, course.id, course.name, course.intro, outline)
        version = versions.new_version(
            db, tree, origin="generated", routing_snapshot=routing_snapshot
        )
        versions.choose(db, course.id, version.id)
        db.commit()
    return get_course(db, course.id)


def save_points(
    db: Session,
    course: Course,
    chapter: Chapter,
    generated,
    *,
    routing_snapshot: dict | None = None,
) -> Course:
    if all(section.points for section in chapter.sections):
        return course
    if getattr(course, "outline_version_id", None) is not None:
        from backend.versions.service import save_points_revision
        return save_points_revision(
            db,
            course,
            chapter,
            generated,
            routing_snapshot=routing_snapshot,
        )
    for section, result in zip(chapter.sections, generated.sections, strict=True):
        # 已有内容不覆盖，只补充尚未生成的小节。
        if section.points:
            continue
        section.points = [
            Point(name=point.name, intro=point.intro, position=i)
            for i, point in enumerate(result.points or [])
        ]
    db.commit()
    return get_course(db, course.id)
