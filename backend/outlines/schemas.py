from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from backend.ai.schemas import CourseByAI
from backend.courses.schemas import CourseRead

AdditionalRequirements = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=12000)
]


class OutlineGenerationRequest(BaseModel):
    additional_requirements: AdditionalRequirements = ""
    reference_version_id: int | None = Field(default=None, ge=1)


class OutlineVersionRead(BaseModel):
    id: int
    course_id: int
    version_number: int
    name: str
    outline: CourseByAI
    additional_requirements: str
    reference_version_id: int | None
    created_at: datetime
    selected: bool


class OutlineActivationRead(BaseModel):
    version: OutlineVersionRead
    course: CourseRead
