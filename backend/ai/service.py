import json

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.ai.client import generate_json
from backend.ai.prompts import outline_prompt, points_prompt
from backend.ai.schemas import Chapter, ChapterPointsRequest, CourseByAI, CourseRequest
from backend.courses import service as courses
from backend.courses.schemas import CourseRead


def generate_outline(request: CourseRequest) -> CourseByAI:
    return generate_json(outline_prompt(request), CourseByAI)


def generate_points(request: ChapterPointsRequest) -> Chapter:
    result = generate_json(points_prompt(request), Chapter)
    if (result.name != request.chapter.name
            or [s.name for s in result.sections] != [s.name for s in request.chapter.sections]
            or any(not s.points for s in result.sections)):
        raise HTTPException(502, "模型修改了原目录或遗漏了知识点，本次未保存，请重试。")
    return result


def generate_saved_outline(course_id: int, db: Session):
    course = courses.get_course(db, course_id)
    if course.chapters:
        return course
    request = CourseRequest(topic=course.name, intro=course.intro)
    # 等待模型期间释放事务，不长期占用数据库锁。
    db.rollback()
    result = generate_outline(request)
    course = courses.get_course(db, course_id, lock=True)
    if (course.name, course.intro) != (request.topic, request.intro):
        raise HTTPException(409, "生成期间课程信息已修改，请使用新信息重新生成。")
    return courses.save_outline(db, course, result)


def generate_saved_points(course_id: int, chapter_id: int, db: Session):
    course = courses.get_course(db, course_id)
    chapter = courses.find_chapter(course, chapter_id)
    if all(section.points for section in chapter.sections):
        return course
    snapshot = CourseRead.model_validate(course)
    # 当前阶段传入目录及知识点简介；完整正文不进入这次请求。
    context = {
        "name": snapshot.name,
        "chapters": [{"name": c.name, "sections": [
            {"name": s.name, "points": [{"name": p.name, "intro": p.intro} for p in s.points]}
            for s in c.sections
        ]} for c in snapshot.chapters],
    }
    request = ChapterPointsRequest(
        course=CourseRequest(topic=course.name, intro=course.intro),
        chapter=Chapter(name=chapter.name, sections=[{"name": s.name} for s in chapter.sections]),
        existing_point_names=[p.name for c in course.chapters for s in c.sections for p in s.points],
        course_context=json.dumps(context, ensure_ascii=False),
    )
    db.rollback()
    result = generate_points(request)
    course = courses.get_course(db, course_id, lock=True)
    chapter = courses.find_chapter(course, chapter_id)
    if ((course.name, course.intro) != (request.course.topic, request.course.intro)
            or chapter.name != request.chapter.name
            or [s.name for s in chapter.sections] != [s.name for s in request.chapter.sections]):
        raise HTTPException(409, "生成期间课程目录已修改，请重试。")
    return courses.save_points(db, course, chapter, result)
