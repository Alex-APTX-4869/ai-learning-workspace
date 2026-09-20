"""Opt-in real-model grounding check, cloning ONLY the existing synthetic fixture."""
import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.accept_basic_live import Acceptance
from backend.ai import client as ai_client
from backend.app import create_app
from backend.database import get_db
from backend.workflows.content import run_learning_job
from backend.tutor.workflow import run_tutor_turn
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-real-models', action='store_true')
    parser.add_argument('--section-index', type=int, choices=(0, 1), default=0,
                        help='0: path example lacking evidence; 1: basic 422 meaning supported by text')
    args = parser.parse_args()
    if not args.run_real_models:
        parser.error('Requires explicit --run-real-models; maximum 10 model calls.')
    # Deliberately fixed: never accept an arbitrary user/production DB path.
    fixture = ROOT / 'tmp/basic-live-gdoec1vl'
    output = Path(tempfile.mkdtemp(prefix='basic-live-grounding-', dir=ROOT / 'tmp'))
    with sqlite3.connect(f'file:{fixture / "acceptance.db"}?mode=ro', uri=True) as source, sqlite3.connect(output / 'acceptance.db') as destination:
        source.backup(destination)
    shutil.copytree(fixture / 'materials', output / 'materials')
    course = json.loads((fixture / 'course.json').read_text())
    audit = Acceptance(output, 10)
    audit.save('course', course)
    engine = create_engine(f'sqlite:///{output / "acceptance.db"}')
    app = create_app(initialize_database=False)
    def database():
        with Session(engine) as db:
            yield db
    app.dependency_overrides[get_db] = database
    print(f'OUTPUT {output}', flush=True)
    with ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ, {'MATERIAL_STORAGE_DIR': str(output / 'materials')}))
        stack.enter_context(patch.object(ai_client, 'get_llm', audit.instrument(ai_client.get_llm)))
        audit.client = stack.enter_context(TestClient(app))
        try:
            audit.stage = 'grounded_content'
            point = course['chapters'][0]['sections'][args.section_index]['points'][0]
            base = f'/courses/{course["id"]}/points/{point["id"]}'
            params = {'outline_version_id': course['outline_version_id']}
            previous = audit.client.get(base + '/content', params=params)
            previous_id = previous.json()['id'] if previous.status_code == 200 else None
            job = audit.request('POST', base + '/content/jobs', params=params)
            run_learning_job(job['id'], engine)
            job = audit.request('GET', f'/learning-jobs/{job["id"]}')
            audit.save('content-job', job)
            if args.section_index == 0:
                audit.check(job['status'] == 'needs_review', '缺乏必要原文的路径示例未自动发布')
                current = audit.client.get(base + '/content', params=params)
                current_id = current.json()['id'] if current.status_code == 200 else None
                audit.check(current_id == previous_id, '资料不足时保留旧内容选择')
                audit.save('result', {'passed': True, 'case': 'insufficient_evidence',
                                      'calls': len(audit.calls), 'checks': audit.checks})
                print('PASS insufficient-evidence guard', flush=True)
                return 0
            audit.check(job['status'] == 'ready', '新原文驱动内容通过审查并发布到隔离库')
            content = audit.request('GET', base + '/content', params=params)
            audit.save('content', content)
            audit.check(content['id'] == job['content_version_id'], '读取的是本次生成结果，不是旧版本')
            evidence = content['content']['material_evidence']
            audit.check(bool(evidence['sources']), '实际读取并持久保存原文')
            used = {sid for card in content['content']['lesson_cards'] for sid in card['source_ids']}
            audit.check(bool(used), '讲解包含显式原文引用')
            for source in evidence['sources']:
                audit.check(source['locator'].get('page') == 1, '来源仅来自已确认的第一页')
                passage = audit.request('GET', f'/material-batches/for-course/{course["id"]}/source', params={
                    **params, **{key:source[key] for key in ('file_id','process_id','element_id','offset')}})
                audit.check(passage['text'].startswith(source['excerpt']), '出处入口回读与生成快照一致')
            audit.stage = 'grounded_teacher'
            session = audit.request('POST', base + '/tutor-session', params=params)
            turn = audit.request('POST', f'/tutor-sessions/{session["id"]}/actions', json={
                'request_id': str(uuid4()), 'revision': session['revision'], 'card_id': session['current_card']['id'],
                'action':'message', 'message':'这张卡片依据教材哪一页？用一句简单的话解释资料中的422是什么意思；如果原文不足请直接说明。'})
            # The normal action endpoint returns the session; queued turn is last.
            pending = turn['turns'][-1]
            run_tutor_turn(pending['id'], engine)
            session = audit.request('GET', f'/tutor-sessions/{session["id"]}')
            audit.save('tutor', session)
            audit.check(session['turns'][-1]['status'] == 'ready', '讲师原文答疑完成')
            audit.save('result', {'passed': True, 'calls': len(audit.calls), 'checks': audit.checks})
            print('PASS grounding acceptance', flush=True)
        except Exception as error:
            audit.save('result', {'passed': False, 'error_type': type(error).__name__, 'stage': audit.stage})
            print(f'FAILED {type(error).__name__} at {audit.stage}', flush=True)
            return 1
        finally:
            engine.dispose()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
