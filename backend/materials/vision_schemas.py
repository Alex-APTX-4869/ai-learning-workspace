from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RecognizedBlock(Strict):
    kind: Literal["text", "formula", "table", "diagram"]
    title: str = Field(max_length=200)
    content: str = Field(max_length=10000)
    uncertain: bool
    note: str = Field(max_length=1000)


class RecognizedPage(Strict):
    blocks: list[RecognizedBlock] = Field(max_length=80)
    issues: list[str] = Field(max_length=40)

    @model_validator(mode="after")
    def bounded(self):
        if not self.blocks and not self.issues:
            raise ValueError("空识别结果必须说明原因")
        if any(len(i) > 1000 for i in self.issues) or len(self.model_dump_json()) > 100000:
            raise ValueError("单页识别结果过长")
        for block in self.blocks:
            if block.uncertain and not block.note.strip():
                raise ValueError("不确定内容必须说明原因")
        return self


class RecognitionStart(Strict):
    request_id: UUID
    plan_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class RecognitionReview(Strict):
    expected_revision: int = Field(ge=1)
    decision: Literal["accepted", "rejected"]
    note: str = Field(default="", max_length=1000)


class RecognitionAdopt(Strict):
    expected_file_revision: int = Field(ge=1)
    expected_recognition_revision: int = Field(ge=1)
    selected: bool
