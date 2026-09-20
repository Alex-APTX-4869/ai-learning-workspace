from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

class BatchCreate(StrictModel):
    request_id: UUID
    name: str = Field(default="", max_length=200)
    intro: str = Field(default="", max_length=12000)

class RevisionRequest(StrictModel):
    expected_revision: int = Field(ge=1)

class BatchUpdate(RevisionRequest):
    name: str = Field(max_length=200)
    intro: str = Field(max_length=12000)
    completeness: Literal["partial", "complete"]

class AnalysisStart(RevisionRequest):
    routing_hash: str = Field(pattern=r"^[a-f0-9]{64}$")

class Annotation(StrictModel):
    role: Literal["overview", "chapter", "reference", "auto"] = "auto"
    chapter: str = Field(default="", max_length=120)
    note: str = Field(default="", max_length=2000)
    page_start: int | None = Field(default=None, ge=1, le=150)
    page_end: int | None = Field(default=None, ge=1, le=150)

    @model_validator(mode="after")
    def valid_range(self):
        if self.role == "chapter" and not self.chapter.strip():
            raise ValueError("指定章节时请填写章节编号或名称")
        if (self.page_start is None) != (self.page_end is None):
            raise ValueError("页码范围需要同时填写起止页")
        if self.page_start and self.page_end < self.page_start:
            raise ValueError("结束页不能小于开始页")
        return self

class FileUpdate(RevisionRequest):
    annotations: list[Annotation] = Field(min_length=1, max_length=30)
    included: bool
    text_only_accepted: bool = False

    @model_validator(mode="after")
    def annotation_budget(self):
        if sum(len(a.note) + len(a.chapter) for a in self.annotations) > 6000:
            raise ValueError("单份文件的标注合计最多 6000 字，请简明描述用途")
        return self

class AnalysisSummary(StrictModel):
    summary: str = Field(min_length=1, max_length=1600)
    topics: list[str] = Field(default_factory=list, max_length=15)
    gaps: list[str] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def short_items(self):
        if any(len(text) > 160 for text in [*self.topics, *self.gaps]):
            raise ValueError("摘要条目过长")
        return self
