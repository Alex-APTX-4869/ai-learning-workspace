from __future__ import annotations

from copy import deepcopy

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.ai.client import generate_json_messages
from backend.courses import service as courses
from backend.courses.models import Course
from backend.intake.models import IntakeSession, IntakeTurn
from backend.intake.prompts import (
    brief_messages,
    depth_options_messages,
    interview_question_messages,
    option_explanation_messages,
)
from backend.intake.schemas import (
    AnswerSubmit,
    CourseBrief,
    DepthOption,
    DepthSelect,
    ExtraQuestionRequest,
    GeneratedDepthPlan,
    GeneratedQuestion,
    IntakeAnswer,
    IntakeConfirmation,
    IntakeCreate,
    IntakeRead,
    InterviewQuestion,
    OptionExplanation,
    QuestionOption,
)
from backend.providers.routing import resolve_routing_snapshot
from backend.materials import service as materials
from backend.intake import extensions


def intake_intro(db, intake):
    return extensions.history_context(materials.with_materials(intake.initial_intro, materials.intake_context(db, intake.id)), intake.extension_history or [])


INTAKE_MODEL_ROLES = (
    "intake.depth",
    "intake.interview",
    "intake.brief",
    "intake.explain",
)


def get_intake(db: Session, intake_id: int, *, lock: bool = False) -> IntakeSession:
    query = (
        select(IntakeSession)
        .where(IntakeSession.id == intake_id)
        .options(selectinload(IntakeSession.turns))
    )
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    intake = db.scalar(query)
    if intake is None:
        raise HTTPException(404, "没有找到这次课程需求确认。")
    return intake


def get_latest_active_intake(db: Session) -> IntakeSession:
    intake = db.scalar(
        select(IntakeSession)
        .where(IntakeSession.status != "completed")
        .options(selectinload(IntakeSession.turns))
        .order_by(IntakeSession.id.desc())
        .limit(1)
    )
    if intake is None:
        raise HTTPException(404, "当前没有未完成的课程需求确认。")
    return intake


def generate_depth_plan(
    data: IntakeCreate, *, routing_snapshot: dict | None = None
) -> GeneratedDepthPlan:
    system, user = depth_options_messages(data.name, data.intro)
    return generate_json_messages(
        system,
        user,
        GeneratedDepthPlan,
        role="intake.depth",
        snapshot=routing_snapshot,
    )


def generate_interview_question(
    *,
    name: str,
    intro: str,
    selected_depth: DepthOption,
    answers: list[IntakeAnswer],
    question_number: int,
    question_count: int,
    routing_snapshot: dict | None = None,
) -> GeneratedQuestion:
    system, user = interview_question_messages(
        name=name,
        intro=intro,
        selected_depth=selected_depth,
        answers=answers,
        question_number=question_number,
        question_count=question_count,
    )
    # focus_key 由模型生成；大小写差异不应绕过重复问题检查。
    used_keys = {answer.focus_key.casefold() for answer in answers}
    for _ in range(2):
        result = generate_json_messages(
            system,
            user,
            GeneratedQuestion,
            role="intake.interview",
            snapshot=routing_snapshot,
        )
        if result.focus_key.casefold() not in used_keys:
            return result
        system += (
            "\n上一次返回的 focus_key 已经使用过。请换一个尚未确认的关注点，"
            "仍只返回规定的 JSON。"
        )
    raise HTTPException(502, "模型连续生成了重复问题，请重试本次访谈。")


def generate_course_brief(
    *,
    name: str,
    intro: str,
    selected_depth: DepthOption,
    answers: list[IntakeAnswer],
    routing_snapshot: dict | None = None,
) -> CourseBrief:
    system, user = brief_messages(
        name=name,
        intro=intro,
        selected_depth=selected_depth,
        answers=answers,
    )
    return generate_json_messages(
        system,
        user,
        CourseBrief,
        role="intake.brief",
        snapshot=routing_snapshot,
    )


