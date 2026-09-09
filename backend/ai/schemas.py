from pydantic import BaseModel, Field

from backend.courses.schemas import Intro, Name


class CourseRequest(BaseModel):
    topic: Name
    intro: Intro


class Point(BaseModel):
    name: Name
    intro: Intro


class Section(BaseModel):
    name: Name
    points: list[Point] | None = None


class Chapter(BaseModel):
    name: Name
    sections: list[Section] = Field(min_length=1)


class CourseByAI(BaseModel):
    name: Name
    chapters: list[Chapter] = Field(min_length=1)


class ChapterPointsRequest(BaseModel):
    course: CourseRequest
    chapter: Chapter
    existing_point_names: list[str] = Field(default_factory=list)
    course_context: str = ""
