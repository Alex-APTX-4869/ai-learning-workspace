from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


ShortText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)
]
MarkdownText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200000)
]
PythonCode = Annotated[
    str, StringConstraints(min_length=1, max_length=100000)
]


class OptionalComponentPlan(BaseModel):
    """规划 Agent 的按需路由决定。

    needed 不是按固定模板填写，而是根据当前知识点的学习目标决定
    是否值得额外调用一个专门 Agent。
    """

    needed: bool
    reason: ShortText
    goal: ShortText | None = None

    @model_validator(mode="after")
    def needed_component_has_goal(self):
        if self.needed and not self.goal:
            raise ValueError("需要生成的内容组件必须说明教学目标")
        return self


class PointPlanItem(BaseModel):
    point_id: int = Field(ge=1)
    learning_objective: ShortText
    scope_in: list[ShortText] = Field(default_factory=list)
    scope_out: list[ShortText] = Field(default_factory=list)
    prerequisite_point_ids: list[int] = Field(default_factory=list)
    example_plan: OptionalComponentPlan
    exercise_plan: OptionalComponentPlan
    code_lab_plan: OptionalComponentPlan


class SectionTeachingPlan(BaseModel):
    section_goal: ShortText
    point_plans: list[PointPlanItem] = Field(min_length=1)


class SourceAttribution(BaseModel):
    source_kind: Literal["source_based", "supplemental"] = "supplemental"
    source_ids: list[Annotated[str, StringConstraints(pattern=r"^S[1-6]$")]] = Field(default_factory=list, max_length=6)


class LessonCard(SourceAttribution):
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    body_markdown: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2400)]


LearningGoal = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]


class LessonDraft(BaseModel):
    learning_goals: list[LearningGoal] = Field(min_length=1, max_length=4)
    lesson_cards: list[LessonCard] = Field(min_length=1)
    summary: ShortText
    source_gaps: list[ShortText] = Field(default_factory=list, max_length=6)

    @property
    def lesson_markdown(self) -> str:
        # 卡片是唯一正文来源，阅读视图直接拼合，避免模型同时生成两份不一致讲义。
        return "\n\n".join(f"## {card.title}\n\n{card.body_markdown}" for card in self.lesson_cards)


class ContentExample(SourceAttribution):
    title: ShortText
    explanation_markdown: MarkdownText
    code: str | None = Field(default=None, max_length=100000)
    language: str | None = Field(default=None, max_length=100)


class ExampleSet(BaseModel):
    examples: list[ContentExample] = Field(min_length=1)


class ExerciseOption(BaseModel):
    label: ShortText
    text: ShortText
    correct: bool


class ContentExercise(SourceAttribution):
    kind: Literal[
        "single_choice", "multiple_choice", "true_false", "short_answer"
    ] = "short_answer"
    question: MarkdownText
    options: list[ExerciseOption] = Field(default_factory=list, max_length=8)
    hint: str | None = Field(default=None, max_length=20000)
    answer: MarkdownText
    explanation: MarkdownText

    @model_validator(mode="after")
    def validate_objective_question(self):
        if self.kind == "short_answer":
            if self.options:
                raise ValueError("解答题不应包含选项")
            return self
        if len(self.options) < 2:
            raise ValueError("客观题至少需要两个选项")
        correct_count = sum(option.correct for option in self.options)
        if self.kind in ("single_choice", "true_false") and correct_count != 1:
            raise ValueError("单选题或判断题必须恰好有一个正确选项")
        if self.kind == "multiple_choice" and correct_count < 1:
            raise ValueError("多选题至少需要一个正确选项")
        if self.kind == "true_false" and len(self.options) != 2:
            raise ValueError("判断题必须恰好有两个选项")
        return self


class ExerciseSet(BaseModel):
    exercises: list[ContentExercise] = Field(min_length=1)


class CodeLabTest(BaseModel):
    name: ShortText
    assertion_code: PythonCode


class CodeLab(SourceAttribution):
    title: ShortText
    instructions_markdown: MarkdownText
    language: Literal["python"]
    starter_code: PythonCode
    solution_code: PythonCode
    tests: list[CodeLabTest] = Field(min_length=1, max_length=20)


class ContentRevision(LessonDraft):
    """修订输出只含一份卡片正文，阅读版由程序组合。"""

    examples: list[ContentExample] = Field(default_factory=list)
    exercises: list[ContentExercise] = Field(default_factory=list)
    code_lab: CodeLab | None = None


class PointContent(BaseModel):
    lesson_markdown: MarkdownText
    learning_goals: list[LearningGoal] = Field(default_factory=list, max_length=4)
    lesson_cards: list[LessonCard] = Field(default_factory=list)
    examples: list[ContentExample] = Field(default_factory=list)
    # 旧内容可以没有这些组件；新内容由规划结果决定是否必须生成。
    exercises: list[ContentExercise] = Field(default_factory=list)
    code_lab: CodeLab | None = None
    summary: ShortText
    source_gaps: list[ShortText] = Field(default_factory=list, max_length=6)
    # Server-owned frozen excerpts. None means legacy content, not verified grounding.
    material_evidence: dict | None = None

    @model_validator(mode="after")
    def cards_are_the_lesson_source(self):
        if self.lesson_cards:
            self.lesson_markdown = "\n\n".join(
                f"## {card.title}\n\n{card.body_markdown}" for card in self.lesson_cards
            )
        return self


class ContentReview(BaseModel):
    approved: bool
    issues: list[ShortText] = Field(default_factory=list)
    revision_instructions: list[ShortText] = Field(default_factory=list)


JobStatus = Literal[
    "queued",
    "planning",
    "writing",
    "reviewing",
    "revising",
    "needs_attention",
    "ready",
    "needs_review",
    "failed",
    "cancelled",
]


class LearningJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    course_id: int
    section_id: int
    point_id: int
    outline_version_id: int | None
    status: JobStatus
    revision_count: int
    plan_id: int | None
    content_version_id: int | None
    error: str | None
    created_at: datetime
    updated_at: datetime


class PointContentRead(BaseModel):
    id: int
    point_id: int
    outline_version_id: int | None = None
    version_number: int
    origin: Literal["generated", "legacy"]
    content: PointContent
    review: ContentReview
    created_at: datetime
