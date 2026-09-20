from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from backend.courses.schemas import Intro, Name
from backend.intake.schemas import CourseBrief


class CourseRequest(BaseModel):
    topic: Name
    intro: Intro
    brief: CourseBrief | None = None


class Point(BaseModel):
    name: Name
    intro: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=360)]


class Section(BaseModel):
    name: Name
    points: list[Point] | None = None


class Chapter(BaseModel):
    name: Name
    sections: list[Section] = Field(min_length=1)


class OutlineSection(BaseModel):
    name: Name


class OutlineChapter(BaseModel):
    name: Name
    sections: list[OutlineSection] = Field(min_length=1)


class CourseByAI(BaseModel):
    name: Name
    # 大纲 schema 只允许章节/小节，不用带 points 的 Section 诱导模型提前生成知识点。
    chapters: list[OutlineChapter] = Field(min_length=1)


class ChapterPointsRequest(BaseModel):
    course: CourseRequest
    chapter: Chapter
    existing_point_names: list[str] = Field(default_factory=list)
    course_context: str = ""