def generate_option_explanation(
    *,
    name: str,
    intro: str,
    selected_depth: DepthOption,
    answers: list[IntakeAnswer],
    question: InterviewQuestion,
    option: QuestionOption,
    routing_snapshot: dict | None = None,
) -> OptionExplanation:
    system, user = option_explanation_messages(
        name=name,
        intro=intro,
        selected_depth=selected_depth,
        answers=answers,
        question=question,
        option=option,
    )
    return generate_json_messages(
        system,
        user,
        OptionExplanation,
        role="intake.explain",
        snapshot=routing_snapshot,
    )


def create_intake(db: Session, data: IntakeCreate) -> IntakeSession:
    # 此时还没有 intake_id，因此第一轮按全局配置一次性解析四个职责；
    # 后续整场访谈只读这份快照，设置页中途改模型也不会混用。
    batch_id = str(data.material_batch_id) if data.material_batch_id else None
    context = None
    if batch_id:
        batch = materials.get_batch(db, batch_id, lock=True)
        if batch.intake_id:
            return get_intake(db, batch.intake_id)
        if batch.status != "ready":
            raise HTTPException(409, "请先完成资料分析并核对识别范围。")
        if batch.name != data.name or batch.intro != data.intro:
            raise HTTPException(409, "课程想法已变化，请返回资料编辑并重新分析。")
        context = deepcopy(batch.context_json)
        routing_snapshot = deepcopy(batch.routing_snapshot_json)
    else:
        routing_snapshot = resolve_routing_snapshot(db, INTAKE_MODEL_ROLES, scope_type="global")
    # 模型调用前释放读事务，不在网络等待期间占用数据库连接或锁。
    db.rollback()
    plan_data = data.model_copy(update={"intro": materials.with_materials(data.intro, context)})
    plan = generate_depth_plan(plan_data, routing_snapshot=routing_snapshot)
    options = [
        DepthOption(id=f"depth_{index}", **option.model_dump())
        for index, option in enumerate(plan.options, start=1)
    ]
    if batch_id:
        batch = materials.get_batch(db, batch_id, lock=True)
        if batch.intake_id:
            return get_intake(db, batch.intake_id)
        if batch.status != "ready" or batch.context_json != context:
            raise HTTPException(409, "资料范围已经变化，请重新开始需求确认。")
    intake = IntakeSession(
        initial_name=data.name,
        initial_intro=data.intro,
        depth_options=[option.model_dump(mode="json") for option in options],
        routing_snapshot_json=routing_snapshot,
    )
    db.add(intake)
    db.flush()
    if batch_id:
        batch.intake_id, batch.status = intake.id, "linked"
    db.commit()
    db.refresh(intake)
    return intake


def _normalize_question(draft: GeneratedQuestion, number: int) -> InterviewQuestion:
    return InterviewQuestion(
        id=f"question_{number}",
        number=number,
        focus_key=draft.focus_key,
        baseline=draft.baseline,
        text=draft.text,
        purpose=draft.purpose,
        recommendation_reason=draft.recommendation_reason,
        options=[
            QuestionOption(id=f"option_{index}", **option.model_dump())
            for index, option in enumerate(draft.options, start=1)
        ],
    )


def select_depth(
    db: Session, intake_id: int, selection: DepthSelect
) -> IntakeSession:
    intake = get_intake(db, intake_id)
    if intake.status != "choosing_depth":
        raise HTTPException(409, "访谈深度已经选择，不能重复提交。")

    options = [DepthOption.model_validate(item) for item in intake.depth_options]
    if selection.option_id is not None:
        selected = next(
            (item for item in options if item.id == selection.option_id), None
        )
        if selected is None:
            raise HTTPException(422, "所选访谈深度不存在。")
    else:
        assert selection.question_count is not None
        selected = DepthOption(
            id="custom",
            title="自定义访谈",
            description=f"按照你的选择确认 {selection.question_count} 个关键问题。",
            question_count=selection.question_count,
            recommended=False,
        )

    version = intake.version
    name, intro = intake.initial_name, intake_intro(db, intake)
    routing_snapshot = deepcopy(intake.routing_snapshot_json)
    db.rollback()
    draft = generate_interview_question(
        name=name,
        intro=intro,
        selected_depth=selected,
        answers=[],
        question_number=1,
        question_count=selected.question_count,
        routing_snapshot=routing_snapshot,
    )
    question = _normalize_question(draft, 1)

    intake = get_intake(db, intake_id, lock=True)
    if intake.version != version or intake.status != "choosing_depth":
        raise HTTPException(409, "访谈状态已经变化，请获取最新状态后继续。")
    intake.selected_depth = selected.model_dump(mode="json")
    intake.question_count = selected.question_count
    intake.current_question = question.model_dump(mode="json")
    intake.turns.append(
        IntakeTurn(
            position=1,
            question_json=question.model_dump(mode="json"),
        )
    )
    intake.status = "interviewing"
    intake.version += 1
    db.commit()
    db.refresh(intake)
    return intake


