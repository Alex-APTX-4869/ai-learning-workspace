import tempfile
import unittest
from copy import deepcopy

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app import create_app
from backend.courses.models import Chapter, Course, Point, Section
from backend.database import Base, get_db
from backend.learning import service as learning
from backend.learning.models import PointContentSelection, PointContentVersion
from backend.outlines.models import OutlineVersion
from backend.versions import service as versions


CONTENT = {
    "lesson_markdown": "## 原讲解\n\n正文",
    "learning_goals": ["理解原知识点"],
    "lesson_cards": [{"title": "原讲解", "body_markdown": "正文"}],
    "examples": [], "exercises": [], "code_lab": None, "summary": "原总结",
}
REVIEW = {"approved": True, "issues": [], "revision_instructions": []}


class DirectoryVersionTests(unittest.TestCase):
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
            point = Point(name="稳定身份", intro="旧章知识点", position=0)
            section = Section(name="旧小节", position=0, points=[point])
            course = Course(name="版本课", intro="验证非破坏性目录", chapters=[
                Chapter(name="旧章", position=0, sections=[section])
            ])
            db.add(course)
            db.flush()
            content = PointContentVersion(
                point_id=point.id, plan_id=None, version_number=1, status="ready",
                origin="generated", content_json=deepcopy(CONTENT),
                review_json=deepcopy(REVIEW), revision_count=0,
                context_hash="legacy-fixture",
            )
            db.add(content)
            db.flush()
            db.add(PointContentSelection(point_id=point.id, version_id=content.id))
            db.commit()
            self.course_id, self.point_id = course.id, point.id
            self.section_id, self.content_id = section.id, content.id
        versions_payload = self.client.get(
            f"/courses/{self.course_id}/outline-versions"
        ).json()
        self.o1 = versions_payload[0]["id"]

    def tearDown(self):
        self.client.close()
        self.engine.dispose()
        self.temp.cleanup()

    def publish_added_chapter(self):
        draft = self.client.post(f"/courses/{self.course_id}/directory-drafts").json()
        changed = self.client.post(
            f"/courses/{self.course_id}/directory-drafts/{draft['id']}/chapters",
            json={
                "expected_revision": draft["revision"],
                "chapter": {
                    "name": "新增章",
                    "sections": [{
                        "name": "新增小节",
                        "points": [{"name": "新增点", "intro": "只属于新版"}],
                    }],
                },
            },
        ).json()
        published = self.client.post(
            f"/courses/{self.course_id}/directory-drafts/{draft['id']}/publish",
            json={"expected_revision": changed["revision"]},
        )
        self.assertEqual(published.status_code, 200, published.text)
        return published.json()["published_version_id"]

    def test_added_chapter_creates_new_version_and_o1_remains_readable(self):
        o2 = self.publish_added_chapter()
        old = self.client.get(
            f"/courses/{self.course_id}/outline-versions/{self.o1}/course"
        ).json()
        new = self.client.get(
            f"/courses/{self.course_id}/outline-versions/{o2}/course"
        ).json()
        self.assertEqual([item["name"] for item in old["chapters"]], ["旧章"])
        self.assertEqual([item["name"] for item in new["chapters"]], ["旧章", "新增章"])
        self.assertEqual(old["chapters"][0]["sections"][0]["points"][0]["id"], self.point_id)
        self.assertEqual(new["chapters"][0]["sections"][0]["points"][0]["id"], self.point_id)

        self.client.post(f"/courses/{self.course_id}/outline-versions/{self.o1}/select")
        self.assertEqual(self.client.get(f"/courses/{self.course_id}").json()["outline_version_id"], self.o1)
        self.client.post(f"/courses/{self.course_id}/outline-versions/{o2}/select")
        self.assertEqual(self.client.get(f"/courses/{self.course_id}").json()["outline_version_id"], o2)

    def test_content_selection_and_tutor_progress_are_isolated_by_outline(self):
        o2 = self.publish_added_chapter()
        with Session(self.engine) as db:
            c2 = PointContentVersion(
                point_id=self.point_id, plan_id=None, version_number=2, status="ready",
                origin="generated", content_json={**deepcopy(CONTENT), "summary": "新版总结"},
                review_json=deepcopy(REVIEW), revision_count=0, context_hash="c2",
            )
            db.add(c2)
            db.flush()
            versions.select_content(db, self.point_id, c2.id, o2)
            db.commit()
            c2_id = c2.id
        old = self.client.get(
            f"/courses/{self.course_id}/points/{self.point_id}/content?outline_version_id={self.o1}"
        ).json()
        new = self.client.get(
            f"/courses/{self.course_id}/points/{self.point_id}/content?outline_version_id={o2}"
        ).json()
        self.assertEqual(old["id"], self.content_id)
        self.assertEqual(new["id"], c2_id)
        old_session = self.client.post(
            f"/courses/{self.course_id}/points/{self.point_id}/tutor-session?outline_version_id={self.o1}&content_version_id={self.content_id}"
        ).json()
        new_session = self.client.post(
            f"/courses/{self.course_id}/points/{self.point_id}/tutor-session?outline_version_id={o2}&content_version_id={c2_id}"
        ).json()
        self.assertNotEqual(old_session["id"], new_session["id"])
        self.assertEqual((old_session["outline_version_id"], new_session["outline_version_id"]), (self.o1, o2))

    def test_same_section_can_have_separate_jobs_in_two_outline_versions(self):
        o2 = self.publish_added_chapter()
        with Session(self.engine) as db:
            first, created_first = learning.create_or_get_job(
                db, self.course_id, self.point_id, outline_version_id=self.o1
            )
        with Session(self.engine) as db:
            second, created_second = learning.create_or_get_job(
                db, self.course_id, self.point_id, outline_version_id=o2
            )
        self.assertTrue(created_first)
        self.assertTrue(created_second)
        self.assertNotEqual(first.id, second.id)
        self.assertEqual((first.outline_version_id, second.outline_version_id), (self.o1, o2))

    def test_stale_draft_is_preserved_but_cannot_overwrite_new_selection(self):
        stale = self.client.post(f"/courses/{self.course_id}/directory-drafts").json()
        stale = self.client.post(
            f"/courses/{self.course_id}/directory-drafts/{stale['id']}/chapters",
            json={"expected_revision": 0, "chapter": {"name": "迟到章", "sections": [{"name": "内容", "points": []}]}},
        ).json()
        self.publish_added_chapter()
        reply = self.client.post(
            f"/courses/{self.course_id}/directory-drafts/{stale['id']}/publish",
            json={"expected_revision": stale["revision"]},
        )
        self.assertEqual(reply.status_code, 409, reply.text)
        self.assertEqual(self.client.get(
            f"/courses/{self.course_id}/directory-drafts/{stale['id']}"
        ).json()["status"], "editing")

    def test_historical_outline_without_manifest_is_readable_before_selection(self):
        with Session(self.engine) as db:
            historical = OutlineVersion(
                course_id=self.course_id,
                version_number=2,
                name="尚未物化的历史版",
                outline_json={
                    "name": "尚未物化的历史版",
                    "chapters": [{"name": "历史章", "sections": [{"name": "历史小节"}]}],
                },
                additional_requirements="迁移前保存",
            )
            db.add(historical)
            db.commit()
            historical_id = historical.id
        reply = self.client.get(
            f"/courses/{self.course_id}/outline-versions/{historical_id}/course"
        )
        self.assertEqual(reply.status_code, 200, reply.text)
        self.assertEqual(reply.json()["chapters"][0]["name"], "历史章")
        self.assertTrue(reply.json()["intro_is_fallback"])
        with Session(self.engine) as db:
            manifest = versions.get_manifest(db, self.course_id, historical_id)
            self.assertIsNone(manifest.brief_json)

    def test_content_selection_rejects_another_points_content(self):
        o2 = self.publish_added_chapter()
        with Session(self.engine) as db:
            other = Point(name="另一知识点", intro="不可错挂", position=1,
                          section_id=self.section_id)
            db.add(other)
            db.flush()
            wrong = PointContentVersion(
                point_id=other.id, plan_id=None, version_number=1, status="ready",
                origin="generated", content_json=deepcopy(CONTENT),
                review_json=deepcopy(REVIEW), revision_count=0, context_hash="wrong",
            )
            db.add(wrong)
            db.flush()
            with self.assertRaisesRegex(Exception, "属于该知识点"):
                versions.select_content(db, self.point_id, wrong.id, o2)


if __name__ == "__main__":
    unittest.main()
