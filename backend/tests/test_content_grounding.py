"""Original evidence retrieval + publication guards; no external model calls."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from sqlalchemy.orm import Session

from backend.learning.grounding import collect_evidence, grounding_issues, MaterialEvidenceError
from backend.learning.schemas import PointContent, LessonDraft, ContentReview
from backend.learning.models import LearningGenerationJob, PointContentVersion
from backend.tests import test_material_retrieval as materials
from backend.tests import test_learning as learning
from backend.tutor.cards import build_deck


EVIDENCE = {"method": "keyword", "sources": [{
    "id": "S1", "file_id": "file", "batch_id": "batch", "process_id": "parse",
    "element_id": "e1", "filename": "合成教材.pdf", "locator": {"type": "pdf_page", "page": 1},
    "offset": 0, "excerpt": "浏览器发出请求，服务端返回响应。", "text_only": True,
}]}


class EvidenceRetrievalTests(unittest.TestCase):
    setUp = materials.MaterialRetrievalTests.setUp
    tearDown = materials.MaterialRetrievalTests.tearDown
    batch = materials.MaterialRetrievalTests.batch
    upload = materials.MaterialRetrievalTests.upload
    prepared = materials.MaterialRetrievalTests.prepared
    annotate = materials.MaterialRetrievalTests.annotate
    linked = materials.MaterialRetrievalTests.linked

    def context(self, keyword):
        return {"target_point": {"name": keyword, "intro": ""},
                "target_section": {"section_name": keyword}}

    def test_frozen_pages_original_text_and_bounds(self):
        text = "HTTPException 返回 422。" * 700
        course, (old, version), _ = self.linked(text)
        with Session(self.engine) as db:
            evidence = collect_evidence(db, course, version, self.context("422"))
            self.assertTrue(evidence["sources"])
            self.assertLessEqual(len(evidence["sources"]), 6)
            for source in evidence["sources"]:
                self.assertEqual(source["locator"]["page"], 1)
                self.assertLessEqual(len(source["excerpt"]), 1800)
                self.assertEqual(source["excerpt"], text[source["offset"]:source["offset"]+1800])
                self.assertNotIn("SECOND", source["excerpt"])
            self.assertEqual(collect_evidence(db, course, old, self.context("422"))["method"], "none")

    def test_empty_hits_and_excluded_page_do_not_fall_back_to_summary(self):
        course, (_, version), _ = self.linked()
        with Session(self.engine) as db:
            for keyword in ("SECOND", "missingxyz"):
                with self.assertRaises(MaterialEvidenceError):
                    collect_evidence(db, course, version, self.context(keyword))


class GroundingWorkflowTests(unittest.TestCase):
    setUp = learning.LearningWorkflowTests.setUp
    tearDown = learning.LearningWorkflowTests.tearDown
    plan = learning.LearningWorkflowTests.plan
    plan_for_components = learning.LearningWorkflowTests.plan_for_components

    def run_job(self, *, source_ids=None, gaps=None, revise=False, evidence=None):
        value = deepcopy(learning.CONTENT)
        value["examples"] = []; value["exercises"] = []
        value["lesson_cards"][0].update(source_kind="source_based", source_ids=source_ids or ["S1"])
        value["source_gaps"] = gaps or []
        lesson = LessonDraft.model_validate(value)
        revised = PointContent.model_validate(value)
        revised.material_evidence = {"sources": [{"filename": "FORGED"}]}
        reviews = [ContentReview(approved=False, revision_instructions=["修正讲解"]), ContentReview(approved=True)] if revise else [ContentReview(approved=True)]
        with (
            patch("backend.workflows.content.collect_evidence", return_value=deepcopy(evidence or EVIDENCE)) as collector,
            patch("backend.workflows.content.plan_section", return_value=self.plan_for_components(examples=False, exercises=False, code_lab=False)) as planner,
            patch("backend.workflows.content.write_lesson", return_value=lesson) as writer,
            patch("backend.workflows.content.review_point", side_effect=reviews) as reviewer,
            patch("backend.workflows.content.revise_point", return_value=revised) as reviser,
            patch("backend.workflows.content.write_examples") as example_writer,
        ):
            response = self.client.post(f"/courses/{self.course_id}/points/{self.point_ids[0]}/content/jobs")
            self.assertEqual(response.status_code, 202, response.text)
            job = self.client.get(response.headers["location"]).json()
            collector.assert_called_once()
            if planner.called:  # Re-generating the same section may reuse its plan.
                self.assertNotIn("material_evidence", planner.call_args.args[0])
            self.assertEqual(writer.call_args.args[0]["material_evidence"], evidence or EVIDENCE)
            if gaps:
                reviewer.assert_not_called()
                reviser.assert_not_called()
                example_writer.assert_not_called()
        return job

    def test_evidence_survives_revision_and_model_cannot_replace_metadata(self):
        job = self.run_job(revise=True)
        self.assertEqual(job["status"], "ready", job)
        with Session(self.engine) as db:
            saved = db.get(PointContentVersion, job["content_version_id"])
            self.assertEqual(saved.content_json["material_evidence"], EVIDENCE)
            content = PointContent.model_validate(saved.content_json)
            self.assertEqual(build_deck(content)[0]["source_ids"], ["S1"])
            self.assertEqual(db.get(LearningGenerationJob, job["id"]).context_json["material_evidence"], EVIDENCE)

    def test_unknown_citation_cannot_publish_even_if_reviewer_approves(self):
        job = self.run_job(source_ids=["S2"])
        self.assertEqual(job["status"], "needs_review", job)
        self.assertIn("未读取", job["error"])
        self.assertEqual(self.client.get(f"/courses/{self.course_id}/points/{self.point_ids[0]}/content").status_code, 404)

    def test_missing_evidence_stops_before_any_model(self):
        with patch("backend.workflows.content.collect_evidence", side_effect=MaterialEvidenceError("未检索到原文")), patch("backend.workflows.content.plan_section") as planner:
            response = self.client.post(f"/courses/{self.course_id}/points/{self.point_ids[0]}/content/jobs")
            job = self.client.get(response.headers["location"]).json()
            self.assertEqual(job["status"], "failed")
            self.assertEqual(job["error"], "未检索到原文")
            planner.assert_not_called()

    def test_reported_gap_cannot_publish_even_if_reviewer_approves(self):
        previous = self.run_job()
        job = self.run_job(gaps=["缺少公式中的变量定义"])
        self.assertEqual(job["status"], "needs_review", job)
        self.assertIn("变量定义", job["error"])
        current = self.client.get(f"/courses/{self.course_id}/points/{self.point_ids[0]}/content").json()
        self.assertEqual(current["id"], previous["content_version_id"])

    def test_supplements_cannot_mask_entirely_ungrounded_lesson(self):
        content = PointContent.model_validate(learning.CONTENT)
        issues = grounding_issues(content, {"material_evidence": EVIDENCE})
        self.assertTrue(any("任何讲解卡片" in issue for issue in issues))
        self.assertEqual(grounding_issues(content, {"material_evidence": {"method": "none"}}), [])
