from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

from backend.courses.schemas import CourseRead, Intro, Name

ShortText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)
]
BriefText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)
]
BriefItem = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=600)
]
Identifier = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=80,
        pattern=r"^[A-Za-z0-9_-]+$",
    ),
]
IntakeStatus = Literal[
    "choosing_depth", "interviewing", "awaiting_extension", "ready_to_confirm", "completed"
]


class IntakeCreate(BaseModel):
    name: Name
    intro: Intro
    material_batch_id: UUID | None = None


class GeneratedDepthOption(BaseModel):
    """需求分析角色生成的内容；稳定 ID 由后端添加。"""

    title: Name
    description: ShortText
    question_count: int = Field(ge=1, le=20)
    recommended: bool


class GeneratedDepthPlan(BaseModel):
    options: list[GeneratedDepthOption] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def validate_options(self):
        counts = [option.question_count for option in self.options]
        if counts != sorted(counts) or len(set(counts)) != 3:
            raise ValueError("三档问题数量必须严格递增")
        if sum(option.recommended for option in self.options) != 1:
            raise ValueError("三档方案必须恰好推荐一档")
        return self


class DepthOption(GeneratedDepthOption):
    id: Identifier


class GeneratedQuestionOption(BaseModel):
    """访谈角色生成的选项；稳定 ID 由后端添加。"""

    title: Name
    description: ShortText
    recommended: bool


class GeneratedQuestion(BaseModel):
    focus_key: Identifier
    baseline: str = Field(default="", max_length=400)
    text: ShortText
    purpose: ShortText
    recommendation_reason: ShortText
    options: list[GeneratedQuestionOption] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_recommendation(self):
        if sum(option.recommended for option in self.options) != 1:
            raise ValueError("每个问题必须恰好推荐一个选项")
        titles = ["".join(option.title.split()).casefold() for option in self.options]
        if len(titles) != len(set(titles)):
            raise ValueError("选项标题不能重复")
        return self


class QuestionOption(GeneratedQuestionOption):
    id: Identifier
    # 兼容已经持久化的旧问题；新的模型输出仍由 GeneratedQuestion 严格校验。
    recommended: bool = False


class InterviewQuestion(BaseModel):
    id: Identifier
    number: int = Field(ge=1)
    extension_reason: str | None = Field(default=None, max_length=1000)
    focus_key: Identifier
    baseline: str = Field(default="", max_length=400)
    text: ShortText
    purpose: ShortText
    # 旧问题没有该字段时返回空字符串；新问题一定会带模型给出的通俗依据。
    recommendation_reason: str = Field(default="", max_length=1000)
    options: list[QuestionOption] = Field(min_length=2)


class DepthSelect(BaseModel):
    option_id: Identifier | None = None
    question_count: int | None = Field(default=None, ge=1, le=20)

    @model_validator(mode="after")
    def exactly_one_choice(self):
        if (self.option_id is None) == (self.question_count is None):
            raise ValueError("option_id 和 question_count 必须且只能填写一个")
        return self


class AnswerSubmit(BaseModel):
    question_id: Identifier
    option_id: Identifier | None = None
    custom_answer: ShortText | None = None

    @model_validator(mode="after")
    def exactly_one_answer(self):
        if (self.option_id is None) == (self.custom_answer is None):
            raise ValueError("option_id 和 custom_answer 必须且只能填写一个")
        return self


class ExtraQuestionRequest(BaseModel):
    expected_version: int = Field(ge=0)


class ExtensionAssessment(BaseModel):
    request_extra: bool
    reason: str = Field(default="", max_length=1000)
    uncertainty: str = Field(default="", max_length=1000)
    question: GeneratedQuestion | None = None

    @model_validator(mode="after")
    def validate_request(self):
        if self.request_extra and (not self.reason.strip() or not self.uncertainty.strip() or self.question is None):
            raise ValueError("申请补问必须给出原因、未知点及一道具体问题")
        if not self.request_extra and self.question is not None:
            raise ValueError("不申请补问时不返回额外问题")
        return self


class ExtensionDecision(BaseModel):
    expected_version: int = Field(ge=0)
    proposal_id: UUID
    approve: bool


class OptionExplanation(BaseModel):
    plain_explanation: ShortText
    suitable_when: ShortText
    course_impact: ShortText
    example: ShortText


class IntakeAnswer(BaseModel):
    question_id: Identifier
    focus_key: Identifier
    question_text: ShortText
    # 保存作答时的共同前提，避免只保存增量选项而丢失其语义；旧回答默认空。
    baseline: str = Field(default="", max_length=400)
    answer_type: Literal["option", "custom"]
    option_id: Identifier | None = None
    answer: ShortText
    option_description: ShortText | None = None


class CourseBrief(BaseModel):
    course_name: Name
    summary: BriefText
    learner_profile: BriefText
    learning_outcomes: list[BriefItem] = Field(min_length=1, max_length=20)
    scope_in: list[BriefItem] = Field(min_length=1, max_length=30)
    scope_out: list[BriefItem] = Field(default_factory=list, max_length=30)
    learning_preferences: list[BriefItem] = Field(default_factory=list, max_length=20)
    constraints: list[BriefItem] = Field(default_factory=list, max_length=20)
    success_criteria: list[BriefItem] = Field(min_length=1, max_length=20)
    # 后端按已确认的资料批次写入；不采信模型或前端自行填写的来源。
    material_basis: dict | None = Field(default=None, exclude_if=lambda value: value is None)


class IntakeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    initial_name: str
    initial_intro: str
    status: IntakeStatus
    depth_options: list[DepthOption]
    selected_depth: DepthOption | None
    question_count: int | None
    answers: list[IntakeAnswer]
    current_question: InterviewQuestion | None
    brief: CourseBrief | None
    course_id: int | None
    version: int
    extension_proposal: dict | None = None


class BriefConfirm(BaseModel):
    brief: CourseBrief | None = None


class IntakeConfirmation(BaseModel):
    intake: IntakeRead
    course: CourseRead
