"""合成资料、临时数据库；不上传私人资料，不调用模型。"""
from copy import deepcopy
from uuid import uuid4
import unittest
from sqlalchemy.orm import Session
from backend.tests import test_materials as fixtures
from backend.materials import service
from backend.materials.models import MaterialBatch, MaterialFile, MaterialProcess
from backend.intake.models import IntakeSession
from backend.courses.models import Course
from backend.outlines.models import OutlineVersion
from backend.versions.models import DirectoryManifest


class MaterialRetrievalTests(unittest.TestCase):
    setUp = fixtures.MaterialsTests.setUp
    tearDown = fixtures.MaterialsTests.tearDown
    batch = fixtures.MaterialsTests.batch
    upload = fixtures.MaterialsTests.upload
    prepared = fixtures.MaterialsTests.prepared
    annotate = fixtures.MaterialsTests.annotate

    def linked(self, text='连接池复用数据库连接。使用 HTTPException 返回 422 错误。'):
        batch=self.annotate(self.prepared(text=text)).json()
        with Session(self.engine) as db:
            course=Course(name='检索测试课程',intro='合成教材')
            db.add(course); db.flush()
            intake=IntakeSession(initial_name=course.name,initial_intro=course.intro,status='completed',course_id=course.id)
            db.add(intake); db.flush()
            row=db.get(MaterialBatch,batch['id'])
            basis,_=service.prepare_manifest(db,row)
            for file in basis['files']:
                file['analysis']={'summary':'合成摘要','topics':[],'gaps':[]}
            row.status='linked'; row.intake_id=intake.id
            row.manifest_json=deepcopy(basis); row.context_json=deepcopy(basis)
            intake.brief={'material_basis':deepcopy(basis)}
            versions=[]
            for number,brief in ((1,None),(2,intake.brief)):
                version=OutlineVersion(course_id=course.id,version_number=number,name=course.name,outline_json={'chapters':[]})
                db.add(version); db.flush()
                db.add(DirectoryManifest(version_id=version.id,course_id=course.id,tree_json={'chapters':[]},brief_json=deepcopy(brief),origin='test'))
                versions.append(version.id)
            db.commit()
            return course.id, versions, batch

    def search(self, course, version, **params):
        return self.client.get(f'/material-batches/for-course/{course}/search',params={'outline_version_id':version,**params})

    def source(self, course, version, hit, **params):
        return self.client.get(f'/material-batches/for-course/{course}/source',params={
            'outline_version_id':version,'file_id':hit['file_id'],'process_id':hit['process_id'],
            'element_id':hit['element_id'],**params})

    def test_keywords_functions_and_physical_page_have_source_locations(self):
        course,(_,version),batch=self.linked()
        for keyword in ('连接池','httpexception','422'):
            response=self.search(course,version,q=keyword)
            self.assertEqual(response.status_code,200,response.text)
            hit=response.json()['hits'][0]
            self.assertEqual(hit['locator']['page'],1)
            self.assertEqual(hit['process_id'],batch['files'][0]['process_id'])
            source=self.source(course,version,hit)
            self.assertEqual(source.status_code,200,source.text)
            self.assertIn('HTTPException',source.json()['text'])
        direct=self.search(course,version,file_id=batch['files'][0]['id'],page=1)
        self.assertEqual(len(direct.json()['hits']),1)

    def test_excluded_pages_and_unknown_terms_are_not_fabricated(self):
        course,(_,version),batch=self.linked()
        self.assertEqual(self.search(course,version,q='SECOND').json()['hits'],[])
        self.assertEqual(self.search(course,version,q='不存在的单词xyz').json()['hits'],[])
        self.assertEqual(self.search(course,version,file_id=batch['files'][0]['id'],page=2).json()['hits'],[])
        hit=self.search(course,version,q='422').json()['hits'][0]
        self.assertEqual(self.source(course,version,hit,element_id='e2').status_code,404)

    def test_course_and_outline_scope_do_not_leak(self):
        course,(old,current),batch=self.linked()
        other,(_,other_version),_=self.linked('OTHER_SECRET')
        hit=self.search(course,current,q='422').json()['hits'][0]
        self.assertFalse(self.search(course,old,q='422').json()['scope_available'])
        self.assertIsNone(self.client.get(f'/material-batches/for-course/{course}',params={'outline_version_id':old}).json())
        self.assertEqual(self.source(course,old,hit).status_code,404)
        self.assertEqual(self.source(other,other_version,hit).status_code,404)
        self.assertEqual(self.search(course,other_version,q='OTHER_SECRET').status_code,404)
        self.assertEqual(self.search(course,current,q='422',file_id=str(uuid4())).status_code,404)

    def test_new_parse_is_not_substituted_and_source_process_is_checked(self):
        course,(_,version),batch=self.linked()
        file=batch['files'][0]
        new_id=str(uuid4())
        with Session(self.engine) as db:
            report=deepcopy(db.get(MaterialProcess,file['process_id']).report_json)
            report['elements'][0]['text']='NEW_REVISION_SECRET'
            db.add(MaterialProcess(id=new_id,file_id=file['id'],status='ready',report_json=report)); db.commit()
        hit=self.search(course,version,q='422').json()['hits'][0]
        self.assertEqual(self.source(course,version,hit,process_id=new_id).status_code,404)
        self.assertEqual(self.search(course,version,q='NEW_REVISION_SECRET').json()['hits'],[])
        metadata=self.client.get(f'/material-batches/for-course/{course}',params={'outline_version_id':version}).json()
        self.assertEqual(metadata['files'][0]['process_id'],file['process_id'])

    def test_changed_manifest_or_file_hash_fails_closed(self):
        course,(_,version),batch=self.linked()
        with Session(self.engine) as db:
            row=db.get(MaterialBatch,batch['id'])
            manifest=deepcopy(row.manifest_json)
            manifest['files'][0]['annotations'][0]['page_end']=2
            row.manifest_json=manifest; db.commit()
        self.assertEqual(self.search(course,version,q='422').status_code,409)
        course,(_,version),batch=self.linked()
        with Session(self.engine) as db:
            db.get(MaterialFile,batch['files'][0]['id']).sha256='0'*64; db.commit()
        self.assertEqual(self.search(course,version,q='422').status_code,409)

    def test_long_paragraph_offsets_preserve_original_text(self):
        original='起点。'+('abcdefghijklmnop '*450)+' TARGET_END'
        course,(_,version),_=self.linked(original)
        hit=self.search(course,version,q='TARGET_END').json()['hits'][0]
        self.assertGreater(hit['offset'],0)
        self.assertEqual(hit['excerpt'],original[hit['offset']:hit['offset']+900])
        first=self.source(course,version,hit).json()
        second=self.source(course,version,hit,offset=first['next_offset']).json()
        self.assertEqual(first['text']+second['text'],original)
        self.assertIsNone(second['next_offset'])
        self.assertEqual(self.source(course,version,hit,offset=len(original)+1).status_code,422)

    def test_word_locator_and_unlisted_preview(self):
        course,(_,version),batch=self.linked()
        with Session(self.engine) as db:
            process=db.get(MaterialProcess,batch['files'][0]['process_id'])
            report=deepcopy(process.report_json)
            report['elements'][0]['locator']={'type':'word_paragraph','paragraph':7,'heading_path':['数据库','连接池']}
            report['elements'][0]['preview']='unlisted.png'
            process.report_json=report
            row=db.get(MaterialBatch,batch['id'])
            basis=deepcopy(row.manifest_json)
            basis['files'][0]['annotations'][0].update(page_start=None,page_end=None)
            row.manifest_json=basis
            db.get(DirectoryManifest,version).brief_json={'material_basis':deepcopy(basis)}
            db.commit()
        hit=self.search(course,version,q='连接池').json()['hits'][0]
        self.assertEqual(hit['locator']['paragraph'],7)
        self.assertIsNone(self.source(course,version,hit).json()['preview'])

    def test_allowed_preview_is_returned_with_frozen_source_identity(self):
        course,(_,version),batch=self.linked()
        with Session(self.engine) as db:
            process=db.get(MaterialProcess,batch['files'][0]['process_id'])
            report=deepcopy(process.report_json)
            report['elements'][0]['preview']='page-1.png'
            report['artifacts']=[{'path':'page-1.png','locator':{'type':'pdf_page','page':1}}]
            process.report_json=report; db.commit()
        hit=self.search(course,version,q='422').json()['hits'][0]
        source=self.source(course,version,hit).json()
        self.assertEqual(source['preview'],'page-1.png')
        self.assertEqual(source['process_id'],batch['files'][0]['process_id'])

    def test_bad_search_input_is_rejected(self):
        course,(_,version),_=self.linked()
        for params in ({},{'q':'!!!'},{'q':'422','page':0},{'q':'422','limit':13}):
            self.assertEqual(self.search(course,version,**params).status_code,422)
