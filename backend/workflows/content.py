from __future__ import annotations

import logging
import hashlib
import json
from contextvars import ContextVar
from copy import deepcopy
from datetime import datetime, timezone
from collections.abc import Callable
from typing import TypeVar

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.ai.client import generate_json_messages
from backend.courses import service as courses
from backend.learning import service as learning
from backend.learning.models import (
    LearningGenerationJob,
    LearningJobStep,
    PointContentSelection,
    PointContentVersion,
    SectionPlan,
)
from backend.learning.prompts import (
    review_point_messages,
    revise_point_messages,
    section_plan_messages,
    write_code_lab_messages,
    write_examples_messages,
    write_exercises_messages,
    write_lesson_messages,
)
from backend.learning.schemas import (
    CodeLab,
    ContentReview,
    ContentRevision,
    ExampleSet,
    ExerciseSet,
    LessonDraft,
    PointContent,
    PointPlanItem,
    SectionTeachingPlan,
)
from backend.versions import service as versions
from backend.learning.quality import language_issues, exercise_type_issues
from backend.learning.grounding import (
    MaterialEvidenceError, collect_evidence, attach_evidence, grounding_issues,
)


class StaleGeneration(Exception):
    pass


class WorkflowAlreadyClaimed(Exception):
    pass


StepResult = TypeVar("StepResult", bound=BaseModel)
_ACTIVE_ROUTING_SNAPSHOT: ContextVar[dict | None] = ContextVar(
    "content_workflow_routing_snapshot", default=None
)

ROLE_BY_STEP = {
    "plan": "content.plan",
    "lesson": "content.lesson",
    "examples": "content.examples",
    "exercises": "content.exercises",
    "code_lab": "content.code_lab",
    "review": "content.review",
    "revision": "content.revise",
}


def _step_hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def _checkpointed_model(
    bind,
    job_id: int,
    *,
    step_key: str,
    role_key: str,
    expected_status: str,
    input_payload: dict,
    schema: type[StepResult],
    call: Callable[[], StepResult],
) -> StepResult:
    """每个付费调用先落运行标记，成功后保存结构化结果供恢复复用。"""
    with Session(bind) as db:
        job, course = _lock_job(db, job_id)
        if job.status != expected_status:
            raise WorkflowAlreadyClaimed
        _assert_current(db, job, course)
        routing_snapshot = deepcopy(job.routing_snapshot_json)
        if routing_snapshot is None:
            # 只兼容 M2 之前没有快照的历史任务。
            route_fingerprint = None
            input_hash = _step_hash(input_payload)
        else:
            route = routing_snapshot.get("routes", {}).get(role_key)
            if not isinstance(route, dict) or not route.get("config_fingerprint"):
                raise HTTPException(409, f"内容任务缺少 {role_key} 模型快照。")
            route_fingerprint = route["config_fingerprint"]
            input_hash = _step_hash(
                {
                    "input": input_payload,
                    "route_fingerprint": route_fingerprint,
                }
            )
        step = db.scalar(select(LearningJobStep).where(
            LearningJobStep.job_id == job_id, LearningJobStep.step_key == step_key
        ).with_for_update())
        if step is not None:
            if step.input_hash != input_hash:
                raise StaleGeneration
            if step.status == "completed":
                return schema.model_validate(step.output_json)
            if step.status == "running":
                raise WorkflowAlreadyClaimed
        else:
            step = LearningJobStep(job_id=job_id, step_key=step_key,
                                   input_hash=input_hash, status="running")
            db.add(step)
        step.status = "running"
        step.output_json = None
        step.started_at = datetime.now(timezone.utc)
        step.completed_at = None
        db.commit()
    token = _ACTIVE_ROUTING_SNAPSHOT.set(routing_snapshot)
    try:
        result = call()
    except Exception:
        with Session(bind) as db:
            step = db.scalar(select(LearningJobStep).where(
                LearningJobStep.job_id == job_id, LearningJobStep.step_key == step_key
            ).with_for_update())
            if step is not None and step.status == "running":
                step.status = "failed"
                db.commit()
        raise
    finally:
        _ACTIVE_ROUTING_SNAPSHOT.reset(token)
    with Session(bind) as db:
        job, course = _lock_job(db, job_id)
        step = db.scalar(select(LearningJobStep).where(
            LearningJobStep.job_id == job_id, LearningJobStep.step_key == step_key
        ).with_for_update())
        if job.status != expected_status:
            if step is not None and step.status == "running":
                step.status = "discarded"
                db.commit()
            raise WorkflowAlreadyClaimed
        _assert_current(db, job, course)
        if step is None or step.status != "running" or step.input_hash != input_hash:
            raise WorkflowAlreadyClaimed
        step.output_json = result.model_dump(mode="json")
        step.status = "completed"
        step.completed_at = datetime.now(timezone.utc)
        db.commit()
    return result


