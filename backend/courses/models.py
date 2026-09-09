from __future__ import annotations

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class Course(Base):
    __tablename__ = "courses"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    intro: Mapped[str] = mapped_column(Text)
    chapters: Mapped[list[Chapter]] = relationship(
        back_populates="course", order_by="Chapter.position", cascade="all, delete-orphan"
    )


class Chapter(Base):
    __tablename__ = "chapters"
    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"))
    name: Mapped[str] = mapped_column(String(200))
    position: Mapped[int]
    course: Mapped[Course] = relationship(back_populates="chapters")
    sections: Mapped[list[Section]] = relationship(
        back_populates="chapter", order_by="Section.position", cascade="all, delete-orphan"
    )


class Section(Base):
    __tablename__ = "sections"
    id: Mapped[int] = mapped_column(primary_key=True)
    chapter_id: Mapped[int] = mapped_column(ForeignKey("chapters.id"))
    name: Mapped[str] = mapped_column(String(200))
    position: Mapped[int]
    content_markdown: Mapped[str | None] = mapped_column(Text)
    chapter: Mapped[Chapter] = relationship(back_populates="sections")
    points: Mapped[list[Point]] = relationship(
        back_populates="section", order_by="Point.position", cascade="all, delete-orphan"
    )


class Point(Base):
    __tablename__ = "points"
    id: Mapped[int] = mapped_column(primary_key=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("sections.id"))
    name: Mapped[str] = mapped_column(String(200))
    intro: Mapped[str] = mapped_column(Text)
    position: Mapped[int]
    content_markdown: Mapped[str | None] = mapped_column(Text)
    section: Mapped[Section] = relationship(back_populates="points")
