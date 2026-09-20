"""隔离资料全链路与版本边界；模型输出替身不会调用用户 API。"""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch
from sqlalchemy.orm import Session
from fastapi import HTTPException
from backend.tests import test_page_recognition as visual, test_intake as intake_fixtures
from backend.materials import service, workflow, vision_service, adoption, retrieval
from backend.materials.models import MaterialBatch, MaterialProcess
from backend.materials.vision_models import PageRecognition
from backend.materials.requests import AnalysisSummary
from backend.intake.schemas import GeneratedDepthPlan, GeneratedQuestion, CourseBrief
from backend.learning.grounding import collect_evidence
from backend.outlines.models import OutlineVersion
from backend.outlines.prompts import outline_stream_messages
from backend.versions.models import DirectoryManifest


class PageAdoptionTests(unittest.TestCase):
    def setUp(self):
        self.v = visual.PageRecognitionTests(); self.v.setUp()
        self.client, self.engine = self.v.client, self.v.engine
        self.bid, self.fid = self.v.batch['id'], self.v.file['id']
        self.prefix = f'/material-batches/{self.bid}'
        # 模拟扫描页：原有提取文字为空，只有采用视觉结果后才可分析。
        with Session(self.engine) as db:
            p = db.get(MaterialProcess,self.v.file['process_id'])
            report = deepcopy(p.report_json); report['elements'][0]['text'] = ''
            p.report_json = report; db.commit()
        self.v.fixture.annotate(self.v.batch, text_only_accepted=False)

    def tearDown(self):
        self.v.tearDown()

    def batch(self):
        return self.client.get(self.prefix).json()

    def ready_job(self, result=None, accept=True):
        job = self.v.begin()
        with patch('backend.materials.vision_service.recognize', return_value=result or visual.RESULT):
            vision_service.run(job['id'],self.engine)
        if accept:
            return self.client.patch(f"{self.v.base}/vision-jobs/{job['id']}/review",
                json={'expected_revision':1,'decision':'accepted','note':'已核对合成原页'}).json()
        return self.client.get(f"{self.v.base}/vision-jobs/{job['id']}").json()

    def adopt(self, job, selected=True, revision=None):
        return self.client.post(f"{self.v.base}/vision-jobs/{job['id']}/adoption",json={
            'expected_file_revision':revision or self.batch()['files'][0]['revision'],
            'expected_recognition_revision':job['revision'],'selected':selected})

    def analyze(self):
        plan = self.client.get(self.prefix+'/analysis-plan')
        self.assertEqual(plan.status_code,200,plan.text)
        response = self.client.post(self.prefix+'/analyze',json={
            'expected_revision':plan.json()['revision'],'routing_hash':plan.json()['routing_hash']})
        self.assertEqual(response.status_code,200,response.text)
        calls=[]
        def model(system,payload,schema,**kwargs):
            calls.append(json.loads(payload))
            return AnalysisSummary(summary='合成公式 y = x^2 与合成表格。',topics=['合成公式'],gaps=[])
        with patch('backend.materials.workflow.generate_json_messages',side_effect=model):
            workflow.run_analysis(self.bid,self.engine)
        self.assertEqual(self.batch()['status'],'ready',self.batch())
        return calls

    def test_scan_page_requires_explicit_review_and_adoption(self):
        job=self.ready_job(accept=False)
        self.assertEqual(self.adopt(job).status_code,409)
        job=self.client.patch(f"{self.v.base}/vision-jobs/{job['id']}/review",json={
            'expected_revision':1,'decision':'accepted'}).json()
        self.assertEqual(self.client.get(self.prefix+'/analysis-plan').status_code,409)
        before=self.batch()['revision']
        response=self.adopt(job); self.assertEqual(response.status_code,200,response.text)
        self.assertGreater(response.json()['revision'],before)
        plan=self.client.get(self.prefix+'/analysis-plan').json()
        self.assertEqual(plan['vision_page_count'],1)
        calls=self.analyze()
        payload=json.dumps(calls,ensure_ascii=False)
        self.assertIn('y = x^2',payload)
        self.assertIn(job['id'],payload)
        self.assertNotIn('SECOND PAGE',payload)

    def test_stale_revision_and_cancel(self):
        job=self.ready_job(); revision=self.batch()['files'][0]['revision']
        self.assertEqual(self.adopt(job,revision=revision).status_code,200)
        self.assertEqual(self.adopt(job,revision=revision).status_code,409)
        self.assertEqual(self.adopt(job,False).status_code,200)
        self.assertEqual(self.client.get(self.prefix+'/analysis-plan').status_code,409)

    def test_uncertain_or_incomplete_page_cannot_be_adopted(self):
        result=deepcopy(visual.RESULT);result['issues']=['右侧缺失，不完整']
        self.assertEqual(self.adopt(self.ready_job(result)).status_code,409)

    def test_selected_page_does_not_cover_other_scanned_pages(self):
        job=self.ready_job();self.adopt(job)
        self.v.fixture.annotate(self.batch(),text_only_accepted=False,
            annotations=[{'role':'overview','page_start':1,'page_end':2}])
        self.assertEqual(self.client.get(self.prefix+'/analysis-plan').status_code,409)

    def test_review_changed_before_analysis_requires_new_confirmation(self):
        job=self.ready_job();self.adopt(job)
        self.client.patch(f"{self.v.base}/vision-jobs/{job['id']}/review",json={
            'expected_revision':job['revision'],'decision':'rejected'})
        self.assertEqual(self.client.get(self.prefix+'/analysis-plan').status_code,409)
        self.assertEqual(self.adopt(job,False).status_code,200)

    def test_frozen_page_flows_to_intake_outline_and_content_evidence(self):
        job=self.ready_job();self.adopt(job);self.analyze()
        with patch('backend.intake.service.generate_depth_plan',return_value=GeneratedDepthPlan.model_validate(intake_fixtures.DEPTHS)) as depth:
            response=self.client.post('/course-intakes',json={'name':'Test course','intro':'Learn from materials','material_batch_id':self.bid})
        self.assertEqual(response.status_code,201,response.text)
        self.assertIn('y = x^2',depth.call_args.args[0].intro)
        iid=response.json()['id']
        with patch('backend.intake.service.generate_interview_question',return_value=GeneratedQuestion.model_validate(intake_fixtures.QUESTION_1)):
            self.client.post(f'/course-intakes/{iid}/depth',json={'question_count':1})
        with patch('backend.intake.extensions.assess',return_value=None), patch('backend.intake.service.generate_course_brief',return_value=CourseBrief.model_validate(intake_fixtures.BRIEF)):
            response=self.client.post(f'/course-intakes/{iid}/answers',json={'question_id':'question_1','custom_answer':'从基础学起'})
        self.assertEqual(response.status_code,200,response.text)
        brief=response.json()['brief']
        self.assertEqual(brief['material_basis']['files'][0]['vision_pages'][0]['recognition_id'],job['id'])
        confirmed=self.client.post(f'/course-intakes/{iid}/confirm',json={}).json()
        course=confirmed['course']['id']
        _,payload=outline_stream_messages({'CourseBrief':brief})
        self.assertIn('y = x^2',payload)
        with Session(self.engine) as db:
            version=OutlineVersion(course_id=course,version_number=1,name='合成课程',outline_json={'chapters':[]})
            db.add(version);db.flush()
            db.add(DirectoryManifest(version_id=version.id,course_id=course,tree_json={'chapters':[]},brief_json=brief,origin='test'))
            db.commit();vid=version.id
            evidence=collect_evidence(db,course,vid,{'target_point':{'name':'合成公式','intro':'平方'},'target_section':{'section_name':'合成公式'}})
            self.assertIn('y = x^2',json.dumps(evidence,ensure_ascii=False))
            self.assertEqual(evidence['sources'][0]['locator']['recognition_id'],job['id'])
        self.assertEqual(self.adopt(job,False).status_code,409)
        # 新的核对结论不重写历史依据；被冻结的 hash 仍校验内容本身。
        self.client.patch(f"{self.v.base}/vision-jobs/{job['id']}/review",json={'expected_revision':job['revision'],'decision':'rejected'})
        with Session(self.engine) as db:
            self.assertTrue(retrieval.search(db,course,vid,'合成公式')['hits'])
            record=db.get(PageRecognition,job['id']);record.result_json={'blocks':[],'issues':['changed']};db.commit()
            with self.assertRaises(HTTPException):
                retrieval.search(db,course,vid,'合成公式')

    def test_out_of_scope_adoption_rejected(self):
        job=self.ready_job()
        self.v.fixture.annotate(self.batch(),text_only_accepted=False,
            annotations=[{'role':'overview','page_start':2,'page_end':2}])
        self.assertEqual(self.adopt(job).status_code,409)

    def test_transcription_replaces_same_page_text_without_duplication(self):
        job=self.ready_job(); self.adopt(job)
        with Session(self.engine) as db:
            process=db.get(MaterialProcess,self.v.file['process_id'])
            report=deepcopy(process.report_json);report['elements'][0]['text']='WRONG_EXTRACTED_FORMULA'
            process.report_json=report;db.commit()
            manifest,_=service.prepare_manifest(db,service.get_batch(db,self.bid))
            combined=adoption.effective_report(db,self.bid,manifest['files'][0],report)
            serialized=json.dumps(service.selected_elements(combined,manifest['files'][0]['annotations']))
            self.assertNotIn('WRONG_EXTRACTED_FORMULA',serialized)
            self.assertEqual(serialized.count('y = x^2'),1)

    def test_changed_original_image_cannot_be_adopted(self):
        job=self.ready_job()
        (self.v.directory/'page-1.png').write_bytes(b'changed test image')
        self.assertEqual(self.adopt(job).status_code,409)

    def test_foreign_file_job_cannot_be_adopted(self):
        job=self.ready_job()
        other=self.v.fixture.prepared()
        response=self.client.post(f"/material-batches/{other['id']}/files/{other['files'][0]['id']}/vision-jobs/{job['id']}/adoption",
            json={'expected_file_revision':other['files'][0]['revision'],'expected_recognition_revision':job['revision'],'selected':True})
        self.assertEqual(response.status_code,404)