def _generate_for_role(
    system: str, human: str, schema: type[StepResult], role_key: str
) -> StepResult:
    snapshot = _ACTIVE_ROUTING_SNAPSHOT.get()
    return generate_json_messages(
        system,
        human,
        schema,
        role=role_key,
        snapshot=snapshot,
    )


def plan_section(context: dict) -> SectionTeachingPlan:
    system, human = section_plan_messages(context)
    return _generate_for_role(system, human, SectionTeachingPlan, ROLE_BY_STEP["plan"])


def write_lesson(context: dict, plan: SectionTeachingPlan) -> LessonDraft:
    system, human = write_lesson_messages(context, plan)
    return _generate_for_role(system, human, LessonDraft, ROLE_BY_STEP["lesson"])


def write_examples(
    context: dict, plan: SectionTeachingPlan, lesson: LessonDraft
) -> ExampleSet:
    system, human = write_examples_messages(context, plan, lesson)
    return _generate_for_role(system, human, ExampleSet, ROLE_BY_STEP["examples"])


def write_exercises(
    context: dict, plan: SectionTeachingPlan, lesson: LessonDraft, examples: list
) -> ExerciseSet:
    system, human = write_exercises_messages(context, plan, lesson, examples)
    return _generate_for_role(system, human, ExerciseSet, ROLE_BY_STEP["exercises"])


def write_code_lab(
    context: dict, plan: SectionTeachingPlan, lesson: LessonDraft, prior_materials: dict
) -> CodeLab:
    system, human = write_code_lab_messages(context, plan, lesson, prior_materials)
    return _generate_for_role(system, human, CodeLab, ROLE_BY_STEP["code_lab"])


def review_point(
    context: dict,
    plan: SectionTeachingPlan,
    draft: PointContent,
    *,
    require_revision: bool = True,
) -> ContentReview:
    system, human = review_point_messages(context, plan, draft)
    result = _generate_for_role(system, human, ContentReview, ROLE_BY_STEP["review"])
    definite_issues = language_issues(draft) + exercise_type_issues(draft) + grounding_issues(draft, context)
    if definite_issues:
        result = result.model_copy(update={"approved":False,
            "issues":[*result.issues,*definite_issues],
            "revision_instructions":[*result.revision_instructions,*definite_issues]})
    if require_revision and not result.approved and not result.revision_instructions:
        raise HTTPException(502, "AI 审查未给出可执行的修订意见。")
    return result


def revise_point(
    context: dict,
    plan: SectionTeachingPlan,
    draft: PointContent,
    review: ContentReview,
) -> PointContent:
    system, human = revise_point_messages(context, plan, draft, review)
    revised = _generate_for_role(
        system, human, ContentRevision, ROLE_BY_STEP["revision"]
    )
    return attach_evidence(PointContent(lesson_markdown=revised.lesson_markdown,
                                       **revised.model_dump(mode="json")), context)


