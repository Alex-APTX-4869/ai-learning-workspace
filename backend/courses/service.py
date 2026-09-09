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
    # 首页只取统计摘要，未来讲义变长后也不会一次下载所有正文。
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
    return db.execute(query).mappings().all()


def get_course(db: Session, course_id: int, *, lock: bool = False) -> Course:
    query = course_query().where(Course.id == course_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    course = db.scalar(query)
    if course is None:
        raise HTTPException(404, "这门课程不存在。")
    return course


def create_course(db: Session, data: CourseCreate) -> Course:
    course = Course(**data.model_dump())
    db.add(course)
    db.commit()
    return get_course(db, course.id)


def update_course(db: Session, course_id: int, data: CourseCreate) -> Course:
    course = get_course(db, course_id, lock=True)
    course.name, course.intro = data.name, data.intro
    db.commit()
    return get_course(db, course_id)


def find_chapter(course: Course, chapter_id: int) -> Chapter:
    chapter = next((item for item in course.chapters if item.id == chapter_id), None)
    if chapter is None:
        raise HTTPException(404, "这门课程中没有找到该章节。")
    return chapter


def save_outline(db: Session, course: Course, outline) -> Course:
    # 调用方已锁住课程行，重复请求不插入第二份目录或覆盖旧内容。
    if not course.chapters:
        course.chapters = [
            Chapter(name=chapter.name, position=i, sections=[
                Section(name=section.name, position=j)
                for j, section in enumerate(chapter.sections)
            ])
            for i, chapter in enumerate(outline.chapters)
        ]
        db.commit()
    return get_course(db, course.id)


def save_points(db: Session, course: Course, chapter: Chapter, generated) -> Course:
    if all(section.points for section in chapter.sections):
        return course
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
