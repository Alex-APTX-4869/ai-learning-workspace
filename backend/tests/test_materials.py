"""临时数据库/合成资料；不读私人教材、不调用外部模型。"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import Session

from backend.app import create_app
from backend.database import Base, get_db
from backend.materials import service, workflow
from backend.materials.models import MaterialBatch, MaterialFile, MaterialProcess, MaterialAnalysisStep
from backend.materials.parser import ROOT, parse_document, sandbox_profile, MaterialParseError, validate_output
from backend.materials.requests import AnalysisSummary
from backend.intake.schemas import GeneratedDepthPlan
from backend.intake.models import IntakeSession
from backend.courses.models import Course
from backend.tests.test_intake import DEPTHS


class MaterialsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.env = patch.dict(os.environ, {"MATERIAL_STORAGE_DIR": str(self.directory / "materials")})
        self.env.start()
        self.app = create_app(initialize_database=False)
        self.engine = create_engine(f"sqlite:///{self.directory / 'test.db'}")
        Base.metadata.create_all(self.engine)
        def db():
            with Session(self.engine) as session:
                yield session
        self.app.dependency_overrides[get_db] = db
        self.client = TestClient(self.app)
        self.snapshot = {"routes": {role: {"config_fingerprint": "f"*64,
                         "provider_name": "Local test only", "model": "test-model"}
                         for role in service.ANALYSIS_ROLES}}
        self.routing = patch("backend.materials.service.resolve_routing_snapshot", return_value=self.snapshot)
        self.routing.start()

    def tearDown(self):
        self.routing.stop()
        self.client.close()
        self.engine.dispose()
        self.env.stop()
        self.temp.cleanup()

    def batch(self):
        response = self.client.post('/material-batches', json={"request_id": str(uuid4()), "name": "Test course", "intro": "Learn from materials"})
        self.assertEqual(response.status_code, 201)
        return response.json()

    def upload(self, batch, content=b"test", request_id=None, filename="notes.pdf"):
        return self.client.put(f"/material-batches/{batch['id']}/files/{request_id or uuid4()}",
                               params={"filename": filename, "expected_revision": batch['revision']},
                               content=content, headers={"Content-Type": "application/octet-stream"})

    def prepared(self, needs_review=False, text="Test source evidence"):
        batch = self.upload(self.batch()).json()
        file = batch['files'][0]
        with Session(self.engine) as db:
            process = db.get(MaterialProcess, file['process_id'])
            process.status = "needs_review" if needs_review else "ready"
            process.report_json = {"page_count": 2, "coverage": {}, "artifacts": [],
                "issues": [{"code": "visual_review_pending", "locator": {"type": "pdf_page", "page": 1}}] if needs_review else [],
                "elements": [{"id": "e1", "text": text, "locator": {"type": "pdf_page", "page": 1}},
                             {"id": "e2", "text": "SECOND PAGE", "locator": {"type": "pdf_page", "page": 2}}]}
            db.commit()
        return self.client.get(f"/material-batches/{batch['id']}").json()

    def annotate(self, batch, **overrides):
        file = batch['files'][0]
        payload = {"expected_revision": file['revision'], "included": True, "text_only_accepted": True,
                   "annotations": [{"role": "chapter", "chapter": "第 5 章", "page_start": 1, "page_end": 1}]}
        return self.client.patch(f"/material-batches/{batch['id']}/files/{file['id']}", json={**payload, **overrides})

    def start(self, batch):
        prefix = f"/material-batches/{batch['id']}"
        plan = self.client.get(prefix+'/analysis-plan')
        self.assertEqual(plan.status_code, 200, plan.text)
        data = {"expected_revision": plan.json()['revision'], "routing_hash": plan.json()['routing_hash']}
        response = self.client.post(prefix+'/analyze', json=data)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_upload_idempotence_conflict_and_batch_scope(self):
        batch = self.batch()
        rid = str(uuid4())
        first = self.upload(batch, request_id=rid)
        self.assertEqual(first.status_code, 201)
        duplicate = self.upload(batch, request_id=rid)
        self.assertEqual(duplicate.json()['files'][0]['id'], first.json()['files'][0]['id'])
        self.assertEqual(len(duplicate.json()['files']), 1)
        self.assertEqual(self.upload(batch, b"different", request_id=rid).status_code, 409)
        self.assertEqual(self.upload(batch).status_code, 409)
        file = first.json()['files'][0]
        another = self.batch()
        self.assertEqual(self.client.get(f"/material-batches/{another['id']}/files/{file['id']}/original").status_code, 404)

    def test_invalid_files_and_annotation_bounds(self):
        batch = self.batch()
        for filename in ('../secret.pdf', 'notes.exe'):
            self.assertEqual(self.upload(batch, filename=filename).status_code, 422)
        self.assertEqual(self.upload(batch, b'').status_code, 422)
        batch = self.prepared()
        self.assertEqual(self.annotate(batch, annotations=[{"role": "chapter"}]).status_code, 422)
        self.assertEqual(self.annotate(batch, annotations=[{"page_start": 1, "page_end": 3}]).status_code, 422)
        updated = self.annotate(batch)
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(self.annotate(batch).status_code, 409)

    def test_review_ack_and_page_range_freeze(self):
        batch = self.prepared(needs_review=True)
        prefix = f"/material-batches/{batch['id']}"
        self.assertEqual(self.client.get(prefix+'/analysis-plan').status_code, 409)
        batch = self.annotate(batch).json()
        started = self.start(batch)
        self.assertEqual(self.annotate(started).status_code, 409)
        self.assertEqual(self.client.post(prefix+'/reopen', json={"expected_revision": started['revision']}).status_code, 409)
        seen = []
        def generate(system, user, model, **kwargs):
            seen.append(user)
            self.assertEqual(kwargs['snapshot'], self.snapshot)
            return AnalysisSummary(summary="Only the first page", topics=["Test"], gaps=[])
        with patch('backend.materials.workflow.generate_json_messages', side_effect=generate):
            workflow.run_analysis(batch['id'], self.engine)
        ready = self.client.get(prefix).json()
        self.assertEqual(ready['status'], 'ready')
        self.assertNotIn('SECOND PAGE', '\n'.join(seen))
        self.assertEqual(ready['context']['files'][0]['annotations'][0]['chapter'], '第 5 章')

    def test_model_change_between_plan_and_start_is_rejected(self):
        batch = self.prepared()
        prefix = f"/material-batches/{batch['id']}"
        plan = self.client.get(prefix+'/analysis-plan').json()
        self.snapshot['routes']['materials.summarize']['model'] = 'changed'
        result = self.client.post(prefix+'/analyze', json={"expected_revision": batch['revision'], "routing_hash": plan['routing_hash']})
        self.assertEqual(result.status_code, 409)
        self.assertEqual(self.client.get(prefix).json()['status'], 'editing')

    def test_chunk_budget_counts_locators_and_json_escaping(self):
        elements = [{"id": f"e{i+1}", "text": '"\n'*50, "locator": {"type":"pdf_page", "page":1}} for i in range(500)]
        pieces = service.chunks(elements)
        self.assertTrue(all(len(json.dumps(piece, ensure_ascii=False)) <= 8000 for piece in pieces))
        self.assertEqual(''.join(e['text'] for piece in pieces for e in piece), ''.join(e['text'] for e in elements))

    def test_failed_analysis_reuses_complete_checkpoint(self):
        batch = self.start(self.prepared(text='x'*9000))
        summary = AnalysisSummary(summary="Checkpoint", topics=[], gaps=[])
        with patch('backend.materials.workflow.generate_json_messages', side_effect=[summary, RuntimeError('offline')]):
            workflow.run_analysis(batch['id'], self.engine)
        prefix = f"/material-batches/{batch['id']}"
        failed = self.client.get(prefix).json()
        self.assertEqual(failed['status'], 'failed')
        self.assertEqual(failed['analysis_completed_steps'], 1)
        self.start(failed)
        with patch('backend.materials.workflow.generate_json_messages', return_value=summary) as model:
            workflow.run_analysis(batch['id'], self.engine)
        self.assertEqual(model.call_count, 2)  # second source part + merge, not first source part
        self.assertEqual(self.client.get(prefix).json()['status'], 'ready')

    def test_analysis_precedes_intake_and_context_is_server_owned(self):
        batch = self.prepared()
        payload = {"name": batch['name'], "intro": batch['intro'], "material_batch_id": batch['id']}
        self.assertEqual(self.client.post('/course-intakes', json=payload).status_code, 409)
        self.start(batch)
        with patch('backend.materials.workflow.generate_json_messages', return_value=AnalysisSummary(summary="Evidence marker", topics=[], gaps=[])):
            workflow.run_analysis(batch['id'], self.engine)
        with patch('backend.intake.service.generate_depth_plan', return_value=GeneratedDepthPlan.model_validate(DEPTHS)) as model:
            response = self.client.post('/course-intakes', json=payload)
            self.assertEqual(response.status_code, 201, response.text)
            repeated = self.client.post('/course-intakes', json=payload)
            self.assertEqual(repeated.json()['id'], response.json()['id'])
            self.assertEqual(model.call_count, 1)
            self.assertIn('Evidence marker', model.call_args.args[0].intro)
        linked = self.client.get(f"/material-batches/{batch['id']}").json()
        self.assertEqual(linked['status'], 'linked')

    def test_recovery_does_not_auto_replay_ambiguous_model_calls(self):
        batch = self.prepared()
        with Session(self.engine) as db:
            db.get(MaterialBatch, batch['id']).status = 'analyzing'
            db.get(MaterialProcess, batch['files'][0]['process_id']).status = 'processing'
            db.commit()
        workflow.recover(self.engine)
        current = self.client.get(f"/material-batches/{batch['id']}").json()
        self.assertEqual(current['status'], 'needs_attention')
        self.assertEqual(current['files'][0]['status'], 'queued')

    def test_course_materials_cannot_read_other_course_batch(self):
        batch = self.prepared()
        with Session(self.engine) as db:
            course = Course(name='Linked', intro='Test')
            other = Course(name='Other', intro='Test')
            db.add_all([course, other]); db.flush()
            intake = IntakeSession(initial_name='Linked', initial_intro='Test', status='completed', course_id=course.id)
            db.add(intake); db.flush()
            row = db.get(MaterialBatch, batch['id'])
            row.intake_id, row.status = intake.id, 'linked'
            ids = course.id, other.id
            db.commit()
        self.assertEqual(self.client.get(f'/material-batches/for-course/{ids[0]}').json()['id'], batch['id'])
        self.assertIsNone(self.client.get(f'/material-batches/for-course/{ids[1]}').json())
        self.assertEqual(self.client.get('/material-batches/for-course/99999').status_code, 404)

    @unittest.skipUnless(sys.platform == 'darwin' and (ROOT / '.venv-materials/bin/python').exists(), 'Mac parser required')
    def test_uploaded_synthetic_pdf_is_parsed_and_preview_is_scoped(self):
        fixture = ROOT/'tmp/material-fixtures-m3a/core/lecture.pdf'
        if not fixture.exists(): self.skipTest('Synthetic fixture missing')
        batch = self.upload(self.batch(), fixture.read_bytes()).json()
        file = batch['files'][0]
        workflow.run_parse(file['process_id'], self.engine)
        current = self.client.get(f"/material-batches/{batch['id']}").json()
        self.assertEqual(current['files'][0]['status'], 'needs_review')
        prefix = f"/material-batches/{batch['id']}/files/{file['id']}/processes/{file['process_id']}"
        report = self.client.get(prefix).json()
        self.assertEqual(report['page_count'], 2)
        preview = self.client.get(prefix+'/artifacts/'+report['artifacts'][0]['path'])
        self.assertEqual(preview.status_code, 200)
        self.assertTrue(preview.content.startswith(b'\x89PNG'))
        self.assertEqual(self.client.get(prefix+'/artifacts/unknown.png').status_code, 404)
        other = self.batch()
        self.assertEqual(self.client.get(prefix.replace(batch['id'], other['id'])).status_code, 404)


@unittest.skipUnless(sys.platform == 'darwin' and (ROOT / '.venv-materials/bin/python').exists(), 'Mac isolated parser runtime required')
class LocalParserTests(unittest.TestCase):
    def test_unsupported_and_invalid_documents_are_not_success(self):
        fixtures = ROOT/'tmp/material-fixtures-m3a/core'
        if not fixtures.is_dir(): self.skipTest('Synthetic fixtures missing')
        expected = {'encrypted.pdf':'encrypted_document', 'fake.pdf':'format_mismatch',
                    'macro.docx':'active_content_not_supported', 'path-traversal.docx':'unsafe_archive_entry',
                    'legacy-signature.doc':'legacy_doc_converter_required'}
        with tempfile.TemporaryDirectory() as temporary:
            for name, code in expected.items():
                with self.subTest(name=name), self.assertRaises(MaterialParseError) as error:
                    parse_document(fixtures/name, Path(temporary)/name)
                self.assertEqual(error.exception.code, code)

    def test_real_synthetic_pdf_word_and_scan(self):
        fixtures = ROOT / 'tmp/material-fixtures-m3a/core'
        if not fixtures.is_dir():
            self.skipTest('Synthetic local fixtures not installed')
        with tempfile.TemporaryDirectory() as temporary:
            for name in ('lecture.pdf', 'structure.docx', 'scan.pdf', 'chart.png'):
                with self.subTest(name=name):
                    output = Path(temporary) / name
                    report = parse_document(fixtures / name, output)
                    self.assertEqual(report.status, 'needs_review')
                    self.assertEqual(report.external_requests, 0)
                    self.assertEqual(validate_output(output, report.source_sha256), report)
                    if report.artifacts:
                        (output / report.artifacts[0].path).unlink()
                        with self.assertRaises(MaterialParseError):
                            validate_output(output, report.source_sha256)

    def test_sandbox_blocks_unrelated_reads_writes_and_network(self):
        with tempfile.TemporaryDirectory() as temporary:
            parent = Path(temporary).resolve()
            work = parent / 'allowed'
            work.mkdir()
            # Synthetic marker, never inspect a user's secret file.
            private = parent / 'private-marker'
            private.touch()
            code = f'''import socket, pathlib, json
result=[]
for operation in [lambda: pathlib.Path({str(private)!r}).read_bytes(), lambda: pathlib.Path({str(parent / 'forbidden')!r}).touch(), lambda: socket.create_connection(("127.0.0.1", 9), timeout=1)]:
    try: operation(); result.append("allowed")
    except PermissionError: result.append("denied")
    except OSError as error: result.append(str(error.errno))
print(json.dumps(result))
'''
            python = ROOT / '.venv-materials/bin/python'
            result = subprocess.run(['/usr/bin/sandbox-exec', '-p', sandbox_profile(work, python), str(python), '-I', '-c', code], cwd=work, capture_output=True, text=True, timeout=10, env={"PATH":"/usr/bin:/bin"})
            self.assertEqual(result.returncode, 0, result.stderr[:400])
            self.assertEqual(json.loads(result.stdout), ['denied', 'denied', 'denied'])
