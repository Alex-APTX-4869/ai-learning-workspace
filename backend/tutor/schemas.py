from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints, model_validator

MessageText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=6000)]


class TutorAction(BaseModel):
    request_id: UUID
    revision: int = Field(ge=0)
    card_id: str = Field(min_length=1, max_length=64)
    action: Literal["next", "previous", "message", "answer", "open"]
    target_card_id: str | None = Field(default=None, min_length=1, max_length=64)
    message: MessageText | None = None
    selected: list[int] = Field(default_factory=list, max_length=8)
    written_answer: str = Field(default="", max_length=6000)

    @model_validator(mode="after")
    def validate_action_payload(self):
        if (self.action == "open") != (self.target_card_id is not None):
            raise ValueError("只有切换对话需要 target_card_id")
        if (self.action == "message") != (self.message is not None):
            raise ValueError("只有对话操作必须携带 message")
        if self.action != "answer" and (self.selected or self.written_answer):
            raise ValueError("答题内容只能用于 answer 操作")
        if len(set(self.selected)) != len(self.selected) or any(index < 0 for index in self.selected):
            raise ValueError("选项编号不能重复或为负数")
        return self


class TutorDecision(BaseModel):
    reply_markdown: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=5000)]
    action: Literal["stay", "show_next_card"]


class TutorTurnRead(BaseModel):
    id: int
    card_id: str
    action: str
    status: str
    user_message: str | None
    reply_markdown: str | None
    error: str | None
    teacher_action: str | None


class TutorSessionRead(BaseModel):
    id: int
    course_id: int
    point_id: int
    outline_version_id: int | None
    content_version_id: int
    revision: int
    card_index: int
    card_count: int
    completed: bool
    busy: bool
    current_card: dict
    card_tabs: list[dict] = Field(default_factory=list)
    stages: list[dict]
    response: dict | None
    turns: list[TutorTurnRead]
    timeline: list[dict] = Field(default_factory=list)
    timeline_truncated: bool = False
