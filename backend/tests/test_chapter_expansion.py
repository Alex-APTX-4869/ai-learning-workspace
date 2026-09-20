import json
import unittest
from copy import deepcopy
from uuid import uuid4
from unittest.mock import patch
from sqlalchemy.orm import Session
from fastapi import HTTPException
from backend.tests import test_versions as fixtures
from backend.versions import expansion, service
from backend.outlines.service import _consume_line
from backend.materials.models import MaterialBatch, MaterialFile, MaterialProcess
from backend.materials import retrieval
from backend.learning.grounding import collect_evidence


class ChapterExpansionTests(unittest.TestCase):
    setUp = fixtures.DirectoryVersionTests.setUp
    tearDown = fixtures.DirectoryVersionTests.tearDown

    def draft(self):
        return self.client.post(f'/courses/{self.course_id}/directory-drafts').json()

    def batch(self, word='追加资料内容'):
        batch_id, file_id, process_id = (str(uuid4()) for _ in range(3))
        annotations = [{'role':'chapter','chapter':'新章','note':'','page_start':1,'page_end':1}]
        item = {'file_id':file_id,'filename':'synthetic.pdf','process_id':process_id,'sha256':'a'*64,
                'annotations':annotations,'analysis':{'summary':word,'topics':[word],'gaps':[]}}
        basis = {'batch_id':batch_id,'files':[item],'completeness':'partial'}
        with Session(self.engine) as db:
            db.add(MaterialBatch(id=batch_id,name='新章',intro='需求',status='ready',manifest_json=deepcopy(basis),context_json=deepcopy(basis)))
            db.add(MaterialFile(id=file_id,batch_id=batch_id,request_id=str(uuid4()),filename='synthetic.pdf',suffix='.pdf',sha256='a'*64,byte_size=123,annotations_json=annotations))
            db.add(MaterialProcess(id=process_id,file_id=file_id,status='ready',report_json={'page_count':1,'issues':[],'artifacts':[],
                'elements':[{'id':'e1','text':word,'kind':'text','locator':{'page':1,'type':'pdf_page'}}]}))
            db.commit()
        return batch_id, file_id

    def generate(self, draft, batch_id=None, name='新增章'):
        with patch.object(expansion, 'generate_json_messages', return_value=expansion.NewChapter(name='模型章名',sections=[expansion.NewSection(name='追加资料内容')])) as model:
            response = self.client.post(f'/courses/{self.course_id}/directory-drafts/{draft["id"]}/generate-chapter',json={
                'expected_revision':draft['revision'],'name':name,'requirements':'用户希望追加的内容','material_batch_id':batch_id})
        return response, model

    def publish(self, draft):
        response = self.client.post(f'/courses/{self.course_id}/directory-drafts/{draft["id"]}/publish',json={'expected_revision':draft['revision']})
        self.assertEqual(response.status_code,200,response.text)
        return response.json()['published_version_id']

    def test_preview_then_publish_preserves_existing_nodes_and_content(self):
        draft = self.draft()
        response, model = self.generate(draft)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(self.client.get(f'/courses/{self.course_id}').json()['outline_version_id'],self.o1)
        model.assert_called_once()
        new_id = self.publish(response.json())
        with Session(self.engine) as db:
            old = service.get_manifest(db,self.course_id,self.o1)
            new = service.get_manifest(db,self.course_id,new_id)
            self.assertEqual(old.tree_json['chapters'][0],new.tree_json['chapters'][0])
            self.assertEqual(len(new.tree_json['chapters']),2)
            self.assertEqual(new.tree_json['chapters'][1]['name'],'新增章')
        self.assertEqual(self.publish(response.json()),new_id)

    def test_new_materials_flow_to_retrieval_and_content_only_after_publish(self):
        batch_id,file_id = self.batch()
        response, model = self.generate(self.draft(),batch_id)
        self.assertEqual(response.status_code,200,response.text)
        payload = json.loads(model.call_args.args[1])
        self.assertEqual(payload['new_materials']['files'][0]['annotations'][0]['chapter'],'新章')
        self.assertIn('course_brief',payload)
        new_id = self.publish(response.json())
        with Session(self.engine) as db:
            self.assertIsNone(retrieval.course_scope(db,self.course_id,self.o1))
            evidence = collect_evidence(db,self.course_id,new_id,{'target_point':{'name':'追加资料内容','intro':''},'target_section':{'section_name':'新章'}})
            self.assertEqual(evidence['sources'][0]['file_id'],file_id)
            self.assertEqual(evidence['sources'][0]['batch_id'],batch_id)
            self.assertEqual(retrieval.read_course_materials(db,self.course_id,new_id)['files'][0]['batch_id'],batch_id)
        reopened = self.client.post(f'/material-batches/{batch_id}/reopen',json={'expected_revision':1})
        self.assertEqual(reopened.status_code,409)

    def test_two_append_batches_preserve_old_version_scope(self):
        first,file1 = self.batch('FIRST_ONLY')
        response,_ = self.generate(self.draft(),first)
        v1 = self.publish(response.json())
        second,file2 = self.batch('SECOND_ONLY')
        response,_ = self.generate(self.draft(),second,name='再新增章')
        self.assertEqual(response.status_code,200,response.text)
        v2 = self.publish(response.json())
        with Session(self.engine) as db:
            self.assertEqual(len(retrieval.course_scope(db,self.course_id,v2)['files']),2)
            self.assertEqual(retrieval.search(db,self.course_id,v1,'SECOND_ONLY')['hits'],[])
            self.assertEqual(retrieval.search(db,self.course_id,v2,'SECOND_ONLY')['hits'][0]['file_id'],file2)

    def test_batch_cannot_be_claimed_twice_and_stale_request_does_not_call_model(self):
        batch,_ = self.batch()
        draft = self.draft()
        result,_ = self.generate(draft,batch)
        self.assertEqual(result.status_code,200,result.text)
        response,model = self.generate(draft,batch)
        self.assertEqual(response.status_code,409);model.assert_not_called()
        response,model = self.generate(self.draft(),batch)
        self.assertEqual(response.status_code,409);model.assert_not_called()

    def test_failure_leaves_original_unchanged_and_allows_explicit_retry(self):
        draft = self.draft()
        with patch.object(expansion,'generate_json_messages',side_effect=HTTPException(502,'模拟失败')):
            response = self.client.post(f'/courses/{self.course_id}/directory-drafts/{draft["id"]}/generate-chapter',json={
                'expected_revision':0,'name':'新增','requirements':'需求'})
        self.assertEqual(response.status_code,502)
        latest = self.client.get(f'/courses/{self.course_id}/directory-drafts/{draft["id"]}').json()
        self.assertEqual(latest['revision'],1)
        self.assertEqual(latest['additions_json'],[])
        response,_ = self.generate(latest)
        self.assertEqual(response.status_code,200,response.text)

    def test_repeated_source_chapter_stream_keeps_sections_in_same_parent(self):
        state={'name':None,'chapters':[],'done':False}
        events=[]
        for data in [{'type':'course','name':'课程'},{'type':'chapter','name':'第4章 线性回归'},
                     {'type':'section','name':'监督学习'},{'type':'chapter','name':'第4章 分类'},
                     {'type':'section','name':'逻辑回归'},{'type':'done'}]:
            events.extend(_consume_line(json.dumps(data),state))
        self.assertEqual(len(state['chapters']),1)
        self.assertEqual(len(state['chapters'][0]['sections']),2)
        self.assertEqual(events[-1]['section']['chapter_index'],0)

    def test_repair_preserves_old_tree_and_point_ids(self):
        with Session(self.engine) as db:
            manifest=service.get_manifest(db,self.course_id,self.o1)
            tree=deepcopy(manifest.tree_json)
            tree['chapters'][0]['name']='第4章 模块 A'
            second=deepcopy(tree['chapters'][0]);second['id']+=100;second['name']='第4章 模块 B';second['sections']=[]
            tree['chapters'].append(second);manifest.tree_json=tree;db.commit()
            version=expansion.repair_numbered_groups(db,self.course_id,self.o1)
            self.assertNotEqual(version,self.o1)
            self.assertEqual(len(service.get_manifest(db,self.course_id,self.o1).tree_json['chapters']),2)
            self.assertEqual(service.point_ids(service.get_manifest(db,self.course_id,version).tree_json),{self.point_id})
            self.assertEqual(expansion.repair_numbered_groups(db,self.course_id,version),version)
