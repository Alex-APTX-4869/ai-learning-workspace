import json
import tempfile
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from fastapi import HTTPException
from backend.learning import service as learning_service

from backend.ai import service as ai_service
from backend.ai.schemas import Chapter, CourseByAI
from backend.courses.models import Course
from backend.database import Base
from backend.intake import service as intake_service
from backend.intake.models import IntakeSession
from backend.intake.schemas import (
    CourseBrief,
    GeneratedDepthPlan,
    GeneratedQuestion,
    IntakeCreate,
)
from backend.outlines import service as outline_service
from backend.outlines.models import OutlineVersion
from backend.outlines.schemas import OutlineGenerationRequest
from backend.providers.schemas import RoutingSnapshot


DEPTH_PLAN = GeneratedDepthPlan.model_validate(
    {
        "options": [
            {
                "title": "快速确认",
                "description": "确认核心目标。",
                "question_count": 1,
                "recommended": False,
            },
            {
                "title": "标准确认",
                "description": "确认基础、目标与验收方式。",
                "question_count": 2,
                "recommended": True,
            },
            {
                "title": "深入确认",
                "description": "进一步确认范围和限制。",
                "question_count": 3,
                "recommended": False,
            },
        ]
    }
)
QUESTION = GeneratedQuestion.model_validate(
    {
        "focus_key": "learner_level",
        "text": "你目前的基础如何？",
        "purpose": "确定课程起点。",
        "recommendation_reason": "当前信息较少，建议从基础开始。",
        "options": [
            {
                "title": "刚开始",
                "description": "需要从基础概念开始。",
                "recommended": True,
            },
            {
                "title": "有经验",
                "description": "可以较快进入实践。",
                "recommended": False,
            },
        ],
    }
)
BRIEF = CourseBrief.model_validate(
    {
        "course_name": "FastAPI 实战",
        "summary": "从基础开始完成一个接口项目。",
        "learner_profile": "具备 Python 基础。",
        "learning_outcomes": ["能完成接口项目"],
        "scope_in": ["FastAPI"],
        "scope_out": [],
        "learning_preferences": ["讲解后练习"],
        "constraints": [],
        "success_criteria": ["项目可以运行"],
    }
)
OUTLINE = CourseByAI.model_validate(
    {
        "name": "FastAPI 实战",
        "chapters": [
            {"name": "接口基础", "sections": [{"name": "请求与响应"}]}
        ],
    }
)
POINTS = Chapter.model_validate(
    {
        "name": "接口基础",
        "sections": [
            {
                "name": "请求与响应",
                "points": [
                    {"name": "HTTP 流程", "intro": "理解一次请求和响应。"}
                ],
            }
        ],
    }
)


def routing_snapshot(*roles: str, marker: str = "model-a") -> dict:
    routes = {}
    for role in roles:
        routes[role] = {
            "requested_role": role,
            "requested_scope_type": "global",
            "requested_scope_id": None,
            "resolution_source": "global:default.chat",
            "binding_id": 1,
            "provider_id": 1,
            "provider_name": "Test provider",
            "base_url": "https://example.test/v1",
            "model_config_id": 1,
            "model": marker,
            "model_revision": 1,
            "runtime_policy": {},
            "config_fingerprint": f"{marker}:{role}",
            "required_capabilities": ["text_chat"],
            "capabilities": None,
        }
    return {"schema_version": 1, "routes": routes}


def outline_stream():
    return iter(
        (
            '{"type":"course","name":"FastAPI 实战"}\n',
            '{"type":"chapter","name":"接口基础"}\n'
            '{"type":"section","name":"请求与响应"}\n'
            '{"type":"done"}\n',
        )
    )


class SavedGenerationRoutingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = create_engine(
            f"sqlite:///{self.temp.name}/routing.db",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(self.engine)

    def tearDown(self):
        self.engine.dispose()
        self.temp.cleanup()

    def test_intake_freezes_all_roles_and_reuses_snapshot(self):
        frozen = routing_snapshot(*intake_service.INTAKE_MODEL_ROLES)
        observed = []

        def depth(data, *, routing_snapshot=None):
            observed.append(routing_snapshot)
            return DEPTH_PLAN

        with Session(self.engine) as db, patch(
            "backend.intake.service.resolve_routing_snapshot",
            return_value=frozen,
        ) as resolve, patch(
            "backend.intake.service.generate_depth_plan", side_effect=depth
        ):
            intake = intake_service.create_intake(
                db, IntakeCreate(name="FastAPI", intro="完成真实项目")
            )
            intake_id = intake.id

        def question(**kwargs):
            observed.append(kwargs["routing_snapshot"])
            return QUESTION

        with Session(self.engine) as db, patch(
            "backend.intake.service.generate_interview_question",
            side_effect=question,
        ):
            intake_service.select_depth(
                db,
                intake_id,
                intake_service.DepthSelect(option_id="depth_2"),
            )

        self.assertEqual(observed, [frozen, frozen])
        resolve.assert_called_once_with(
            unittest.mock.ANY,
            intake_service.INTAKE_MODEL_ROLES,
            scope_type="global",
        )
        with Session(self.engine) as db:
            saved = db.get(IntakeSession, intake_id)
            self.assertEqual(saved.routing_snapshot_json, frozen)
            serialized = json.dumps(saved.routing_snapshot_json)
            self.assertNotIn("api_key", serialized)
            self.assertNotIn("key_ref", serialized)

    def test_outline_and_points_versions_record_their_own_routes(self):
        outline_route = routing_snapshot("outline.generate", marker="outline-a")
        points_route = routing_snapshot("points.generate", marker="points-b")
        with Session(self.engine) as db:
            course = Course(name="FastAPI", intro="完成真实项目")
            db.add(course)
            db.commit()
            course_id = course.id

        with Session(self.engine) as db, patch(
            "backend.ai.service.resolve_routing_snapshot",
            return_value=outline_route,
        ), patch("backend.ai.service.generate_outline", return_value=OUTLINE):
            course = ai_service.generate_saved_outline(course_id, db)
            chapter_id = course.chapters[0].id
            original_outline_id = course.outline_version_id

        with Session(self.engine) as db, patch(
            "backend.ai.service.resolve_routing_snapshot",
            return_value=points_route,
        ), patch("backend.ai.service.generate_points", return_value=POINTS):
            updated = ai_service.generate_saved_points(course_id, chapter_id, db)
            new_outline_id = updated.outline_version_id
            point_id = updated.chapters[0].sections[0].points[0].id

        # 新知识点属于新目录；内容任务必须使用生成接口返回的版本。
        self.assertNotEqual(original_outline_id, new_outline_id)
        with Session(self.engine) as db:
            with self.assertRaises(HTTPException) as error:
                learning_service.create_or_get_job(db, course_id, point_id,
                                                  outline_version_id=original_outline_id)
            self.assertEqual(error.exception.status_code, 404)
        with Session(self.engine) as db, patch('backend.learning.service.resolve_routing_snapshot',
                return_value=routing_snapshot(*learning_service.CONTENT_ROLE_KEYS)):
            job, created = learning_service.create_or_get_job(db, course_id, point_id,
                                                             outline_version_id=new_outline_id)
            self.assertTrue(created)
            self.assertEqual(job.outline_version_id, new_outline_id)

        with Session(self.engine) as db:
            saved = db.scalars(
                select(OutlineVersion)
                .where(OutlineVersion.course_id == course_id)
                .order_by(OutlineVersion.version_number)
            ).all()
            self.assertEqual(len(saved), 2)
            self.assertEqual(
                saved[0].routing_snapshot_json,
                RoutingSnapshot.model_validate(outline_route).model_dump(mode="json"),
            )
            self.assertEqual(
                saved[1].routing_snapshot_json,
                RoutingSnapshot.model_validate(points_route).model_dump(mode="json"),
            )

    def test_stream_resolves_before_iteration_and_saves_same_snapshot(self):
        frozen = routing_snapshot("outline.generate", marker="stream-a")
        with Session(self.engine) as db:
            course = Course(name="FastAPI", intro="完成真实项目")
            db.add(course)
            db.commit()
            course_id = course.id

        captured = {}

        def model(system, human, *, role=None, snapshot=None, **kwargs):
            captured.update(role=role, snapshot=snapshot)
            return outline_stream()

        with Session(self.engine) as db, patch(
            "backend.outlines.service.resolve_routing_snapshot",
            return_value=frozen,
        ) as resolve, patch(
            "backend.outlines.service._client_stream_text_messages",
            side_effect=model,
        ):
            stream = outline_service.stream_new_version(
                db, course_id, OutlineGenerationRequest()
            )
            # 创建惰性迭代器时就已经解析；尚未消费任何模型输出。
            resolve.assert_called_once()
            events = [json.loads(line) for line in stream]

        self.assertEqual(events[-1]["type"], "completed")
        self.assertEqual(captured, {"role": "outline.generate", "snapshot": frozen})
        with Session(self.engine) as db:
            version = db.scalar(select(OutlineVersion))
            self.assertEqual(
                version.routing_snapshot_json,
                RoutingSnapshot.model_validate(frozen).model_dump(mode="json"),
            )


if __name__ == "__main__":
    unittest.main()
