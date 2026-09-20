from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Intro = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=12000)]


class CourseCreate(BaseModel):
    name: Name
    intro: Intro


class ReadModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PointRead(ReadModel):
    id: int
    name: str
    intro: str
    content_markdown: str | None


class SectionRead(ReadModel):
    id: int
    name: str
    points: list[PointRead]


class ChapterRead(ReadModel):
    id: int
    name: str
    sections: list[SectionRead]


class CourseRead(ReadModel):
    id: int
    name: str
    intro: str
    outline_version_id: int | None = None
    directory_origin: str | None = None
    intro_is_fallback: bool = False
    chapters: list[ChapterRead]


class CourseSummary(ReadModel):
    id: int
    name: str
    intro: str
    chapter_count: int
    section_count: int
    point_count: int
