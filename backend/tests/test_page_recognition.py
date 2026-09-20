"""临时库、合成图片、模型替身；不读取私人 PDF，不向外部发送请求。"""
import base64
from copy import deepcopy
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4
from pydantic import SecretStr
from sqlalchemy.orm import Session
from backend.materials import storage, vision_service, vision_client
from backend.materials.models import MaterialProcess
from backend.materials.vision_models import PageRecognition
from backend.providers.probes import _vision_challenge
from backend.providers.schemas import ModelRuntimePolicy
from backend.tests import test_materials

RESULT={"blocks":[{"kind":"formula","title":"合成公式","content":"y = x^2","uncertain":False,"note":""},
    {"kind":"table","title":"合成表格","content":"| x | y |\n| --- | --- |\n| 2 | 4 |","uncertain":False,"note":""}],"issues":[]}


class PageRecognitionTests(unittest.TestCase):
    def setUp(self):
        self.fixture=test_materials.MaterialsTests();self.fixture.setUp()
        self.client=self.fixture.client;self.engine=self.fixture.engine
        self.batch=self.fixture.prepared(needs_review=True,text='PAGE ONE synthetic text')
        self.file=self.batch['files'][0]
        self.image=base64.b64decode(_vision_challenge()[0].split(',')[1])
        self.directory=storage.process_dir(self.file['id'],self.file['process_id'])
        self.directory.mkdir(parents=True)
        (self.directory/'page-1.png').write_bytes(self.image)
        (self.directory/'page-2.png').write_bytes(self.image)
        with Session(self.engine) as db:
            process=db.get(MaterialProcess,self.file['process_id'])
            report=deepcopy(process.report_json)
            report['artifacts']=[{'path':f'page-{n}.png','locator':{'type':'pdf_page','page':n}} for n in [1,2]]
            process.report_json=report;db.commit()
        self.base=f"/material-batches/{self.batch['id']}/files/{self.file['id']}"
        self.page=f"{self.base}/processes/{self.file['process_id']}/pages/1"
        self.route={'provider_name':'Synthetic fixture','model':'test-vision','base_url':'http://127.0.0.1:9/v1','config_fingerprint':'a'*64}
        self.routing=patch('backend.materials.vision_service.resolve_routing_snapshot',side_effect=lambda *a,**k:{'routes':{'materials.vision':deepcopy(self.route)}})
        self.routing.start()

    def tearDown(self):
        self.routing.stop();self.fixture.tearDown()

    def prepare(self):
        response=self.client.get(self.page+'/vision-plan');self.assertEqual(response.status_code,200,response.text)
        return response.json()

    def begin(self,plan=None,request_id=None):
        p=plan or self.prepare()
        response=self.client.post(self.page+'/vision',json={'request_id':request_id or str(uuid4()),'plan_hash':p['plan_hash']})
        self.assertEqual(response.status_code,202,response.text)
        return response.json()

    def test_inspection_and_plan_do_not_call_model(self):
        with patch('backend.materials.vision_service.recognize') as model:
            page=self.client.get(self.page+'/vision').json();p=self.prepare()
        model.assert_not_called()
        self.assertEqual(page['text'],'PAGE ONE synthetic text');self.assertEqual(page['jobs'],[])
        self.assertEqual(p['maximum_calls'],1);self.assertNotIn('SECOND PAGE',json.dumps(p))

    def test_idempotency_cache_and_exact_page_payload(self):
        p=self.prepare();request_id=str(uuid4());first=self.begin(p,request_id)
        self.assertEqual(first['id'],self.begin(p,request_id)['id'])
        self.assertEqual(first['id'],self.begin(p)['id'])
        with patch('backend.materials.vision_service.recognize',return_value=RESULT) as model:
            vision_service.run(first['id'],self.engine);vision_service.run(first['id'],self.engine)
        model.assert_called_once_with(self.route,self.image,'PAGE ONE synthetic text')
        self.assertEqual(self.prepare()['maximum_calls'],0)
        self.assertEqual(self.begin()['id'],first['id'])
        original=self.client.get(f"/material-batches/{self.batch['id']}").json()
        self.assertFalse(original['files'][0]['text_only_accepted'])
        self.assertEqual(original['status'],'editing')

    def test_plan_invalidated_when_model_changes(self):
        p=self.prepare();self.route['config_fingerprint']='b'*64
        reply=self.client.post(self.page+'/vision',json={'request_id':str(uuid4()),'plan_hash':p['plan_hash']})
        self.assertEqual(reply.status_code,409)

    def test_plan_invalidated_when_image_changes(self):
        p=self.prepare();(self.directory/'page-1.png').write_bytes(b'changed')
        reply=self.client.post(self.page+'/vision',json={'request_id':str(uuid4()),'plan_hash':p['plan_hash']})
        self.assertEqual(reply.status_code,409)

    def test_original_mutation_after_enqueue_stops_before_model(self):
        job=self.begin();(self.directory/'page-1.png').write_bytes(b'changed')
        with patch('backend.materials.vision_service.recognize') as model:vision_service.run(job['id'],self.engine)
        model.assert_not_called()
        self.assertEqual(self.client.get(self.base+'/vision-jobs/'+job['id']).json()['status'],'failed')

    def test_scope_and_page_bounds(self):
        self.assertEqual(self.client.get(self.page.replace('/pages/1','/pages/3')+'/vision').status_code,422)
        other=self.fixture.prepared();foreign=f"/material-batches/{other['id']}/files/{other['files'][0]['id']}/processes/{self.file['process_id']}/pages/1/vision"
        self.assertEqual(self.client.get(foreign).status_code,404)
        job=self.begin()
        self.assertEqual(self.client.get(f"/material-batches/{other['id']}/files/{other['files'][0]['id']}/vision-jobs/{job['id']}").status_code,404)

    def test_read_saved_result_and_review_do_not_alter_source(self):
        job=self.begin()
        with patch('backend.materials.vision_service.recognize',return_value=RESULT):vision_service.run(job['id'],self.engine)
        result=self.client.get(self.base+'/vision-jobs/'+job['id']).json()
        self.assertEqual(result['status'],'ready');self.assertEqual(result['review'],'pending')
        url=self.base+'/vision-jobs/'+job['id']+'/review'
        response=self.client.patch(url,json={'expected_revision':1,'decision':'rejected','note':'核对发现错误'})
        self.assertEqual(response.status_code,200);self.assertEqual(response.json()['review'],'rejected')
        self.assertEqual(self.prepare()['maximum_calls'],1)
        self.assertEqual(self.client.patch(url,json={'expected_revision':1,'decision':'accepted'}).status_code,409)
        self.assertEqual(self.client.get(self.page+'/vision').json()['text'],'PAGE ONE synthetic text')

    def test_failure_redacts_provider_details_and_never_auto_retries(self):
        job=self.begin()
        with patch('backend.materials.vision_service.recognize',side_effect=RuntimeError('SECRET_SENTINEL raw private text')) as model:
            vision_service.run(job['id'],self.engine);vision_service.run(job['id'],self.engine)
        model.assert_called_once()
        response=self.client.get(self.base+'/vision-jobs/'+job['id'])
        self.assertNotIn('SECRET_SENTINEL',response.text);self.assertEqual(response.json()['status'],'failed')

    def test_recovery_marks_inflight_uncertain_without_retry(self):
        job=self.begin()
        with Session(self.engine) as db:db.get(PageRecognition,job['id']).status='running';db.commit()
        vision_service.recover(self.engine)
        with patch('backend.materials.vision_service.recognize') as model:vision_service.run(job['id'],self.engine)
        model.assert_not_called();self.assertEqual(self.client.get(self.base+'/vision-jobs/'+job['id']).json()['status'],'interrupted')

    def test_invalid_output_not_published_as_complete(self):
        job=self.begin()
        with patch('backend.materials.vision_service.recognize',return_value={'blocks':[],'issues':[]}):vision_service.run(job['id'],self.engine)
        self.assertEqual(self.client.get(self.base+'/vision-jobs/'+job['id']).json()['status'],'failed')

    def test_http_adapter_sends_png_and_text_without_retry(self):
        received=[]
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                received.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                payload={'id':'local-test','object':'chat.completion','created':1,'model':'test-vision',
                         'choices':[{'index':0,'message':{'role':'assistant','content':json.dumps(RESULT)},'finish_reason':'stop'}]}
                raw=json.dumps(payload).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(raw)
        server=HTTPServer(('127.0.0.1',0),Handler);thread=Thread(target=server.serve_forever,daemon=True);thread.start()
        runtime=SimpleNamespace(model='test-vision',api_key=SecretStr('LOCAL_FIXTURE_KEY'),base_url=f'http://127.0.0.1:{server.server_port}/v1',runtime_policy=ModelRuntimePolicy())
        try:
            with patch('backend.materials.vision_client.runtime_from_snapshot',return_value=runtime):
                self.assertEqual(vision_client.recognize(self.route,self.image,'synthetic'),RESULT)
        finally:server.shutdown();server.server_close();thread.join()
        self.assertEqual(len(received),1)
        content=received[0]['messages'][1]['content']
        self.assertTrue(content[1]['image_url']['url'].startswith('data:image/png;base64,'))
        self.assertEqual(base64.b64decode(content[1]['image_url']['url'].split(',')[1]),self.image)
        self.assertIn('synthetic',content[0]['text'])


if __name__=='__main__':unittest.main()
