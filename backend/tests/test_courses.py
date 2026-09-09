import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.ai.schemas import Chapter, CourseByAI
from backend.app import create_app
from backend.database import Base, get_db
from backend.courses.models import Point, Section

OUTLINE = {"name": "FastAPI", "chapters": [{"name": "认识接口", "sections": [{"name": "第一个接口"}, {"name": "路径参数"}]}]}
POINTS = {"name": "认识接口", "sections": [
    {"name": "第一个接口", "points": [{"name": "创建应用", "intro": "创建应用并返回数据"}]},
    {"name": "路径参数", "points": [{"name": "读取编号", "intro": "从路径读取课程编号"}]},
]}


class CourseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = create_engine(f"sqlite:///{self.temp.name}/test.db", connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        app = create_app(initialize_database=False)

        def database():
            with Session(self.engine) as db:
                yield db

        app.dependency_overrides[get_db] = database
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.engine.dispose()
        self.temp.cleanup()

    def create(self, name="FastAPI"):
        reply = self.client.post("/courses", json={"name": name, "intro": "从零开始学习接口"})
        self.assertEqual(reply.status_code, 201, reply.text)
        return reply.json()

    def outline(self, course_id):
        with patch("backend.ai.service.generate_outline", return_value=CourseByAI.model_validate(OUTLINE)):
            reply = self.client.post(f"/courses/{course_id}/outline")
        self.assertEqual(reply.status_code, 200, reply.text)
        return reply.json()

    def test_create_read_update_and_validation(self):
        item = self.create("  FastAPI  ")
        self.assertEqual(item["name"], "FastAPI")
        self.assertEqual(self.client.get(f'/courses/{item["id"]}').json(), item)
        updated = self.client.patch(f'/courses/{item["id"]}', json={"name": "Python", "intro": "重新整理目标"})
        self.assertEqual(updated.json()["name"], "Python")
        summary = self.client.get("/courses").json()[0]
        self.assertEqual(summary["name"], "Python")
        self.assertEqual((summary["chapter_count"], summary["section_count"], summary["point_count"]), (0, 0, 0))
        self.assertEqual(self.client.post("/courses", json={"name": "  ", "intro": "目标"}).status_code, 422)
        self.assertEqual(self.client.get("/courses/9999").status_code, 404)

    def test_outline_points_persist_and_repeat_does_not_overwrite(self):
        item = self.outline(self.create()["id"])
        chapter_id = item["chapters"][0]["id"]
        path = f'/courses/{item["id"]}/chapters/{chapter_id}/points'
        with patch("backend.ai.service.generate_points", return_value=Chapter.model_validate(POINTS)):
            saved = self.client.post(path)
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(len(saved.json()["chapters"][0]["sections"][0]["points"]), 1)
        self.assertEqual(self.client.get(f'/courses/{item["id"]}').json(), saved.json())
        with patch("backend.ai.service.generate_points") as model:
            self.assertEqual(self.client.post(path).json(), saved.json())
            model.assert_not_called()
        with patch("backend.ai.service.generate_outline") as model:
            self.assertEqual(self.client.post(f'/courses/{item["id"]}/outline').json(), saved.json())
            model.assert_not_called()
        summary = self.client.get("/courses").json()[0]
        self.assertEqual((summary["chapter_count"], summary["section_count"], summary["point_count"]), (1, 2, 2))

    def test_partial_chapter_only_fills_missing_sections(self):
        item = self.outline(self.create()["id"])
        with Session(self.engine) as db:
            first = db.scalars(select(Section).order_by(Section.position)).first()
            assert first is not None
            first.points = [Point(name="原有知识点", intro="必须保留", position=0)]
            db.commit()
        chapter_id = item["chapters"][0]["id"]
        with patch("backend.ai.service.generate_points", return_value=Chapter.model_validate(POINTS)):
            saved = self.client.post(f'/courses/{item["id"]}/chapters/{chapter_id}/points')
        self.assertEqual(saved.status_code, 200, saved.text)
        sections = saved.json()["chapters"][0]["sections"]
        self.assertEqual(sections[0]["points"][0]["name"], "原有知识点")
        self.assertEqual(sections[1]["points"][0]["name"], "读取编号")

    def test_wrong_course_cannot_generate_another_chapter(self):
        one = self.outline(self.create()["id"])
        two = self.create("另一门课程")
        with patch("backend.ai.service.generate_points") as model:
            reply = self.client.post(f'/courses/{two["id"]}/chapters/{one["chapters"][0]["id"]}/points')
            self.assertEqual(reply.status_code, 404)
            model.assert_not_called()

    def test_model_failure_leaves_saved_outline_intact(self):
        item = self.outline(self.create()["id"])
        with patch("backend.ai.service.generate_points", side_effect=HTTPException(502, "模型服务不可用")):
            reply = self.client.post(f'/courses/{item["id"]}/chapters/{item["chapters"][0]["id"]}/points')
            self.assertEqual(reply.status_code, 502)
        self.assertEqual(self.client.get(f'/courses/{item["id"]}').json(), item)

    def test_invalid_model_json_and_changed_section_are_not_saved(self):
        item = self.create()
        with patch("backend.ai.client.get_llm") as model:
            model.return_value.invoke.return_value = SimpleNamespace(content="not json")
            self.assertEqual(self.client.post(f'/courses/{item["id"]}/outline').status_code, 502)
        self.assertEqual(self.client.get(f'/courses/{item["id"]}').json()["chapters"], [])
        item = self.outline(item["id"])
        invalid = Chapter.model_validate({"name": "认识接口", "sections": [{"name": "改名的小节", "points": [{"name": "错误", "intro": "不该保存"}]}]})
        with patch("backend.ai.service.generate_json", return_value=invalid):
            reply = self.client.post(f'/courses/{item["id"]}/chapters/{item["chapters"][0]["id"]}/points')
            self.assertEqual(reply.status_code, 502)
        self.assertEqual(self.client.get(f'/courses/{item["id"]}').json(), item)

    def test_course_changed_during_generation_does_not_save_stale_result(self):
        item = self.create()
        def generate(request):
            reply = self.client.patch(f'/courses/{item["id"]}', json={"name": "新主题", "intro": "新目标"})
            self.assertEqual(reply.status_code, 200)
            return CourseByAI.model_validate(OUTLINE)
        with patch("backend.ai.service.generate_outline", side_effect=generate):
            self.assertEqual(self.client.post(f'/courses/{item["id"]}/outline').status_code, 409)
        saved = self.client.get(f'/courses/{item["id"]}').json()
        self.assertEqual(saved["name"], "新主题")
        self.assertEqual(saved["chapters"], [])


if __name__ == "__main__":
    unittest.main()
