import json
import tempfile
import unittest
from copy import deepcopy
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.ai.schemas import Chapter, CourseByAI
from backend.app import create_app
from backend.courses.models import Chapter as SavedChapter
from backend.courses.models import Course, Point, Section as SavedSection
from backend.database import Base, get_db
from backend.intake.models import IntakeSession
from backend.outlines.models import OutlineVersion
from backend.outlines.prompts import outline_stream_messages


BRIEF = {
    "course_name": "FastAPI 实战",
    "summary": "通过真实项目学会设计 API。",
    "learner_profile": "会 Python 基础，还不熟悉 Web 后端。",
    "learning_outcomes": ["能独立完成课程 API"],
    "scope_in": ["FastAPI", "数据库"],
    "scope_out": ["分布式部署"],
    "learning_preferences": ["先讲解后实践"],
    "constraints": ["每晚学习一小时"],
    "success_criteria": ["前端能调用自己的 API"],
}


def model_stream(name: str, chapter: str, sections: list[str]):
    lines = [
        json.dumps({"type": "course", "name": name}, ensure_ascii=False),
        json.dumps({"type": "chapter", "name": chapter}, ensure_ascii=False),
        *[
            json.dumps({"type": "section", "name": item}, ensure_ascii=False)
            for item in sections
        ],
        json.dumps({"type": "done"}),
    ]
    text = "\n".join(lines) + "\n"
    # 故意在 JSON 行中间分块，验证解析器不假设模型块刚好等于一行。
    midpoint = len(text) // 2
    return iter((text[:midpoint], text[midpoint:]))