def explain_option(
    db: Session,
    intake_id: int,
    question_id: str,
    option_id: str,
) -> OptionExplanation:
    intake = get_intake(db, intake_id)
    if intake.status != "interviewing" or intake.current_question is None:
        raise HTTPException(409, "当前没有可以解释的访谈问题。")
    question = InterviewQuestion.model_validate(intake.current_question)
    if question.id != question_id:
        raise HTTPException(409, "这个问题已经不是当前问题，请刷新后继续。")
    option = next((item for item in question.options if item.id == option_id), None)
    if option is None:
        raise HTTPException(422, "这个选项不属于当前问题。")

    selected = DepthOption.model_validate(intake.selected_depth)
    answers = [
        IntakeAnswer.model_validate(turn.answer_json)
        for turn in intake.turns
        if turn.answer_json
    ]
    name, intro = intake.initial_name, intake_intro(db, intake)
    routing_snapshot = deepcopy(intake.routing_snapshot_json)
    db.rollback()
    explanation = generate_option_explanation(
        name=name,
        intro=intro,
        selected_depth=selected,
        answers=answers,
        question=question,
        option=option,
        routing_snapshot=routing_snapshot,
    )

    # 短暂锁住会话完成最终校验，确保解释返回时用户仍在同一道题。
    intake = get_intake(db, intake_id, lock=True)
    if intake.status != "interviewing" or not intake.current_question:
        raise HTTPException(409, "问题已推进，本次解释已过期。")
    current = InterviewQuestion.model_validate(intake.current_question)
    if current.id != question_id or not any(
        item.id == option_id for item in current.options
    ):
        raise HTTPException(409, "问题已推进，本次解释已过期。")
    return explanation


def add_extra_question(db: Session, intake_id: int, request: ExtraQuestionRequest) -> IntakeSession:
    raise HTTPException(410, "需要澄清时，访谈 Agent 会自动增加一道问题。")


def _record_answer(
    question: InterviewQuestion, submission: AnswerSubmit
) -> IntakeAnswer:
    if submission.option_id is not None:
        option = next(
            (item for item in question.options if item.id == submission.option_id),
            None,
        )
        if option is None:
            raise HTTPException(422, "这个选项不属于当前问题。")
        return IntakeAnswer(
            question_id=question.id,
            focus_key=question.focus_key,
            question_text=question.text,
            baseline=question.baseline,
            answer_type="option",
            option_id=option.id,
            answer=option.title,
            option_description=option.description,
        )
    assert submission.custom_answer is not None
    return IntakeAnswer(
        question_id=question.id,
        focus_key=question.focus_key,
        question_text=question.text,
        baseline=question.baseline,
        answer_type="custom",
        answer=submission.custom_answer,
    )


