import json
import tempfile
import unittest
from copy import deepcopy
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session

from backend.app import create_app
from backend.courses.models import Chapter, Course, Point, Section
from backend.database import Base, get_db
from backend.learning.models import PointContentSelection, PointContentVersion
from backend.learning.schemas import PointContent
from backend.tutor.models import TutorSession, TutorTurn
from backend.tutor.schemas import TutorDecision
from backend.tutor.service import clear_advance_intent, recover_interrupted_turns
from backend.tutor.workflow import run_tutor_turn


CARD_CONTENT = {
    "lesson_markdown": "由卡片组合",
    "learning_goals": ["说明字典如何表示一条课程记录。"],
    "lesson_cards": [
        {"title": "用字段表达记录", "body_markdown": "字典用键和值表达一条记录。\n\n- `name` 是字段。\n- 值表达具体内容。"},
        {"title": "根据键读取值", "body_markdown": "使用 `course['name']` 读取课程名称。"},
    ],
    "examples": [{"title": "课程记录", "explanation_markdown": "先构建记录，再读取名称。", "code": "course = {'name': 'Python'}", "language": "python"}],
    "exercises": [{"kind": "single_choice", "question": "怎样读取课程名称？", "hint": "注意键的名称。",
                   "options": [{"label": "A", "text": "course['name']", "correct": True},
                               {"label": "B", "text": "course[0]", "correct": False}],
                   "answer": "选择 A", "explanation": "字典通过键取值。"}],
    "code_lab": None,
    "summary": "字典使用键值对表达结构化记录。",
}


class TutorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.engine = create_engine(f"sqlite:///{self.temp.name}/tutor.db", connect_args={"check_same_thread": False})
        Base.metadata.create_all(self.engine)
        app = create_app(initialize_database=False, inline_jobs=True)

        def database():
            with Session(self.engine) as db:
                yield db

        app.dependency_overrides[get_db] = database
        self.client = TestClient(app)
        with Session(self.engine) as db:
            point = Point(name="字典记录", intro="用字段表示记录。", position=0)
            course = Course(name="Python", intro="学习基本数据结构", chapters=[
                Chapter(name="数据", position=0, sections=[Section(name="字典", position=0, points=[point])])
            ])
            db.add(course)
            db.flush()
            version = PointContentVersion(point_id=point.id, plan_id=None, version_number=1, status="ready",
                origin="generated", content_json=PointContent.model_validate(CARD_CONTENT).model_dump(mode="json"),
                review_json={"approved": True, "issues": [], "revision_instructions": []}, context_hash="fixture")
            db.add(version)
            db.flush()
            db.add(PointContentSelection(point_id=point.id, version_id=version.id))
            db.commit()
            self.course_id, self.point_id, self.version_id = course.id, point.id, version.id

    def tearDown(self):
        self.client.close()
        self.engine.dispose()
        self.temp.cleanup()

    def start(self):
        result = self.client.post(f"/courses/{self.course_id}/points/{self.point_id}/tutor-session")
        self.assertEqual(result.status_code, 200, result.text)
        return result.json()

    def payload(self, state, action="next", **fields):
        return {"request_id": str(uuid4()), "revision": state["revision"], "card_id": state["current_card"]["id"], "action": action, **fields}

    def act(self, state, action="next", **fields):
        response = self.client.post(f"/tutor-sessions/{state['id']}/actions", json=self.payload(state, action, **fields))
        self.assertEqual(response.status_code, 202, response.text)
        return self.client.get(f"/tutor-sessions/{state['id']}").json()

    def test_deck_order_single_card_and_resume_without_model(self):
        with patch("backend.tutor.workflow.generate_reply") as model:
            state = self.start()
            self.assertEqual([stage["kind"] for stage in state["stages"]], ["lesson", "example", "exercise"])
            self.assertEqual(state["card_count"], 4)
            self.assertNotIn("cards", state)
            state = self.act(state)
            resumed = self.start()
            self.assertEqual(resumed["id"], state["id"])
            self.assertEqual(resumed["current_card"]["id"], "lesson-1")
            model.assert_not_called()

    def test_card_tabs_only_open_visited_cards_and_preserve_conversations(self):
        with patch('backend.tutor.workflow.generate_reply') as model:
            first = self.start()
            self.assertEqual([tab['id'] for tab in first['card_tabs']], ['lesson-0'])
            forbidden = self.client.post(f"/tutor-sessions/{first['id']}/actions",
                json=self.payload(first, 'open', target_card_id='exercise-0'))
            self.assertEqual(forbidden.status_code, 422)
            second = self.act(first)
            self.assertEqual(len(second['card_tabs']), 2)
            restored = self.act(second, 'open', target_card_id='lesson-0')
            revisited = self.act(restored)
            self.assertEqual(len(revisited['card_tabs']), 2)
            self.assertEqual(self.start()['current_card']['id'], 'lesson-1')
            model.assert_not_called()

    def test_timeline_keeps_card_message_then_next_card_on_resume(self):
        state=self.start()
        self.assertEqual([e['card']['id'] for e in state['timeline']],['lesson-0'])
        with patch('backend.tutor.workflow.generate_reply',return_value=TutorDecision(reply_markdown='键就像字段名称。',action='stay')):
            state=self.act(state,'message',message='键是什么意思？')
        state=self.act(state,'next')
        restored=self.start()
        self.assertEqual([e['type'] for e in restored['timeline']],['card','message','card'])
        self.assertEqual(restored['timeline'][-1]['card']['id'],'lesson-1')
        self.assertNotIn('exercise-0',str(restored['timeline']))

    def test_repeated_navigation_is_idempotent_and_stale_navigation_is_rejected(self):
        state = self.start()
        payload = self.payload(state)
        url = f"/tutor-sessions/{state['id']}/actions"
        one = self.client.post(url, json=payload).json()
        two = self.client.post(url, json=payload).json()
        self.assertEqual((one["card_index"], two["card_index"]), (1, 1))
        self.assertEqual(self.client.post(url, json=self.payload(state)).status_code, 409)
        payload["action"] = "previous"
        self.assertEqual(self.client.post(url, json=payload).status_code, 409)

    def test_teacher_receives_current_card_and_question_without_advancing(self):
        state = self.start()
        with patch("backend.tutor.workflow.generate_reply", return_value=TutorDecision(reply_markdown="键是给值起的名称。", action="stay")) as model:
            result = self.act(state, "message", message="键是什么意思？")
        self.assertEqual(result["card_index"], 0)
        self.assertFalse(result["busy"])
        self.assertEqual(result["turns"][-1]["reply_markdown"], "键是给值起的名称。")
        context = model.call_args.args[0]
        self.assertEqual(context["current_card"]["id"], "lesson-0")
        self.assertFalse(context["advance_authorized"])
        self.assertIn("根据键读取值", context["upcoming_card_titles"])

    def test_teacher_advance_tool_is_authorized_by_clear_user_intent(self):
        state = self.start()
        with patch("backend.tutor.workflow.generate_reply", return_value=TutorDecision(reply_markdown="继续看下一张。", action="show_next_card")):
            result = self.act(state, "message", message="没有问题，继续")
        self.assertEqual(result["card_index"], 1)
        self.assertEqual(result["turns"][-1]["teacher_action"], "show_next_card")

    def test_teacher_receives_bounded_prior_cards_and_course_without_brief(self):
        state = self.act(self.start())
        with patch("backend.tutor.workflow.generate_reply", return_value=TutorDecision(reply_markdown="上一张使用字段表达记录。", action="stay")) as model:
            self.act(state, "message", message="上一张说的字段是键吗？")
        context = model.call_args.args[0]
        self.assertEqual(context["course"]["name"], "Python")
        self.assertIsNone(context["course_brief"])
        self.assertEqual(context["recent_cards"][0]["id"], "lesson-0")
        self.assertNotIn("lesson-1", [card["id"] for card in context["recent_cards"]])

    def test_model_cannot_advance_on_question_or_vague_acknowledgement(self):
        for message in ("好", "我还没明白", "不要继续", "继续是什么意思？", "没有问题？"):
            with self.subTest(message=message):
                self.assertFalse(clear_advance_intent(message))
        state = self.start()
        with patch("backend.tutor.workflow.generate_reply", return_value=TutorDecision(reply_markdown="已经翻页。", action="show_next_card")):
            result = self.act(state, "message", message="为什么要用键？")
        self.assertEqual(result["card_index"], 0)
        self.assertFalse(result["busy"])
        self.assertEqual(result["turns"][-1]["status"], "failed")
        self.assertIsNone(result["turns"][-1]["reply_markdown"])

    def test_pending_question_survives_reopen_and_deduplicates_submission(self):
        state = self.start()
        payload = self.payload(state, "message", message="请换一个例子。")
        with patch("backend.tutor.router.run_tutor_turn") as runner:
            url = f"/tutor-sessions/{state['id']}/actions"
            first = self.client.post(url, json=payload)
            self.client.post(url, json=payload)
            runner.assert_called_once()
        self.assertTrue(first.json()["busy"])
        self.assertTrue(self.start()["busy"])
        self.assertEqual(self.client.post(url, json=self.payload(state)).status_code, 409)
        with Session(self.engine) as db:
            turn_id = db.scalar(select(TutorTurn.id))
        with patch("backend.tutor.workflow.generate_reply", return_value=TutorDecision(reply_markdown="把键想成字段名。", action="stay")) as model:
            run_tutor_turn(turn_id, self.engine)
            run_tutor_turn(turn_id, self.engine)
            model.assert_called_once()
        self.assertFalse(self.start()["busy"])

    def test_failed_model_call_preserves_progress_and_allows_followup(self):
        state = self.act(self.start())
        with patch("backend.tutor.workflow.generate_reply", side_effect=RuntimeError("private-provider-details")):
            result = self.act(state, "message", message="为什么？")
        self.assertEqual(result["card_index"], 1)
        self.assertNotIn("private-provider-details", json.dumps(result))
        self.assertFalse(result["busy"])
        with patch("backend.tutor.workflow.generate_reply", return_value=TutorDecision(reply_markdown="我们通过名称查找值。", action="stay")):
            result = self.act(result, "message", message="再解释一下。")
        self.assertEqual(result["turns"][-1]["status"], "ready")

    def test_exercise_answer_hidden_then_graded_and_persisted(self):
        state = self.start()
        for _ in range(3):
            state = self.act(state)
        exercise = state["current_card"]["exercise"]
        self.assertNotIn("answer", exercise)
        self.assertNotIn("correct", exercise["options"][0])
        self.assertIsNone(state["response"])
        with patch("backend.tutor.workflow.generate_reply", return_value=TutorDecision(reply_markdown="先想想字典通过什么查值。", action="stay")) as model:
            state = self.act(state, "message", message="给个提示。")
        context = model.call_args.args[0]
        self.assertNotIn("answer", context["current_card"]["exercise"])
        self.assertIsNone(context["exercise_response"])
        state = self.act(state, "answer", selected=[1])
        self.assertFalse(state["response"]["correct"])
        self.assertEqual(state["response"]["answer"], "选择 A")
        state = self.act(state, "answer", selected=[0])
        self.assertTrue(state["response"]["correct"])
        self.assertEqual(self.start()["response"], state["response"])
        with patch("backend.tutor.workflow.generate_reply", return_value=TutorDecision(reply_markdown="通过键读取是正确的。", action="stay")) as model:
            self.act(state, "message", message="解释我的答案。")
        self.assertTrue(model.call_args.args[0]["exercise_response"]["correct"])

    def test_invalid_answer_does_not_change_revision(self):
        state = self.start()
        for _ in range(3):
            state = self.act(state)
        url = f"/tutor-sessions/{state['id']}/actions"
        for selected in ([0, 1], [8], [], [-1], [0, 0]):
            response = self.client.post(url, json=self.payload(state, "answer", selected=selected))
            self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(self.start()["revision"], state["revision"])

    def test_completed_is_reading_progress_and_previous_reopens(self):
        state = self.start()
        for _ in range(4):
            state = self.act(state)
        self.assertTrue(state["completed"])
        self.assertEqual(state["card_index"], 3)
        self.assertIsNone(state["response"])
        state = self.act(state, "previous")
        self.assertFalse(state["completed"])
        self.assertEqual(state["card_index"], 2)

    def test_new_content_version_gets_separate_progress(self):
        original = self.act(self.start())
        with Session(self.engine) as db:
            old = db.get(PointContentVersion, self.version_id)
            new = PointContentVersion(point_id=self.point_id, plan_id=None, version_number=2, status="ready",
                origin="generated", content_json=deepcopy(old.content_json), review_json=deepcopy(old.review_json), context_hash="new")
            db.add(new)
            db.flush()
            db.get(PointContentSelection, self.point_id).version_id = new.id
            db.commit()
        fresh = self.start()
        self.assertNotEqual(fresh["id"], original["id"])
        self.assertEqual(fresh["card_index"], 0)
        prior = self.client.get(f"/tutor-sessions/{original['id']}").json()
        self.assertEqual(prior["card_index"], 1)

    def test_start_requires_own_course_and_real_cards(self):
        self.assertEqual(self.client.post(f"/courses/999/points/{self.point_id}/tutor-session").status_code, 404)
        with Session(self.engine) as db:
            version = db.get(PointContentVersion, self.version_id)
            value = deepcopy(version.content_json)
            value["lesson_cards"] = []
            version.content_json = value
            db.commit()
        self.assertEqual(self.client.post(f"/courses/{self.course_id}/points/{self.point_id}/tutor-session").status_code, 409)

    def test_restart_keeps_unsent_message_queued_without_losing_position(self):
        state = self.act(self.start())
        with patch("backend.tutor.router.run_tutor_turn"):
            self.act(state, "message", message="讲一下。")
        self.assertEqual(recover_interrupted_turns(self.engine), 1)
        restored = self.start()
        self.assertTrue(restored["busy"])
        self.assertEqual(restored["card_index"], 1)
        self.assertEqual(restored["turns"][-1]["status"], "queued")

    def test_restart_does_not_blindly_replay_running_tutor_request(self):
        state = self.act(self.start())
        with patch("backend.tutor.router.run_tutor_turn"):
            self.act(state, "message", message="讲一下。")
        with Session(self.engine) as db:
            turn = db.scalar(select(TutorTurn).where(TutorTurn.status == "queued"))
            turn.status = "running"
            db.commit()
        self.assertEqual(recover_interrupted_turns(self.engine), 1)
        restored = self.start()
        self.assertFalse(restored["busy"])
        self.assertEqual(restored["turns"][-1]["status"], "failed")
        self.assertIn("结果不确定", restored["turns"][-1]["error"])


if __name__ == "__main__":
    unittest.main()
