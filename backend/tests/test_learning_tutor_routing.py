import json
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

# 登记所有外键相关的 ORM 模型。
from backend import app as _app  # noqa: F401
from backend.courses.models import Chapter, Course, Point, Section
from backend.database import Base
from backend.learning.models import LearningGenerationJob, SectionPlan
from backend.learning.schemas import ContentReview, LessonDraft, SectionTeachingPlan
from backend.learning.service import CONTENT_ROLE_KEYS, create_or_get_job
from backend.providers.models import LLMModelConfig, LLMRoleBinding, LlmProvider
from backend.providers.routing import legacy_capabilities
from backend.tutor.models import TutorTurn
from backend.tutor.schemas import TutorAction, TutorDecision
from backend.tutor.service import apply_action, start_session
from backend.tutor.workflow import run_tutor_turn
from backend.workflows.content import run_learning_job


class LearningTutorRoutingSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = create_engine(
            f"sqlite:///{self.temp.name}/routing.db",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(self.engine)
        with Session(self.engine) as db:
            self.course = Course(
                name="FastAPI",
                intro="学会构建 API。",
                chapters=[
                    Chapter(
                        name="Web",
                        position=0,
                        sections=[
                            Section(
                                name="HTTP",
                                position=0,
                                points=[
                                    Point(name="请求", intro="理解请求。", position=0),
                                    Point(name="响应", intro="理解响应。", position=1),
                                ],
                            )
                        ],
                    )
                ],
            )
            db.add(self.course)
            db.flush()
            self.course_id = self.course.id
            self.section_id = self.course.chapters[0].sections[0].id
            self.point_ids = [
                point.id for point in self.course.chapters[0].sections[0].points
            ]

            first_provider = LlmProvider(
                name="first",
                base_url="https://first.example/v1",
                model="legacy-first",
                key_ref="private-first-reference",
                is_active=False,
            )
            second_provider = LlmProvider(
                name="second",
                base_url="https://second.example/v1",
                model="legacy-second",
                key_ref="private-second-reference",
                is_active=False,
            )
            db.add_all([first_provider, second_provider])
            db.flush()
            first_model = LLMModelConfig(
                provider_id=first_provider.id,
                label="first model",
                model="model-before",
                capabilities_json=legacy_capabilities(),
                runtime_policy_json={},
                is_enabled=True,
                revision=1,
            )
            second_model = LLMModelConfig(
                provider_id=second_provider.id,
                label="second model",
                model="model-after",
                capabilities_json=legacy_capabilities(),
                runtime_policy_json={},
                is_enabled=True,
                revision=1,
            )
            db.add_all([first_model, second_model])
            db.flush()
            binding = LLMRoleBinding(
                scope_type="global",
                scope_id=None,
                scope_key="global",
                role_key="default.chat",
                model_config_id=first_model.id,
                revision=1,
            )
            db.add(binding)
            db.commit()
            self.binding_id = binding.id
            self.first_model_id = first_model.id
            self.second_model_id = second_model.id

    def tearDown(self):
        self.engine.dispose()
        self.temp.cleanup()

    def _switch_default(self, model_id: int) -> None:
        with Session(self.engine) as db:
            binding = db.get(LLMRoleBinding, self.binding_id)
            binding.model_config_id = model_id
            binding.revision += 1
            db.commit()

    def _plan(self) -> SectionTeachingPlan:
        return SectionTeachingPlan.model_validate(
            {
                "section_goal": "理解 HTTP 交互。",
                "point_plans": [
                    {
                        "point_id": point_id,
                        "learning_objective": f"理解知识点 {point_id}。",
                        "scope_in": ["核心概念"],
                        "scope_out": ["高级部署"],
                        "prerequisite_point_ids": self.point_ids[:index],
                        "example_plan": {"needed": False, "reason": "暂不需要。"},
                        "exercise_plan": {"needed": False, "reason": "暂不需要。"},
                        "code_lab_plan": {"needed": False, "reason": "暂不需要。"},
                    }
                    for index, point_id in enumerate(self.point_ids)
                ],
            }
        )

    @staticmethod
    def _lesson() -> LessonDraft:
        return LessonDraft(
            learning_goals=["说明请求与响应。"],
            lesson_cards=[
                {"title": "HTTP 交互", "body_markdown": "客户端发出请求。"}
            ],
            summary="请求与响应组成一次交互。",
        )

    def test_learning_job_freezes_every_role_and_planner_route_partitions_cache(self):
        with Session(self.engine) as db:
            first_job, created = create_or_get_job(
                db, self.course_id, self.point_ids[0]
            )
            self.assertTrue(created)
            first_job_id = first_job.id
            first_structure_hash = first_job.structure_hash
            snapshot = first_job.routing_snapshot_json

        self.assertEqual(set(snapshot["routes"]), set(CONTENT_ROLE_KEYS))
        self.assertTrue(
            all(route["model"] == "model-before" for route in snapshot["routes"].values())
        )
        serialized = json.dumps(snapshot, ensure_ascii=False)
        self.assertNotIn("private-first-reference", serialized)
        self.assertNotIn("api_key", serialized)
        self.assertNotIn("key_ref", serialized)

        # 任务入队后改默认绑定：旧任务仍必须全程使用旧快照。
        self._switch_default(self.second_model_id)
        calls: list[tuple[str, str]] = []

        def fake_model(_system, _human, schema, **kwargs):
            role = kwargs["role"]
            route = kwargs["snapshot"]["routes"][role]
            calls.append((role, route["model"]))
            if schema is SectionTeachingPlan:
                return self._plan()
            if schema is LessonDraft:
                return self._lesson()
            if schema is ContentReview:
                return ContentReview(approved=True)
            self.fail(f"未预期的模型输出类型：{schema}")

        with patch(
            "backend.workflows.content.generate_json_messages",
            side_effect=fake_model,
        ):
            run_learning_job(first_job_id, self.engine)
        self.assertEqual(
            calls,
            [
                ("content.plan", "model-before"),
                ("content.lesson", "model-before"),
                ("content.review", "model-before"),
            ],
        )

        # 新任务使用新规划模型，即使教学结构未变也不复用旧 SectionPlan。
        with Session(self.engine) as db:
            second_job, created = create_or_get_job(
                db, self.course_id, self.point_ids[1]
            )
            self.assertTrue(created)
            second_job_id = second_job.id
            self.assertNotEqual(second_job.structure_hash, first_structure_hash)
            self.assertEqual(
                second_job.routing_snapshot_json["routes"]["content.plan"]["model"],
                "model-after",
            )
        calls.clear()
        with patch(
            "backend.workflows.content.generate_json_messages",
            side_effect=fake_model,
        ):
            run_learning_job(second_job_id, self.engine)
        self.assertEqual(calls[0], ("content.plan", "model-after"))
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count(SectionPlan.id))), 2)
            jobs = db.scalars(
                select(LearningGenerationJob).order_by(LearningGenerationJob.id)
            ).all()
            self.assertEqual([job.status for job in jobs], ["ready", "ready"])

    def test_tutor_turn_keeps_enqueued_model_after_binding_switch(self):
        # 先生成一份可学习的内容。
        with Session(self.engine) as db:
            job, _ = create_or_get_job(db, self.course_id, self.point_ids[0])
            job_id = job.id

        def learning_model(_system, _human, schema, **_kwargs):
            if schema is SectionTeachingPlan:
                return self._plan()
            if schema is LessonDraft:
                return self._lesson()
            if schema is ContentReview:
                return ContentReview(approved=True)
            self.fail(f"未预期的模型输出类型：{schema}")

        with patch(
            "backend.workflows.content.generate_json_messages",
            side_effect=learning_model,
        ):
            run_learning_job(job_id, self.engine)

        with Session(self.engine) as db:
            state = start_session(db, self.course_id, self.point_ids[0])
            action = TutorAction(
                request_id=uuid4(),
                revision=state.revision,
                card_id=state.current_card["id"],
                action="message",
                message="请再讲一遍。",
            )
            _, turn_id = apply_action(db, state.id, action)
            turn = db.get(TutorTurn, turn_id)
            frozen = turn.routing_snapshot_json
        self.assertEqual(frozen["routes"]["tutor.answer"]["model"], "model-before")

        self._switch_default(self.second_model_id)
        seen = {}

        def tutor_model(_system, _human, schema, **kwargs):
            seen.update(kwargs)
            self.assertIs(schema, TutorDecision)
            return TutorDecision(reply_markdown="请求由客户端发出。", action="stay")

        with patch(
            "backend.tutor.workflow.generate_json_messages", side_effect=tutor_model
        ):
            run_tutor_turn(turn_id, self.engine)
        self.assertEqual(seen["role"], "tutor.answer")
        self.assertEqual(
            seen["snapshot"]["routes"]["tutor.answer"]["model"],
            "model-before",
        )
        with Session(self.engine) as db:
            turn = db.get(TutorTurn, turn_id)
            self.assertEqual(turn.status, "ready")


if __name__ == "__main__":
    unittest.main()