def submit_answer(
    db: Session, intake_id: int, submission: AnswerSubmit
) -> IntakeSession:
    intake = get_intake(db, intake_id)
    if intake.status != "interviewing" or intake.current_question is None:
        raise HTTPException(409, "当前没有等待回答的问题。")

    question = InterviewQuestion.model_validate(intake.current_question)
    if submission.question_id != question.id:
        raise HTTPException(409, "这个问题已经不是当前问题，请刷新后继续。")
    answer = _record_answer(question, submission)
    answers = [
        IntakeAnswer.model_validate(turn.answer_json)
        for turn in intake.turns
        if turn.answer_json
    ]
    answers.append(answer)
    selected = DepthOption.model_validate(intake.selected_depth)
    assert intake.question_count is not None

    version = intake.version
    name, intro = intake.initial_name, intake_intro(db, intake)
    question_count = intake.question_count
    is_last = len(answers) >= question_count
    extension_history = deepcopy(intake.extension_history or [])
    routing_snapshot = deepcopy(intake.routing_snapshot_json)
    db.rollback()

    proposal = None
    if answer.answer_type == 'custom' or is_last:
        proposal = extensions.assess(name=name,intro=intro,answers=answers,question_count=question_count,
                                     history=extension_history,snapshot=routing_snapshot)
    if proposal:
        brief = None
        next_question = _normalize_question(GeneratedQuestion.model_validate(proposal['question']), len(answers) + 1)
        next_question.extension_reason = proposal['reason']
    elif is_last:
        brief = generate_course_brief(
            name=name,
            intro=intro,
            selected_depth=selected,
            answers=answers,
            routing_snapshot=routing_snapshot,
        )
        next_question = None
    else:
        draft = generate_interview_question(
            name=name,
            intro=intro,
            selected_depth=selected,
            answers=answers,
            question_number=len(answers) + 1,
            question_count=question_count,
            routing_snapshot=routing_snapshot,
        )
        next_question = _normalize_question(draft, len(answers) + 1)
        brief = None

    intake = get_intake(db, intake_id, lock=True)
    if (
        intake.version != version
        or intake.status != "interviewing"
        or not intake.current_question
        or intake.current_question.get("id") != question.id
    ):
        raise HTTPException(409, "访谈状态已经变化，本次回答没有重复写入。")

    current_turn = next(
        (
            turn
            for turn in intake.turns
            if turn.question_json.get("id") == question.id
        ),
        None,
    )
    if current_turn is None or current_turn.answer_json is not None:
        raise HTTPException(409, "当前问题已经处理，请获取最新状态后继续。")
    current_turn.answer_json = answer.model_dump(mode="json")
    intake.current_question = (
        next_question.model_dump(mode="json") if next_question else None
    )
    if next_question is not None:
        intake.turns.append(
            IntakeTurn(
                position=next_question.number,
                question_json=next_question.model_dump(mode="json"),
            )
        )
    if brief is not None:
        brief = brief.model_copy(update={"material_basis": materials.intake_context(db, intake.id)})
        intake.brief = brief.model_dump(mode="json")
        intake.status = "ready_to_confirm"
    if proposal:
        intake.question_count = question_count + 1
        intake.extension_proposal = None
        intake.extension_history = [*extension_history, {
            'id': proposal['id'], 'reason': proposal['reason'],
            'uncertainty': proposal['uncertainty'], 'automatic': True,
        }]
    intake.version += 1
    db.commit()
    db.refresh(intake)
    return intake


def confirm_intake(
    db: Session,
    intake_id: int,
    edited_brief: CourseBrief | None = None,
) -> IntakeConfirmation:
    intake = get_intake(db, intake_id, lock=True)
    if intake.status == "completed" and intake.course_id is not None:
        course = courses.get_course(db, intake.course_id)
        return IntakeConfirmation(
            intake=IntakeRead.model_validate(intake), course=course
        )
    if intake.status != "ready_to_confirm" or intake.brief is None:
        raise HTTPException(409, "需求访谈尚未完成，暂时不能创建课程。")

    brief = edited_brief or CourseBrief.model_validate(intake.brief)
    brief = brief.model_copy(update={"material_basis": materials.intake_context(db, intake.id)})
    course = Course(name=brief.course_name, intro=brief.summary)
    db.add(course)
    db.flush()
    intake.brief = brief.model_dump(mode="json")
    intake.course_id = course.id
    intake.status = "completed"
    intake.version += 1
    db.commit()

    intake = get_intake(db, intake_id)
    course = courses.get_course(db, course.id)
    return IntakeConfirmation(
        intake=IntakeRead.model_validate(intake), course=course
    )


def get_confirmed_brief(db: Session, course_id: int) -> CourseBrief | None:
    payload = db.scalar(
        select(IntakeSession.brief).where(
            IntakeSession.course_id == course_id,
            IntakeSession.status == "completed",
        )
    )
    return CourseBrief.model_validate(payload) if payload else None
