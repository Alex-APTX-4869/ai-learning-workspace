import json
import tempfile
import unittest
from copy import deepcopy
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from backend.app import create_app
from backend.courses.models import Chapter, Course, Point, Section
from backend.database import Base, get_db
from backend.intake.models import IntakeSession
from backend.learning.models import (
    LearningGenerationJob,
    LearningJobStep,
    PointContentSelection,
    PointContentVersion,
    SectionPlan,
)
from backend.learning.service import cancel_job, recover_interrupted_jobs
from backend.learning.schemas import (
    CodeLab,
    ContentReview,
    ContentRevision,
    ExampleSet,
    ExerciseSet,
    LessonDraft,
    PointContent,
    SectionTeachingPlan,
)
from backend.workflows.content import run_learning_job


BRIEF = {
    "course_name": "FastAPI 实战",
    "summary": "从基础到真实 API。",
    "learner_profile": "会 Python，还不熟悉 Web 开发。",
    "learning_outcomes": ["能实现并解释 API"],
    "scope_in": ["HTTP", "FastAPI"],
    "scope_out": ["分布式部署"],
    "learning_preferences": ["讲解后实践"],
    "constraints": ["每晚一小时"],
    "success_criteria": ["完成可调用的课程 API"],
}

CONTENT = {
    "lesson_markdown": "## 请求与响应\n\n浏览器向服务端发出请求。",
    "learning_goals": ["解释请求与响应的关系。"],
    "lesson_cards": [{"title": "请求与响应", "body_markdown": "浏览器向服务端发出请求。"}],
    "examples": [
        {
            "title": "最小路由",
            "explanation_markdown": "这个函数返回 JSON。",
            "code": "@app.get('/')\ndef root(): return {'ok': True}",
            "language": "python",
        }
    ],
    "exercises": [
        {
            "kind": "short_answer",
            "question": "写一个返回课程名的 GET 路由。",
            "options": [],
            "hint": "使用 @app.get。",
            "answer": "`return {'name': 'FastAPI'}`",
            "explanation": "字典会被序列化为 JSON。",
        }
    ],
    "code_lab": None,
    "summary": "一次 Web 交互由请求和响应组成。",
}

CODE_LAB = {
    "title": "实现状态码分类",
    "instructions_markdown": "补全函数，返回状态码所属类别。",
    "language": "python",
    "starter_code": "def status_family(code):\n    # TODO\n    pass",
    "solution_code": "def status_family(code):\n    return code // 100",
    "tests": [
        {"name": "200 属于 2xx", "assertion_code": "assert status_family(200) == 2"}
    ],
}


class LearningWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = create_engine(
            f"sqlite:///{self.temp.name}/test.db",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(self.engine)
        app = create_app(initialize_database=False, inline_jobs=True)

        def database():
            with Session(self.engine) as db:
                yield db

        app.dependency_overrides[get_db] = database
        self.client = TestClient(app)
        with Session(self.engine) as db:
            course = Course(
                name="FastAPI",
                intro="完成一个真实课程 API",
                chapters=[
                    Chapter(
                        name="Web 基础",
                        position=0,
                        sections=[
                            Section(
                                name="请求与响应",
                                position=0,
                                points=[
                                    Point(
                                        name="HTTP 流程",
                                        intro="理解客户端和服务端交互。",
                                        position=0,
                                    ),
                                    Point(
                                        name="状态码",
                                        intro="理解响应状态。",
                                        position=1,
                                    ),
                                ],
                            )
                        ],
                    ),
                    Chapter(
                        name="FastAPI 路由",
                        position=1,
                        sections=[
                            Section(
                                name="GET 接口",
                                position=0,
                                points=[
                                    Point(
                                        name="路径操作",
                                        intro="定义 GET 接口。",
                                        position=0,
                                    )
                                ],
                            )
                        ],
                    ),
                ],
            )
            db.add(course)
            db.flush()
            db.add(
                IntakeSession(
                    initial_name=course.name,
                    initial_intro=course.intro,
                    status="completed",
                    depth_options=[],
                    brief=deepcopy(BRIEF),
                    course_id=course.id,
                    version=1,
                )
            )
            db.commit()
            self.course_id = course.id
            self.section_id = course.chapters[0].sections[0].id
            self.point_ids = [item.id for item in course.chapters[0].sections[0].points]
            self.other_point_id = course.chapters[1].sections[0].points[0].id

    def tearDown(self):
        self.client.close()
        self.engine.dispose()
        self.temp.cleanup()

    def plan(self):
        return SectionTeachingPlan.model_validate(
            {
                "section_goal": "理解 HTTP 交互并能判断响应结果。",
                "point_plans": [
                    {
                        "point_id": self.point_ids[0],
                        "learning_objective": "解释请求响应流程。",
                        "scope_in": ["客户端", "服务端"],
                        "scope_out": ["状态码分类"],
                        "prerequisite_point_ids": [],
                        "example_plan": {
                            "needed": True,
                            "reason": "具体请求链路有助于理解。",
                            "goal": "跟踪一次 GET 请求。",
                        },
                        "exercise_plan": {
                            "needed": True,
                            "reason": "需要检验交互顺序。",
                            "goal": "能排列交互步骤。",
                        },
                        "code_lab_plan": {
                            "needed": False,
                            "reason": "这个概念不需要独立 Python 实验。",
                        },
                    },
                    {
                        "point_id": self.point_ids[1],
                        "learning_objective": "根据状态码判断结果。",
                        "scope_in": ["常用状态码"],
                        "scope_out": ["重讲完整请求流程"],
                        "prerequisite_point_ids": [self.point_ids[0]],
                        "example_plan": {
                            "needed": True,
                            "reason": "对比能显示状态差异。",
                            "goal": "比较成功和失败响应。",
                        },
                        "exercise_plan": {
                            "needed": True,
                            "reason": "状态码适合客观题检验。",
                            "goal": "能选择合适状态码。",
                        },
                        "code_lab_plan": {
                            "needed": False,
                            "reason": "不需要独立 Python 实验。",
                        },
                    },
                ],
            }
        )

    def approved(self):
        return ContentReview(approved=True)

    def plan_for_components(
        self, *, examples: bool, exercises: bool, code_lab: bool
    ):
        data = self.plan().model_dump(mode="json")
        target = data["point_plans"][0]
        target["example_plan"]["needed"] = examples
        target["exercise_plan"]["needed"] = exercises
        target["code_lab_plan"]["needed"] = code_lab
        target["example_plan"]["goal"] = "用有效示例帮助理解。" if examples else None
        target["exercise_plan"]["goal"] = "检验是否掌握该知识点。" if exercises else None
        target["code_lab_plan"]["goal"] = "用最小 Python 实验掌握核心逻辑。" if code_lab else None
        return SectionTeachingPlan.model_validate(data)

    def lesson(self, content=None):
        value = content or CONTENT
        return LessonDraft(
            learning_goals=value["learning_goals"],
            lesson_cards=value["lesson_cards"],
            summary=value["summary"],
        )

    def example_set(self, content=None):
        return ExampleSet(examples=(content or CONTENT)["examples"])

    def exercise_set(self, content=None):
        return ExerciseSet(exercises=(content or CONTENT)["exercises"])

    def run_success(self, point_id=None, content=None):
        point_id = point_id or self.point_ids[0]
        value = content or CONTENT
        with (
            patch("backend.workflows.content.plan_section", return_value=self.plan()) as planner,
            patch(
                "backend.workflows.content.write_lesson",
                return_value=self.lesson(value),
            ) as writer,
            patch(
                "backend.workflows.content.write_examples",
                return_value=self.example_set(value),
            ),
            patch(
                "backend.workflows.content.write_exercises",
                return_value=self.exercise_set(value),
            ),
            patch("backend.workflows.content.write_code_lab") as code_writer,
            patch(
                "backend.workflows.content.review_point",
                return_value=self.approved(),
            ) as reviewer,
        ):
            reply = self.client.post(
                f"/courses/{self.course_id}/points/{point_id}/content/jobs"
            )
        self.assertEqual(reply.status_code, 202, reply.text)
        job = self.client.get(reply.headers["location"]).json()
        self.assertEqual(job["status"], "ready", job)
        code_writer.assert_not_called()
        return job, planner, writer, reviewer

    def test_success_includes_full_context_and_returns_structured_content(self):
        job, planner, writer, reviewer = self.run_success()
        self.assertEqual(job["revision_count"], 0)
        planning_input = planner.call_args.args[0]
        self.assertEqual(planning_input["course_brief"], BRIEF)
        self.assertEqual(len(planning_input["course_outline"]["chapters"]), 2)
        self.assertEqual(
            [item["id"] for item in planning_input["target_section"]["points"]],
            self.point_ids,
        )
        self.assertIn("existing_content_summaries", planning_input)
        writer.assert_called_once()
        reviewer.assert_called_once()

        reply = self.client.get(
            f"/courses/{self.course_id}/points/{self.point_ids[0]}/content"
        )
        self.assertEqual(reply.status_code, 200, reply.text)
        expected = PointContent.model_validate(CONTENT).model_dump(mode="json")
        expected["material_evidence"] = {"method": "none", "sources": []}
        self.assertEqual(reply.json()["content"], expected)
        self.assertTrue(reply.json()["review"]["approved"])
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count(SectionPlan.id))), 1)
            self.assertEqual(db.scalar(select(func.count(PointContentVersion.id))), 1)

    def test_planner_can_skip_all_optional_content_agents(self):
        plan = self.plan_for_components(
            examples=False, exercises=False, code_lab=False
        )
        with (
            patch("backend.workflows.content.plan_section", return_value=plan),
            patch(
                "backend.workflows.content.write_lesson",
                return_value=self.lesson(),
            ),
            patch("backend.workflows.content.write_examples") as examples,
            patch("backend.workflows.content.write_exercises") as exercises,
            patch("backend.workflows.content.write_code_lab") as code_lab,
            patch(
                "backend.workflows.content.review_point",
                return_value=self.approved(),
            ),
        ):
            reply = self.client.post(
                f"/courses/{self.course_id}/points/{self.point_ids[0]}/content/jobs"
            )
        self.assertEqual(reply.status_code, 202, reply.text)
        examples.assert_not_called()
        exercises.assert_not_called()
        code_lab.assert_not_called()
        content = self.client.get(
            f"/courses/{self.course_id}/points/{self.point_ids[0]}/content"
        ).json()["content"]
        self.assertEqual(content["examples"], [])
        self.assertEqual(content["exercises"], [])
        self.assertIsNone(content["code_lab"])

    def test_code_lab_agent_only_runs_when_planner_requests_it(self):
        plan = self.plan_for_components(
            examples=False, exercises=False, code_lab=True
        )
        with (
            patch("backend.workflows.content.plan_section", return_value=plan),
            patch(
                "backend.workflows.content.write_lesson",
                return_value=self.lesson(),
            ),
            patch("backend.workflows.content.write_examples") as examples,
            patch("backend.workflows.content.write_exercises") as exercises,
            patch(
                "backend.workflows.content.write_code_lab",
                return_value=CodeLab.model_validate(CODE_LAB),
            ) as code_lab,
            patch(
                "backend.workflows.content.review_point",
                return_value=self.approved(),
            ),
        ):
            reply = self.client.post(
                f"/courses/{self.course_id}/points/{self.point_ids[0]}/content/jobs"
            )
        self.assertEqual(reply.status_code, 202, reply.text)
        examples.assert_not_called()
        exercises.assert_not_called()
        code_lab.assert_called_once()
        content = self.client.get(
            f"/courses/{self.course_id}/points/{self.point_ids[0]}/content"
        ).json()["content"]
        self.assertEqual(content["code_lab"], CodeLab.model_validate(CODE_LAB).model_dump(mode="json"))

    def test_section_plan_is_reused_and_existing_summary_reaches_next_writer(self):
        self.run_success(self.point_ids[0])
        captured = {}

        def write(context, plan):
            captured["context"] = context
            return LessonDraft(
                learning_goals=CONTENT["learning_goals"],
                lesson_cards=CONTENT["lesson_cards"],
                summary="能根据状态码判断请求结果。",
            )

        with (
            patch("backend.workflows.content.plan_section") as planner,
            patch("backend.workflows.content.write_lesson", side_effect=write),
            patch(
                "backend.workflows.content.write_examples",
                return_value=self.example_set(),
            ),
            patch(
                "backend.workflows.content.write_exercises",
                return_value=self.exercise_set(),
            ),
            patch("backend.workflows.content.review_point", return_value=self.approved()),
        ):
            reply = self.client.post(
                f"/courses/{self.course_id}/points/{self.point_ids[1]}/content/jobs"
            )
        self.assertEqual(reply.status_code, 202, reply.text)
        job = self.client.get(reply.headers["location"]).json()
        self.assertEqual(job["status"], "ready", job)
        planner.assert_not_called()
        summaries = captured["context"]["existing_content_summaries"]
        self.assertEqual(summaries[0]["point_id"], self.point_ids[0])
        self.assertEqual(summaries[0]["summary"], CONTENT["summary"])
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count(SectionPlan.id))), 1)

    def test_review_allows_exactly_one_revision(self):
        revised = PointContent.model_validate(
            {**CONTENT, "summary": "修订后的准确总结。"}
        )
        reviews = [
            ContentReview(
                approved=False,
                issues=["总结不够准确"],
                revision_instructions=["改写总结"],
            ),
            ContentReview(approved=True),
        ]
        with (
            patch("backend.workflows.content.plan_section", return_value=self.plan()),
            patch(
                "backend.workflows.content.write_lesson",
                return_value=self.lesson(),
            ),
            patch("backend.workflows.content.write_examples", return_value=self.example_set()),
            patch("backend.workflows.content.write_exercises", return_value=self.exercise_set()),
            patch("backend.workflows.content.review_point", side_effect=reviews) as reviewer,
            patch("backend.workflows.content.revise_point", return_value=revised) as reviser,
        ):
            reply = self.client.post(
                f"/courses/{self.course_id}/points/{self.point_ids[0]}/content/jobs"
            )
        job = self.client.get(reply.headers["location"]).json()
        self.assertEqual(job["status"], "ready", job)
        self.assertEqual(job["revision_count"], 1)
        self.assertEqual(reviewer.call_count, 2)
        reviser.assert_called_once()
        content = self.client.get(
            f"/courses/{self.course_id}/points/{self.point_ids[0]}/content"
        ).json()
        self.assertEqual(content["content"]["summary"], "修订后的准确总结。")

    def test_second_rejection_is_needs_review_and_does_not_select_candidate(self):
        rejected = ContentReview(
            approved=False,
            issues=["仍与其他知识点重复"],
            revision_instructions=[],
        )
        first = ContentReview(
            approved=False,
            issues=["内容重复"],
            revision_instructions=["删除重复范围"],
        )
        with (
            patch("backend.workflows.content.plan_section", return_value=self.plan()),
            patch(
                "backend.workflows.content.write_lesson",
                return_value=self.lesson(),
            ),
            patch("backend.workflows.content.write_examples", return_value=self.example_set()),
            patch("backend.workflows.content.write_exercises", return_value=self.exercise_set()),
            patch("backend.workflows.content.review_point", side_effect=[first, rejected]) as reviewer,
            patch(
                "backend.workflows.content.revise_point",
                return_value=PointContent.model_validate(CONTENT),
            ) as reviser,
        ):
            reply = self.client.post(
                f"/courses/{self.course_id}/points/{self.point_ids[0]}/content/jobs"
            )
        job = self.client.get(reply.headers["location"]).json()
        self.assertEqual(job["status"], "needs_review", job)
        self.assertEqual(reviewer.call_count, 2)
        reviser.assert_called_once()
        self.assertEqual(
            self.client.get(
                f"/courses/{self.course_id}/points/{self.point_ids[0]}/content"
            ).status_code,
            404,
        )
        with Session(self.engine) as db:
            candidate = db.get(PointContentVersion, job["content_version_id"])
            self.assertEqual(candidate.status, "needs_review")
            self.assertIsNone(db.get(PointContentSelection, self.point_ids[0]))

    def test_failure_does_not_replace_selected_content_or_expose_exception(self):
        original, *_ = self.run_success()
        with (
            patch("backend.workflows.content.write_lesson", side_effect=RuntimeError("PRIVATE_SENTINEL")),
            patch("backend.workflows.content.plan_section") as planner,
        ):
            reply = self.client.post(
                f"/courses/{self.course_id}/points/{self.point_ids[0]}/content/jobs"
            )
        job = self.client.get(reply.headers["location"]).json()
        self.assertEqual(job["status"], "failed", job)
        self.assertNotIn("PRIVATE_SENTINEL", json.dumps(job))
        planner.assert_not_called()  # 相同结构直接复用 section plan。
        current = self.client.get(
            f"/courses/{self.course_id}/points/{self.point_ids[0]}/content"
        ).json()
        self.assertEqual(current["id"], original["content_version_id"])

    def test_active_job_is_idempotent_and_blocks_other_point_in_section(self):
        # 暂停调度器，让第一个任务保持 queued。
        with patch("backend.learning.router.run_learning_job") as runner:
            first = self.client.post(
                f"/courses/{self.course_id}/points/{self.point_ids[0]}/content/jobs"
            )
            repeated = self.client.post(
                f"/courses/{self.course_id}/points/{self.point_ids[0]}/content/jobs"
            )
            blocked = self.client.post(
                f"/courses/{self.course_id}/points/{self.point_ids[1]}/content/jobs"
            )
        self.assertEqual(first.status_code, 202, first.text)
        self.assertEqual(repeated.status_code, 202, repeated.text)
        self.assertEqual(first.json()["id"], repeated.json()["id"])
        self.assertEqual(blocked.status_code, 409, blocked.text)
        runner.assert_called_once()
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count(LearningGenerationJob.id))), 1)

    def test_active_job_can_be_rediscovered_and_only_explicit_cancel_stops_it(self):
        with patch("backend.learning.router.run_learning_job"):
            created = self.client.post(
                f"/courses/{self.course_id}/points/{self.point_ids[0]}/content/jobs"
            )
        job_id = created.json()["id"]
        active = self.client.get(
            f"/courses/{self.course_id}/points/{self.point_ids[0]}/content/jobs/active"
        )
        self.assertEqual(active.status_code, 200, active.text)
        self.assertEqual(active.json()["id"], job_id)

        stopped = self.client.post(f"/learning-jobs/{job_id}/cancel")
        self.assertEqual(stopped.status_code, 200, stopped.text)
        self.assertEqual(stopped.json()["status"], "cancelled")
        self.assertIn("停止", stopped.json()["error"])
        self.assertIsNone(
            self.client.get(
                f"/courses/{self.course_id}/points/{self.point_ids[0]}/content/jobs/active"
            ).json()
        )

        # 取消后即使旧的后台入口被再次调度，也不会调用模型或保存。
        with patch("backend.workflows.content.plan_section") as planner:
            run_learning_job(job_id, self.engine)
        planner.assert_not_called()
        with Session(self.engine) as db:
            self.assertIsNone(db.get(PointContentSelection, self.point_ids[0]))

        with patch("backend.learning.router.run_learning_job"):
            retry = self.client.post(
                f"/courses/{self.course_id}/points/{self.point_ids[0]}/content/jobs"
            )
        self.assertNotEqual(retry.json()["id"], job_id)

    def test_cancel_during_agent_call_discards_its_late_result(self):
        def cancel_while_writing(context, plan):
            with Session(self.engine) as db:
                active = db.scalar(
                    select(LearningGenerationJob).where(
                        LearningGenerationJob.status == "writing"
                    )
                )
                cancel_job(db, active.id)
            # 模型请求可能已在途中；即使稍后返回也必须丢弃。
            return self.lesson()

        with (
            patch("backend.workflows.content.plan_section", return_value=self.plan()),
            patch(
                "backend.workflows.content.write_lesson",
                side_effect=cancel_while_writing,
            ),
            patch("backend.workflows.content.write_examples") as examples,
            patch("backend.workflows.content.write_exercises") as exercises,
            patch("backend.workflows.content.write_code_lab") as code_lab,
            patch("backend.workflows.content.review_point") as reviewer,
        ):
            reply = self.client.post(
                f"/courses/{self.course_id}/points/{self.point_ids[0]}/content/jobs"
            )
        job = self.client.get(reply.headers["location"]).json()
        self.assertEqual(job["status"], "cancelled", job)
        examples.assert_not_called()
        exercises.assert_not_called()
        code_lab.assert_not_called()
        reviewer.assert_not_called()
        with Session(self.engine) as db:
            self.assertIsNone(db.scalar(select(PointContentVersion.id)))

    def test_point_from_another_course_is_rejected_before_scheduling(self):
        with Session(self.engine) as db:
            other = Course(name="Vue", intro="前端", chapters=[])
            db.add(other)
            db.commit()
            other_id = other.id
        with patch("backend.learning.router.run_learning_job") as runner:
            reply = self.client.post(
                f"/courses/{other_id}/points/{self.point_ids[0]}/content/jobs"
            )
        self.assertEqual(reply.status_code, 404, reply.text)
        runner.assert_not_called()

    def test_brief_change_during_model_call_marks_job_failed_without_save(self):
        def change_brief(context, plan):
            with Session(self.engine) as db:
                intake = db.scalar(
                    select(IntakeSession).where(
                        IntakeSession.course_id == self.course_id
                    )
                )
                changed = deepcopy(intake.brief)
                changed["summary"] = "已经修改的需求"
                intake.brief = changed
                db.commit()
            return self.lesson()

        with (
            patch("backend.workflows.content.plan_section", return_value=self.plan()),
            patch("backend.workflows.content.write_lesson", side_effect=change_brief),
            patch("backend.workflows.content.review_point") as reviewer,
        ):
            reply = self.client.post(
                f"/courses/{self.course_id}/points/{self.point_ids[0]}/content/jobs"
            )
        job = self.client.get(reply.headers["location"]).json()
        self.assertEqual(job["status"], "failed", job)
        self.assertIn("需求档案", job["error"])
        reviewer.assert_not_called()
        with Session(self.engine) as db:
            self.assertIsNone(db.scalar(select(PointContentVersion.id)))

    def test_point_change_during_model_call_marks_job_failed_without_save(self):
        def change_point(context, plan):
            with Session(self.engine) as db:
                point = db.get(Point, self.point_ids[0])
                point.name = "被修改的知识点"
                db.commit()
            return self.lesson()

        with (
            patch("backend.workflows.content.plan_section", return_value=self.plan()),
            patch("backend.workflows.content.write_lesson", side_effect=change_point),
            patch("backend.workflows.content.review_point") as reviewer,
        ):
            reply = self.client.post(
                f"/courses/{self.course_id}/points/{self.point_ids[0]}/content/jobs"
            )
        job = self.client.get(reply.headers["location"]).json()
        self.assertEqual(job["status"], "failed", job)
        self.assertIn("课程结构", job["error"])
        reviewer.assert_not_called()

    def test_other_point_summary_update_does_not_invalidate_context_snapshot(self):
        def publish_other(context, plan):
            with Session(self.engine) as db:
                version = PointContentVersion(point_id=self.other_point_id, version_number=1,
                    status="ready", origin="generated", content_json=deepcopy(CONTENT),
                    review_json={"approved": True}, context_hash="parallel-work")
                db.add(version)
                db.flush()
                db.add(PointContentSelection(point_id=self.other_point_id, version_id=version.id))
                db.commit()
            return self.lesson()

        with (
            patch("backend.workflows.content.plan_section", return_value=self.plan_for_components(examples=False, exercises=False, code_lab=False)),
            patch("backend.workflows.content.write_lesson", side_effect=publish_other),
            patch("backend.workflows.content.review_point", return_value=self.approved()),
        ):
            reply = self.client.post(f"/courses/{self.course_id}/points/{self.point_ids[0]}/content/jobs")
        job = self.client.get(reply.headers["location"]).json()
        self.assertEqual(job["status"], "ready", job)
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count(PointContentSelection.point_id))), 2)

    def test_forward_prerequisite_is_rejected_before_writing(self):
        plan = self.plan()
        plan.point_plans[0].prerequisite_point_ids = [self.point_ids[1]]
        with (
            patch("backend.workflows.content.plan_section", return_value=plan),
            patch("backend.workflows.content.write_lesson") as writer,
        ):
            reply = self.client.post(f"/courses/{self.course_id}/points/{self.point_ids[0]}/content/jobs")
        job = self.client.get(reply.headers["location"]).json()
        self.assertEqual(job["status"], "failed")
        self.assertIn("校验", job["error"])
        writer.assert_not_called()

    def test_revision_uses_cards_as_single_source_for_reading_view(self):
        from backend.workflows.content import revise_point
        from backend.learning.prompts import revise_point_messages
        draft = PointContent.model_validate(CONTENT)
        payload = deepcopy(CONTENT)
        payload.pop("lesson_markdown")
        payload["lesson_cards"][0]["body_markdown"] = "修订后的卡片正文。"
        revision = ContentRevision.model_validate(payload)
        with patch("backend.workflows.content.generate_json_messages", return_value=revision) as model:
            result = revise_point({}, self.plan(), draft, self.approved())
        self.assertEqual(result.lesson_markdown, "## 请求与响应\n\n修订后的卡片正文。")
        self.assertIs(model.call_args.args[2], ContentRevision)
        system, human = revise_point_messages({}, self.plan(), draft, self.approved())
        self.assertNotIn("lesson_markdown", json.loads(human)["draft"])
        self.assertNotIn("lesson_markdown", ContentRevision.model_json_schema()["properties"])

    def test_selected_version_cas_prevents_background_overwrite(self):
        original, *_ = self.run_success()
        external_version_id = None

        def switch_selected(context, plan):
            nonlocal external_version_id
            with Session(self.engine) as db:
                current = db.get(PointContentVersion, original["content_version_id"])
                external = PointContentVersion(
                    point_id=self.point_ids[0],
                    plan_id=current.plan_id,
                    version_number=current.version_number + 1,
                    status="ready",
                    origin="generated",
                    # 摘要故意不变，确保是选中指针 CAS 而不是文本 hash 发现冲突。
                    content_json=deepcopy(CONTENT),
                    review_json=ContentReview(approved=True).model_dump(mode="json"),
                    revision_count=0,
                    context_hash="external",
                )
                db.add(external)
                db.flush()
                db.get(PointContentSelection, self.point_ids[0]).version_id = external.id
                external_version_id = external.id
                db.commit()
            return self.lesson()

        with (
            patch("backend.workflows.content.plan_section") as planner,
            patch("backend.workflows.content.write_lesson", side_effect=switch_selected),
            patch("backend.workflows.content.review_point") as reviewer,
        ):
            reply = self.client.post(
                f"/courses/{self.course_id}/points/{self.point_ids[0]}/content/jobs"
            )
        job = self.client.get(reply.headers["location"]).json()
        self.assertEqual(job["status"], "failed", job)
        planner.assert_not_called()
        reviewer.assert_not_called()
        current = self.client.get(
            f"/courses/{self.course_id}/points/{self.point_ids[0]}/content"
        ).json()
        self.assertEqual(current["id"], external_version_id)

    def test_brief_endpoint_returns_confirmed_brief_or_null(self):
        reply = self.client.get(f"/courses/{self.course_id}/brief")
        self.assertEqual(reply.status_code, 200, reply.text)
        self.assertEqual(reply.json(), BRIEF)
        with Session(self.engine) as db:
            plain = Course(name="旧课程", intro="无需求档案")
            db.add(plain)
            db.commit()
            plain_id = plain.id
        self.assertIsNone(self.client.get(f"/courses/{plain_id}/brief").json())
        self.assertEqual(self.client.get("/courses/999999/brief").status_code, 404)

    def test_restart_requeues_unsent_job_without_creating_duplicate(self):
        with patch("backend.learning.router.run_learning_job"):
            first = self.client.post(
                f"/courses/{self.course_id}/points/{self.point_ids[0]}/content/jobs"
            )
        self.assertEqual(first.json()["status"], "queued")
        self.assertEqual(recover_interrupted_jobs(self.engine), 1)
        interrupted = self.client.get(first.headers["location"]).json()
        self.assertEqual(interrupted["status"], "queued")
        self.assertIsNone(interrupted["error"])

        with patch("backend.learning.router.run_learning_job"):
            retry = self.client.post(
                f"/courses/{self.course_id}/points/{self.point_ids[0]}/content/jobs"
            )
        self.assertEqual(retry.status_code, 202, retry.text)
        self.assertEqual(retry.json()["id"], first.json()["id"])

    def test_restart_requires_confirmation_for_unknown_provider_result(self):
        with patch("backend.learning.router.run_learning_job"):
            first = self.client.post(
                f"/courses/{self.course_id}/points/{self.point_ids[0]}/content/jobs"
            )
        job_id = first.json()["id"]
        with Session(self.engine) as db:
            job = db.get(LearningGenerationJob, job_id)
            job.status = "writing"
            db.add(LearningJobStep(job_id=job_id, step_key="lesson", input_hash="x" * 64,
                                   status="running"))
            db.commit()
        self.assertEqual(recover_interrupted_jobs(self.engine), 1)
        interrupted = self.client.get(first.headers["location"]).json()
        self.assertEqual(interrupted["status"], "needs_attention")
        self.assertIn("重复计费", interrupted["error"])
        with patch("backend.learning.router.run_learning_job"):
            retried = self.client.post(f"/learning-jobs/{job_id}/retry")
        self.assertEqual(retried.status_code, 200, retried.text)
        self.assertEqual(retried.json()["status"], "queued")
        with Session(self.engine) as db:
            step = db.scalar(select(LearningJobStep).where(LearningJobStep.job_id == job_id))
            self.assertEqual(step.status, "retry_authorized")

    def test_legacy_markdown_is_exposed_without_fabricated_exercises(self):
        with Session(self.engine) as db:
            point = db.get(Point, self.point_ids[0])
            point.content_markdown = "# 旧讲义\n\n这是用户早期已保存的内容。"
            db.commit()
        reply = self.client.get(
            f"/courses/{self.course_id}/points/{self.point_ids[0]}/content"
        )
        self.assertEqual(reply.status_code, 200, reply.text)
        payload = reply.json()
        self.assertEqual(payload["origin"], "legacy")
        self.assertEqual(payload["content"]["exercises"], [])
        self.assertFalse(payload["review"]["approved"])
        self.assertIn("旧讲义", payload["content"]["lesson_markdown"])
        course = self.client.get(f"/courses/{self.course_id}").json()
        self.assertIn(
            "旧讲义",
            course["chapters"][0]["sections"][0]["points"][0]["content_markdown"],
        )


if __name__ == "__main__":
    unittest.main()
