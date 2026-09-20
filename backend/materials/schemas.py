from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Locator(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["pdf_page", "word_paragraph", "word_table", "image"]
    page: int | None = Field(default=None, ge=1)
    paragraph: int | None = Field(default=None, ge=1)
    table: int | None = Field(default=None, ge=1)
    image: int | None = Field(default=None, ge=1)
    heading_path: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def required_anchor(self):
        field = {"pdf_page": "page", "word_paragraph": "paragraph", "word_table": "table", "image": "image"}[self.type]
        if getattr(self, field) is None:
            raise ValueError("缺少来源定位")
        return self


class Element(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^e[1-9][0-9]*$", max_length=20)
    kind: Literal["paragraph", "heading", "table", "formula", "visual", "page_image", "image"]
    text: str = Field(max_length=2_000_000)
    locator: Locator
    preview: str | None = Field(default=None, pattern=r"^[a-z0-9-]+\.png$")
    rows: list[list[str]] | None = None
    original_omml: str | None = Field(default=None, max_length=100_000)
    expression_status: Literal["unverified"] | None = None
    description_status: Literal["pending"] | None = None


class Artifact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str = Field(pattern=r"^[a-z0-9-]+\.png$", max_length=80)
    mime_type: Literal["image/png"]
    locator: Locator


class Issue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(pattern=r"^[a-z_]+$", max_length=80)
    locator: Locator | None = None


class OutlineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(max_length=2000)
    level: int = Field(ge=1, le=20)
    locator: Locator


class ParseReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    parser_version: Literal["local-structure-v1"]
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    format: Literal["pdf", "docx", "image"]
    status: Literal["ready", "needs_review"]
    page_count: int | None = Field(default=None, ge=1, le=150)
    elements: list[Element] = Field(max_length=12000)
    outline: list[OutlineItem] = Field(max_length=2000)
    issues: list[Issue] = Field(max_length=24000)
    artifacts: list[Artifact] = Field(max_length=150)
    coverage: dict[str, str | int]
    external_requests: Literal[0]

    @model_validator(mode="after")
    def coherent_result(self):
        if len({e.id for e in self.elements}) != len(self.elements):
            raise ValueError("重复片段身份")
        if self.issues and self.status == "ready":
            raise ValueError("存在识别问题不能标记为完整可用")
        paths = {artifact.path for artifact in self.artifacts}
        if len(paths) != len(self.artifacts):
            raise ValueError("重复产物")
        for item in [*self.elements, *self.artifacts, *self.outline]:
            if item.locator.type == "pdf_page" and (self.page_count is None or item.locator.page > self.page_count):
                raise ValueError("来源页越界")
        if any(e.preview and e.preview not in paths for e in self.elements):
            raise ValueError("缺少原页预览")
        return self