class OutlineVersionTests(unittest.TestCase):
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

    def tearDown(self):
        self.client.close()
        self.engine.dispose()
        self.temp.cleanup()

    def create_course(self, name="FastAPI"):
        reply = self.client.post(
            "/courses", json={"name": name, "intro": "从零完成一个真实项目"}
        )
        self.assertEqual(reply.status_code, 201, reply.text)
        return reply.json()

    def stream(self, course_id: int, name: str, chapter: str, sections: list[str], payload=None):
        with patch(
            "backend.outlines.service.stream_text_messages",
            return_value=model_stream(name, chapter, sections),
        ):
            reply = self.client.post(
                f"/courses/{course_id}/outline-versions/stream",
                json=payload or {},
            )
        self.assertEqual(reply.status_code, 200, reply.text)
        return reply, [json.loads(line) for line in reply.text.splitlines()]

    def test_first_stream_emits_progress_materializes_and_supports_points(self):
        course = self.create_course()
        reply, events = self.stream(
            course["id"], "FastAPI", "接口基础", ["请求与响应", "路由"]
        )
        self.assertEqual(
            [item["type"] for item in events],
            ["start", "chapter", "section", "section", "completed"],
        )
        self.assertTrue(events[-1]["version"]["selected"])
        self.assertEqual(reply.headers["cache-control"], "no-cache")
        self.assertEqual(reply.headers["x-accel-buffering"], "no")

        saved = self.client.get(f'/courses/{course["id"]}').json()
        self.assertEqual(saved["chapters"][0]["name"], "接口基础")
        chapter_id = saved["chapters"][0]["id"]
        generated_points = Chapter.model_validate(
            {
                "name": "接口基础",
                "sections": [
                    {
                        "name": "请求与响应",
                        "points": [{"name": "HTTP 流程", "intro": "理解一次请求。"}],
                    },
                    {
                        "name": "路由",
                        "points": [{"name": "路径映射", "intro": "定义请求路径。"}],
                    },
                ],
            }
        )
        with patch("backend.ai.service.generate_points", return_value=generated_points):
            points_reply = self.client.post(
                f'/courses/{course["id"]}/chapters/{chapter_id}/points'
            )
        self.assertEqual(points_reply.status_code, 200, points_reply.text)
        self.assertEqual(points_reply.json()["chapters"][0]["sections"][0]["points"][0]["name"], "HTTP 流程")

    def test_failed_stream_saves_neither_version_nor_tree(self):
        course = self.create_course()
        incomplete = iter(
            ('{"type":"course","name":"FastAPI"}\n', '{"type":"chapter","name":"未完成"}\n')
        )
        with patch(
            "backend.outlines.service.stream_text_messages", return_value=incomplete
        ):
            reply = self.client.post(
                f'/courses/{course["id"]}/outline-versions/stream', json={}
            )
        events = [json.loads(line) for line in reply.text.splitlines()]
        self.assertEqual(events[-1]["type"], "error")
        self.assertEqual(self.client.get(f'/courses/{course["id"]}').json()["chapters"], [])
        self.assertEqual(
            self.client.get(f'/courses/{course["id"]}/outline-versions').json(), []
        )

    def test_versions_switch_without_deleting_learning_content(self):
        course = self.create_course()
        _, first = self.stream(course["id"], "FastAPI", "旧章", ["旧小节"])
        first_version = first[-1]["version"]
        _, second = self.stream(course["id"], "FastAPI", "新章", ["新小节"])
        second_version = second[-1]["version"]
        self.assertFalse(second_version["selected"])

        selected = self.client.post(
            f'/courses/{course["id"]}/outline-versions/{second_version["id"]}/select'
        )
        self.assertEqual(selected.status_code, 200, selected.text)
        self.assertEqual(self.client.get(f'/courses/{course["id"]}').json()["chapters"][0]["name"], "新章")

        current = self.client.get(f'/courses/{course["id"]}').json()
        chapter_id = current["chapters"][0]["id"]
        generated = Chapter.model_validate({
            "name": "新章", "sections": [{"name": "新小节", "points": [
                {"name": "必须保留", "intro": "已学内容"}
            ]}]
        })
        with patch("backend.ai.service.generate_points", return_value=generated):
            expanded = self.client.post(
                f'/courses/{course["id"]}/chapters/{chapter_id}/points?outline_version_id={second_version["id"]}'
            ).json()
        point_id = expanded["chapters"][0]["sections"][0]["points"][0]["id"]
        expanded_version_id = expanded["outline_version_id"]

        switched = self.client.post(
            f'/courses/{course["id"]}/outline-versions/{first_version["id"]}/select'
        )
        self.assertEqual(switched.status_code, 200, switched.text)
        after = self.client.get(f'/courses/{course["id"]}').json()
        self.assertEqual(after["chapters"][0]["name"], "旧章")
        self.assertEqual(after["chapters"][0]["sections"][0]["points"], [])
        self.client.post(
            f'/courses/{course["id"]}/outline-versions/{expanded_version_id}/select'
        )
        restored = self.client.get(f'/courses/{course["id"]}').json()
        self.assertEqual(restored["chapters"][0]["sections"][0]["points"][0]["id"], point_id)

    def test_legacy_outline_is_bootstrapped_without_changing_ids_or_content(self):
        course = self.create_course()
        with Session(self.engine) as db:
            saved = db.get(Course, course["id"])
            saved.chapters = [
                SavedChapter(
                    name="原有章节",
                    position=0,
                    sections=[
                        SavedSection(
                            name="原有小节",
                            position=0,
                            content_markdown="原有讲义",
                            points=[Point(name="原有知识点", intro="不能丢", position=0)],
                        )
                    ],
                )
            ]
            db.commit()
        before = self.client.get(f'/courses/{course["id"]}').json()
        versions = self.client.get(
            f'/courses/{course["id"]}/outline-versions'
        ).json()
        after = self.client.get(f'/courses/{course["id"]}').json()
        self.assertEqual(len(versions), 1)
        self.assertTrue(versions[0]["selected"])
        self.assertIsNone(before["outline_version_id"])
        self.assertIsNotNone(after["outline_version_id"])
        self.assertEqual(after["directory_origin"], "legacy")
        before.pop("outline_version_id")
        after.pop("outline_version_id")
        before.pop("directory_origin")
        after.pop("directory_origin")
        self.assertEqual(before, after)

    def test_reference_requirements_and_confirmed_brief_enter_human_context(self):
        course = self.create_course()
        _, first_events = self.stream(course["id"], "FastAPI", "基础", ["入门"])
        reference_id = first_events[-1]["version"]["id"]
        with Session(self.engine) as db:
            db.add(
                IntakeSession(
                    initial_name="FastAPI",
                    initial_intro="初始需求",
                    status="completed",
                    depth_options=[],
                    brief=deepcopy(BRIEF),
                    course_id=course["id"],
                    version=1,
                )
            )
            db.commit()

        captured = {}

        def stream_model(system, human):
            captured["system"] = system
            captured["human"] = json.loads(human)
            return model_stream("FastAPI", "进阶", ["实战"])

        with patch(
            "backend.outlines.service.stream_text_messages", side_effect=stream_model
        ):
            reply = self.client.post(
                f'/courses/{course["id"]}/outline-versions/stream',
                json={
                    "additional_requirements": "增加可部署项目",
                    "reference_version_id": reference_id,
                },
            )
        self.assertEqual(reply.status_code, 200, reply.text)
        self.assertEqual(captured["human"]["course_brief"], BRIEF)
        self.assertEqual(captured["human"]["additional_requirements"], "增加可部署项目")
        self.assertEqual(captured["human"]["reference_outline"]["chapters"][0]["name"], "基础")
        self.assertIn("不套用固定数量", captured["system"])

    def test_brief_changed_during_stream_prevents_atomic_save(self):
        course = self.create_course()
        with Session(self.engine) as db:
            intake = IntakeSession(
                initial_name="FastAPI",
                initial_intro="初始需求",
                status="completed",
                depth_options=[],
                brief=deepcopy(BRIEF),
                course_id=course["id"],
                version=1,
            )
            db.add(intake)
            db.commit()
            intake_id = intake.id

        def change_brief(system, human):
            with Session(self.engine) as db:
                intake = db.get(IntakeSession, intake_id)
                changed = deepcopy(intake.brief)
                changed["summary"] = "生成期间已更改"
                intake.brief = changed
                db.commit()
            return model_stream("FastAPI", "过时章节", ["过时小节"])

        with patch(
            "backend.outlines.service.stream_text_messages", side_effect=change_brief
        ):
            reply = self.client.post(
                f'/courses/{course["id"]}/outline-versions/stream', json={}
            )
        events = [json.loads(line) for line in reply.text.splitlines()]
        self.assertEqual(events[-1]["type"], "error")
        self.assertIn("需求档案已经修改", events[-1]["detail"])
        with Session(self.engine) as db:
            self.assertIsNone(db.scalar(select(OutlineVersion.id)))
            self.assertEqual(db.get(Course, course["id"]).chapters, [])

    def test_reference_must_belong_to_same_course(self):
        first = self.create_course("FastAPI")
        second = self.create_course("Vue")
        _, events = self.stream(first["id"], "FastAPI", "基础", ["入门"])
        reference_id = events[-1]["version"]["id"]
        with patch("backend.outlines.service.stream_text_messages") as model:
            reply = self.client.post(
                f'/courses/{second["id"]}/outline-versions/stream',
                json={"reference_version_id": reference_id},
            )
        self.assertEqual(reply.status_code, 404, reply.text)
        model.assert_not_called()

    def test_prompt_has_no_example_count_hint(self):
        system, human = outline_stream_messages(
            {
                "current_course": {"name": "X", "intro": "Y"},
                "course_brief": None,
                "additional_requirements": "",
                "reference_outline": None,
            }
        )
        self.assertIn("数量完全由学习目标", system)
        self.assertIn("不套用固定数量", system)
        self.assertIsNone(json.loads(human)["course_brief"])


if __name__ == "__main__":
    unittest.main()