def _lock_job(db: Session, job_id: int):
    peek = db.get(LearningGenerationJob, job_id)
    if peek is None:
        raise WorkflowAlreadyClaimed
    # 所有路径统一先锁 Course 再锁 Job，避免与新建任务的锁顺序相反。
    course = courses.get_course(db, peek.course_id, lock=True,
                                outline_version_id=peek.context_json.get("outline_version_id"))
    job = db.scalar(
        select(LearningGenerationJob)
        .where(LearningGenerationJob.id == job_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if job is None:
        raise WorkflowAlreadyClaimed
    return job, course


def _assert_current(db: Session, job: LearningGenerationJob, course) -> None:
    try:
        current = learning.build_generation_context(
            db,
            job.course_id,
            job.point_id,
            loaded_course=course,
            routing_snapshot=job.routing_snapshot_json,
        )
    except HTTPException as error:
        raise StaleGeneration from error
    if (
        current.structure_hash != job.structure_hash
        or current.section.id != job.section_id
        or current.selected_version_id != job.expected_selected_version_id
    ):
        raise StaleGeneration


def _validate_plan(plan: SectionTeachingPlan, context: dict) -> None:
    expected = [item["id"] for item in context["target_section"]["points"]]
    actual = [item.point_id for item in plan.point_plans]
    if actual != expected:
        raise HTTPException(502, "AI 规划未完整按顺序覆盖当前小节的知识点。")
    ordered_point_ids = [
        point["id"]
        for chapter in context["course_outline"]["chapters"]
        for section in chapter["sections"]
        for point in section["points"]
    ]
    for item in plan.point_plans:
        prerequisites = item.prerequisite_point_ids
        if (
            len(prerequisites) != len(set(prerequisites))
            or item.point_id in prerequisites
            or any(
                point_id not in ordered_point_ids[:ordered_point_ids.index(item.point_id)]
                for point_id in prerequisites
            )
        ):
            raise HTTPException(502, "AI 规划包含无效的先修知识点。")


def _target_plan(
    plan: SectionTeachingPlan, context: dict
) -> PointPlanItem:
    point_id = context["target_point"]["id"]
    item = next(
        (candidate for candidate in plan.point_plans if candidate.point_id == point_id),
        None,
    )
    if item is None:
        raise HTTPException(502, "AI 规划中没有当前知识点。")
    return item


def _validate_content_components(
    content: PointContent, point_plan: PointPlanItem
) -> None:
    if not content.learning_goals or not content.lesson_cards:
        raise HTTPException(502, "AI 内容缺少简明学习目标或分步讲解卡片。")
    checks = (
        (point_plan.example_plan.needed, bool(content.examples), "示例"),
        (point_plan.exercise_plan.needed, bool(content.exercises), "练习"),
        (point_plan.code_lab_plan.needed, content.code_lab is not None, "代码实验"),
    )
    for needed, present, label in checks:
        if needed != present:
            expectation = "缺少" if needed else "多生成了"
            raise HTTPException(502, f"AI 内容{expectation}规划中的{label}。")


def _claim_job(bind, job_id: int) -> bool:
    with Session(bind) as db:
        job, course = _lock_job(db, job_id)
        if job.status != "queued":
            return False
        _assert_current(db, job, course)
        # One immutable evidence snapshot per job. Do not retrieve on ordinary
        # content reads, or overwrite the snapshot during retry/revision.
        if "material_evidence" not in job.context_json:
            try:
                evidence = collect_evidence(db, job.course_id, job.outline_version_id, job.context_json)
            except HTTPException as error:
                raise MaterialEvidenceError("原文资料范围或解析版本不可用，已停止制作。请到参考资料核对；当前内容保持不变。") from error
            job.context_json = {**job.context_json, "material_evidence": evidence}
            job.context_hash = _step_hash(job.context_json)
        job.status = "planning"
        db.commit()
        return True


def _get_or_generate_plan(bind, job_id: int) -> SectionTeachingPlan:
    with Session(bind) as db:
        job, course = _lock_job(db, job_id)
        if job.status != "planning":
            raise WorkflowAlreadyClaimed
        _assert_current(db, job, course)
        existing = db.scalar(
            select(SectionPlan).where(
                SectionPlan.section_id == job.section_id,
                SectionPlan.context_hash == job.structure_hash,
            )
        )
        if existing is not None:
            plan = SectionTeachingPlan.model_validate(existing.plan_json)
            job.plan_id = existing.id
            job.status = "writing"
            db.commit()
            return plan
        context = deepcopy(job.context_json)

    # 模型等待发生在 Session 之外，不占用事务或行锁。
    planning_payload = learning.planning_context(context)
    plan = _checkpointed_model(
        bind, job_id, step_key="plan", role_key=ROLE_BY_STEP["plan"], expected_status="planning",
        input_payload=planning_payload, schema=SectionTeachingPlan,
        call=lambda: plan_section(planning_payload),
    )
    _validate_plan(plan, context)

    with Session(bind) as db:
        job, course = _lock_job(db, job_id)
        if job.status != "planning":
            raise WorkflowAlreadyClaimed
        _assert_current(db, job, course)
        existing = db.scalar(
            select(SectionPlan).where(
                SectionPlan.section_id == job.section_id,
                SectionPlan.context_hash == job.structure_hash,
            )
        )
        if existing is None:
            latest = db.scalar(
                select(func.max(SectionPlan.version_number)).where(
                    SectionPlan.section_id == job.section_id
                )
            )
            existing = SectionPlan(
                section_id=job.section_id,
                version_number=(latest or 0) + 1,
                context_hash=job.structure_hash,
                plan_json=plan.model_dump(mode="json"),
                prompt_version=learning.PROMPT_VERSIONS["planner"],
            )
            db.add(existing)
            db.flush()
        job.plan_id = existing.id
        job.status = "writing"
        db.commit()
        saved_plan_json = deepcopy(existing.plan_json)
    return SectionTeachingPlan.model_validate(saved_plan_json)


def _job_snapshot(bind, job_id: int, expected_status: str) -> tuple[dict, int]:
    with Session(bind) as db:
        job, course = _lock_job(db, job_id)
        if job.status != expected_status or job.plan_id is None:
            raise WorkflowAlreadyClaimed
        _assert_current(db, job, course)
        return deepcopy(job.context_json), job.plan_id


def _advance(
    bind,
    job_id: int,
    *,
    expected_status: str,
    next_status: str,
    revision_count: int | None = None,
) -> None:
    with Session(bind) as db:
        job, course = _lock_job(db, job_id)
        if job.status != expected_status:
            raise WorkflowAlreadyClaimed
        _assert_current(db, job, course)
        job.status = next_status
        if revision_count is not None:
            job.revision_count = revision_count
        db.commit()


def _save_candidate(
    bind,
    job_id: int,
    draft: PointContent,
    review: ContentReview,
) -> None:
    with Session(bind) as db:
        job, course = _lock_job(db, job_id)
        if job.status != "reviewing" or job.plan_id is None:
            raise WorkflowAlreadyClaimed
        _assert_current(db, job, course)
        draft = attach_evidence(draft, job.context_json)
        issues = grounding_issues(draft, job.context_json)
        if issues:
            review = review.model_copy(update={"approved": False,
                "issues": [*review.issues, *issues]})
            job.error = "资料依据校验未通过：" + "；".join(issues)
        elif not review.approved:
            job.error = "本次内容未发布：" + ("；".join(review.issues)[:1800] or "自动审查仍有待解决的问题，当前内容保持不变。")
        latest = db.scalar(
            select(func.max(PointContentVersion.version_number)).where(
                PointContentVersion.point_id == job.point_id
            )
        )
        status = "ready" if review.approved else "needs_review"
        version = PointContentVersion(
            point_id=job.point_id,
            plan_id=job.plan_id,
            version_number=(latest or 0) + 1,
            status=status,
            origin="generated",
            content_json=draft.model_dump(mode="json"),
            review_json=review.model_dump(mode="json"),
            revision_count=job.revision_count,
            context_hash=job.context_hash,
        )
        db.add(version)
        db.flush()
        job.content_version_id = version.id
        job.status = status
        if review.approved:
            # _assert_current 已检查启动时的内容选择；切换目录不会改变发布目标。
            versions.select_content(db, job.point_id, version.id, job.context_json.get("outline_version_id"))
        db.commit()


def _fail_job(bind, job_id: int, *, code: str, message: str) -> None:
    try:
        with Session(bind) as db:
            job, _ = _lock_job(db, job_id)
            if job.status in learning.ACTIVE_JOB_STATUSES:
                job.status = "failed"
                job.error_code = code
                job.error = message
                db.commit()
    except Exception as error:
        logging.getLogger(__name__).error(
            "Could not persist learning job failure: %s", type(error).__name__
        )


def run_learning_job(job_id: int, bind) -> None:
    """BackgroundTasks 入口；只接收 ID/Engine，不复用 HTTP Session。"""
    try:
        if not _claim_job(bind, job_id):
            return
        plan = _get_or_generate_plan(bind, job_id)

        context, _ = _job_snapshot(bind, job_id, "writing")
        point_plan = _target_plan(plan, context)
        base_input = {"context_hash": _step_hash(context), "plan": plan.model_dump(mode="json")}
        lesson = _checkpointed_model(
            bind, job_id, step_key="lesson", role_key=ROLE_BY_STEP["lesson"], expected_status="writing",
            input_payload=base_input, schema=LessonDraft,
            call=lambda: write_lesson(context, plan),
        )

        if context.get("material_evidence", {}).get("method") == "keyword" and lesson.source_gaps:
            # Missing source material cannot be repaired by another paid writer.
            # Keep a non-published candidate and stop before optional components.
            draft = attach_evidence(PointContent(
                lesson_markdown=lesson.lesson_markdown, learning_goals=lesson.learning_goals,
                lesson_cards=lesson.lesson_cards, summary=lesson.summary,
                source_gaps=lesson.source_gaps), context)
            _advance(bind, job_id, expected_status="writing", next_status="reviewing")
            _save_candidate(bind, job_id, draft, ContentReview(approved=False,
                issues=["当前知识点缺少必要原文，已停止后续制作。"],
                revision_instructions=["请核对资料范围，补齐必要材料后在新版本中重新生成。无需反复重试同一份资料。 "]))
            return

        # 每个专门 Agent 前后都重读任务。关闭页面不改变任务；
        # 用户主动取消时，当前模型请求即使稍后返回也不会再启动下一节点或保存。
        _job_snapshot(bind, job_id, "writing")
        examples = []
        if point_plan.example_plan.needed:
            example_set = _checkpointed_model(
                bind, job_id, step_key="examples", role_key=ROLE_BY_STEP["examples"], expected_status="writing",
                input_payload={**base_input, "lesson": lesson.model_dump(mode="json")},
                schema=ExampleSet, call=lambda: write_examples(context, plan, lesson),
            )
            examples = example_set.examples
            _job_snapshot(bind, job_id, "writing")

        exercises = []
        if point_plan.exercise_plan.needed:
            serialized_examples = [item.model_dump(mode="json") for item in examples]
            exercise_set = _checkpointed_model(
                bind, job_id, step_key="exercises", role_key=ROLE_BY_STEP["exercises"], expected_status="writing",
                input_payload={**base_input, "lesson": lesson.model_dump(mode="json"),
                               "examples": serialized_examples}, schema=ExerciseSet,
                call=lambda: write_exercises(context, plan, lesson, serialized_examples),
            )
            exercises = exercise_set.exercises
            _job_snapshot(bind, job_id, "writing")

        code_lab = None
        if point_plan.code_lab_plan.needed:
            prior_materials = {
                "examples": [item.model_dump(mode="json") for item in examples],
                "exercises": [item.model_dump(mode="json") for item in exercises],
            }
            code_lab = _checkpointed_model(
                bind, job_id, step_key="code_lab", role_key=ROLE_BY_STEP["code_lab"], expected_status="writing",
                input_payload={**base_input, "lesson": lesson.model_dump(mode="json"),
                               "prior_materials": prior_materials}, schema=CodeLab,
                call=lambda: write_code_lab(context, plan, lesson, prior_materials),
            )
            _job_snapshot(bind, job_id, "writing")

        draft = PointContent(
            lesson_markdown=lesson.lesson_markdown,
            learning_goals=lesson.learning_goals,
            lesson_cards=lesson.lesson_cards,
            examples=examples,
            exercises=exercises,
            code_lab=code_lab,
            summary=lesson.summary,
            source_gaps=lesson.source_gaps,
        )
        draft = attach_evidence(draft, context)
        _validate_content_components(draft, point_plan)
        _advance(
            bind,
            job_id,
            expected_status="writing",
            next_status="reviewing",
        )

        context, _ = _job_snapshot(bind, job_id, "reviewing")
        review = _checkpointed_model(
            bind, job_id, step_key="review_0", role_key=ROLE_BY_STEP["review"], expected_status="reviewing",
            input_payload={**base_input, "draft": draft.model_dump(mode="json")},
            schema=ContentReview, call=lambda: review_point(context, plan, draft),
        )
        if not review.approved:
            _advance(
                bind,
                job_id,
                expected_status="reviewing",
                next_status="revising",
                revision_count=1,
            )
            context, _ = _job_snapshot(bind, job_id, "revising")
            draft = _checkpointed_model(
                bind, job_id, step_key="revision_1", role_key=ROLE_BY_STEP["revision"], expected_status="revising",
                input_payload={**base_input, "draft": draft.model_dump(mode="json"),
                               "review": review.model_dump(mode="json")},
                schema=PointContent, call=lambda: revise_point(context, plan, draft, review),
            )
            _validate_content_components(draft, point_plan)
            _advance(
                bind,
                job_id,
                expected_status="revising",
                next_status="reviewing",
            )
            context, _ = _job_snapshot(bind, job_id, "reviewing")
            review = _checkpointed_model(
                bind, job_id, step_key="review_1", role_key=ROLE_BY_STEP["review"], expected_status="reviewing",
                input_payload={**base_input, "draft": draft.model_dump(mode="json")},
                schema=ContentReview,
                call=lambda: review_point(context, plan, draft, require_revision=False),
            )

        _save_candidate(bind, job_id, draft, review)
    except MaterialEvidenceError as error:
        _fail_job(bind, job_id, code="material_evidence_unavailable", message=str(error))
    except WorkflowAlreadyClaimed:
        return
    except StaleGeneration:
        _fail_job(
            bind,
            job_id,
            code="stale_context",
            message="生成期间课程结构、需求档案或已选内容已变化，本次结果未保存。",
        )
    except HTTPException:
        _fail_job(
            bind,
            job_id,
            code="model_output_invalid",
            message="AI 生成或校验失败，已选内容保持不变。",
        )
    except Exception as error:
        logging.getLogger(__name__).error(
            "Learning workflow failed: %s", type(error).__name__
        )
        _fail_job(
            bind,
            job_id,
            code="internal_error",
            message="内容制作暂时失败，已选内容保持不变。",
        )
