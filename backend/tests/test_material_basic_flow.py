"""基础版本闭环验收：真实解析合成 PDF/DOCX，模型节点使用隔离替身。"""
import sys
import unittest
from unittest.mock import patch
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.tests import test_materials as fixtures
from backend.tests.test_intake import DEPTHS, QUESTION_1, BRIEF
from backend.materials import workflow
from backend.materials.parser import ROOT
from backend.materials.requests import AnalysisSummary
from backend.intake.schemas import GeneratedDepthPlan, GeneratedQuestion, CourseBrief
from backend.courses.models import Course


@unittest.skipUnless(sys.platform=='darwin' and (ROOT/'.venv-materials/bin/python').exists(), '需要已安装的 Mac 隔离解析环境')
class BasicMaterialsFlowTests(unittest.TestCase):
    setUp=fixtures.MaterialsTests.setUp
    tearDown=fixtures.MaterialsTests.tearDown
    batch=fixtures.MaterialsTests.batch
    upload=fixtures.MaterialsTests.upload
    start=fixtures.MaterialsTests.start

    def verify_flow(self, filename, page_range):
        path=ROOT/'tmp/material-fixtures-m3a/core'/filename
        if not path.exists(): self.skipTest('缺少合成验收文件')
        original=path.read_bytes()
        batch=self.upload(self.batch(),original,filename=filename).json()
        file=batch['files'][0]
        workflow.run_parse(file['process_id'],self.engine)
        batch=self.client.get(f"/material-batches/{batch['id']}").json()
        file=batch['files'][0]
        self.assertEqual(file['status'],'needs_review')
        self.assertEqual(self.client.get(f"/material-batches/{batch['id']}/analysis-plan").status_code,409)
        annotated=self.client.patch(f"/material-batches/{batch['id']}/files/{file['id']}",json={
            'expected_revision':file['revision'],'included':True,'text_only_accepted':True,
            'annotations':[{'role':'chapter','chapter':'第一章 HTTP','page_start':page_range,'page_end':page_range}]})
        self.assertEqual(annotated.status_code,200,annotated.text)
        batch=self.start(annotated.json())
        seen=[]
        def summarize(system,user,schema,**kwargs):
            seen.append(user)
            return AnalysisSummary(summary='HTTP 请求、路由与状态码。',topics=['HTTP','422'],gaps=['公式和图表尚未识别'])
        with patch('backend.materials.workflow.generate_json_messages',side_effect=summarize):
            workflow.run_analysis(batch['id'],self.engine)
        self.assertEqual(self.client.get(f"/material-batches/{batch['id']}").json()['status'],'ready')
        if page_range: self.assertNotIn('SQL transactions','\n'.join(seen))

        # 按正式接口推进访谈，只有模型推理本身由固定结果替代，不伪造课程/关联。
        with patch('backend.intake.service.generate_depth_plan',return_value=GeneratedDepthPlan.model_validate(DEPTHS)):
            created=self.client.post('/course-intakes',json={'name':batch['name'],'intro':batch['intro'],'material_batch_id':batch['id']})
        self.assertEqual(created.status_code,201,created.text)
        intake=created.json()
        with patch('backend.intake.service.generate_interview_question',return_value=GeneratedQuestion.model_validate(QUESTION_1)):
            choice=self.client.post(f"/course-intakes/{intake['id']}/depth",json={'question_count':1})
        self.assertEqual(choice.status_code,200,choice.text)
        question=choice.json()['current_question']
        with patch('backend.intake.extensions.assess',return_value=None), patch('backend.intake.service.generate_course_brief',return_value=CourseBrief.model_validate(BRIEF)):
            answered=self.client.post(f"/course-intakes/{intake['id']}/answers",json={'question_id':question['id'],'option_id':question['options'][0]['id']})
        self.assertEqual(answered.status_code,200,answered.text)
        confirmed=self.client.post(f"/course-intakes/{intake['id']}/confirm",json={})
        self.assertEqual(confirmed.status_code,200,confirmed.text)
        course=confirmed.json()['course']['id']
        repeated=self.client.post(f"/course-intakes/{intake['id']}/confirm",json={})
        self.assertEqual(repeated.json()['course']['id'],course)
        with Session(self.engine) as db:
            self.assertEqual(db.scalar(select(func.count()).select_from(Course)),1)
        results=self.client.get(f'/material-batches/for-course/{course}/search',params={'q':'422'})
        self.assertEqual(results.status_code,200,results.text)
        self.assertTrue(results.json()['hits'])
        hit=results.json()['hits'][0]
        source=self.client.get(f'/material-batches/for-course/{course}/source',params={
            'file_id':hit['file_id'],'process_id':hit['process_id'],'element_id':hit['element_id']})
        self.assertEqual(source.status_code,200,source.text)
        self.assertIn('422',source.json()['text'])
        self.assertEqual(hit['locator']['type'],'pdf_page' if page_range else 'word_paragraph')
        if page_range:
            self.assertEqual(hit['locator']['page'],1)
            self.assertEqual(self.client.get(f'/material-batches/for-course/{course}/search',params={'q':'SQL transactions'}).json()['hits'],[])
            preview=source.json()['preview']
            image=self.client.get(f"/material-batches/{batch['id']}/files/{file['id']}/processes/{file['process_id']}/artifacts/{preview}")
            self.assertEqual(image.status_code,200,image.text[:100] if image.status_code!=200 else '')
            self.assertTrue(image.content.startswith(b'\x89PNG'))
        download=self.client.get(f"/material-batches/{batch['id']}/files/{file['id']}/original")
        self.assertEqual(download.content,original)
        self.assertEqual(self.client.get(f'/material-batches/for-course/{course}').json()['id'],batch['id'])

    def test_pdf_upload_to_course_search_and_original_preview(self):
        self.verify_flow('lecture.pdf',1)

    def test_word_upload_to_course_search_and_paragraph(self):
        self.verify_flow('structure.docx',None)
