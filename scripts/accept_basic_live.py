"""显式选择的真实模型验收，不在普通测试发现中运行。

从正式库只读复制模型配置到独立 SQLite；不复制课程、不写钥匙串。
模型调用仍使用生产客户端、提示词和工作流。合成资料与输出留在 tmp，
便于复核；不记录凭据或供应商原始错误正文。
"""
import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from backend.app import create_app
from backend.database import Base, get_db, get_engine
from backend.ai import client as ai_client
from backend.materials import workflow as materials
from backend.providers.models import LlmProvider, LLMModelConfig, LLMRoleBinding
from backend.providers.roles import ROLE_DEFINITIONS
from backend.providers.routing import resolve_routing_snapshot
from backend.workflows.content import run_learning_job
from backend.tutor.workflow import run_tutor_turn


INTRO = ('我是会 Python 变量和函数、但不懂 HTTP 的初学者，已经能启动 FastAPI。'
         '只想用 20 分钟学会根据上传资料读懂 422 响应，并修正一个整数路径参数。'
         '这是全部资料；不扩展数据库、部署或其他框架。先通俗讲解，再看示例、做一道客观题。'
         '成功标准是看懂 loc、msg、type，能把 /items/abc 改为 /items/3 并说明原因。')


class Acceptance:
    def __init__(self, output, max_calls, resume_content=False):
        self.output, self.max_calls = output, max_calls
        self.resume_content = resume_content
        self.calls, self.checks = [], []
        if resume_content:
            self.calls = json.loads((output / 'calls.json').read_text())
            self.checks = json.loads((output / 'checks.json').read_text())
        self.stage = 'setup'

    def save(self, name, value):
        (self.output / (name + '.json')).write_text(
            json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding='utf-8')

    def check(self, condition, label):
        if not condition:
            raise AssertionError(label)
        self.checks.append(label)
        self.save('checks', self.checks)

    def request(self, method, path, **kwargs):
        response = self.client.request(method, path, **kwargs)
        if response.status_code >= 400:
            self.save('http-failure', {'stage': self.stage, 'status': response.status_code,
                                      'body': response.json()})
            raise AssertionError(f'{self.stage}: HTTP {response.status_code}')
        return response.json()

    def instrument(self, original):
        audit = self
        def create(**kwargs):
            llm = original(**kwargs)
            class RecordedModel:
                def run(self, method, value):
                    if len(audit.calls) >= audit.max_calls:
                        raise HTTPException(429, '本轮验收已达到模型调用上限，停止而不自动重试。')
                    record = {'role': kwargs.get('role'), 'stage': audit.stage,
                              'model': llm.model_name, 'status': 'running'}
                    audit.calls.append(record)
                    call_number = len(audit.calls)
                    audit.save('calls', audit.calls)
                    print(f"CALL {len(audit.calls)} {record['role']}", flush=True)
                    start = time.monotonic()
                    output_parts = []
                    try:
                        if method == 'stream':
                            for chunk in llm.stream(value):
                                if isinstance(chunk.content, str):
                                    output_parts.append(chunk.content)
                                yield chunk
                        else:
                            reply = llm.invoke(value)
                            record['usage'] = reply.usage_metadata
                            output_parts.append(reply.content)
                            yield reply
                        record['status'] = 'complete'
                    except Exception as error:
                        record['status'] = 'failed'
                        record['error_type'] = type(error).__name__
                        record['http_status'] = getattr(error, 'status_code', None)
                        raise
                    finally:
                        record['seconds'] = round(time.monotonic() - start, 2)
                        audit.save(f'model-output-{call_number}', output_parts)
                        audit.save('calls', audit.calls)
                        print(f"RESULT {record['status']} {record['seconds']}s", flush=True)
                def invoke(self, value):
                    return list(self.run('invoke', value))[0]
                def stream(self, value):
                    return self.run('stream', value)
            return RecordedModel()
        return create

    def run(self):
        engine = create_engine(f"sqlite:///{self.output / 'acceptance.db'}")
        Base.metadata.create_all(engine)
        # Only model configuration is copied. No secret values or user course data.
        with Session(get_engine()) as source, Session(engine) as target:
            for model in (LlmProvider, LLMModelConfig, LLMRoleBinding):
                if self.resume_content:
                    break
                query = select(model)
                if model is LLMRoleBinding:
                    query = query.where(model.scope_key == 'global')
                for row in source.scalars(query):
                    target.add(model(**{c.name: getattr(row, c.name) for c in model.__table__.columns}))
                target.flush()
            target.commit()
        app = create_app(initialize_database=False)
        def db():
            with Session(engine) as session:
                yield session
        app.dependency_overrides[get_db] = db
        with ExitStack() as stack:
            stack.enter_context(patch.dict(os.environ, {'MATERIAL_STORAGE_DIR': str(self.output / 'materials')}))
            stack.enter_context(patch.object(ai_client, 'get_llm', self.instrument(ai_client.get_llm)))
            self.client = stack.enter_context(TestClient(app))
            try:
                if self.resume_content:
                    self.learn(engine, json.loads((self.output / 'course.json').read_text()))
                else:
                    self.flow(engine)
            finally:
                engine.dispose()

    def flow(self, engine):
        self.stage = 'materials'
        with Session(engine) as db:
            roles = [r.key for r in ROLE_DEFINITIONS
                     if not set(r.required_capabilities) & {'vision', 'embeddings'}]
            snapshot = resolve_routing_snapshot(db, roles)
            self.save('models', {k: {'provider': v['provider_name'], 'model': v['model']}
                                 for k, v in snapshot['routes'].items()})
        batch = self.request('POST', '/material-batches', json={
            'request_id': str(uuid4()), 'name': '验收：读懂 FastAPI 的 422 响应', 'intro': INTRO})
        prefix = f"/material-batches/{batch['id']}"
        batch = self.request('PATCH', prefix, json={
            'expected_revision': batch['revision'], 'name': batch['name'],
            'intro': INTRO, 'completeness': 'complete'})
        source = ROOT / 'tmp/material-fixtures-m3a/core/lecture.pdf'
        batch = self.request('PUT', prefix + '/files/' + str(uuid4()),
            params={'filename': 'synthetic-http.pdf', 'expected_revision': batch['revision']},
            content=source.read_bytes(), headers={'Content-Type': 'application/octet-stream'})
        file = batch['files'][0]
        materials.run_parse(file['process_id'], engine)
        batch = self.request('GET', prefix)
        file = batch['files'][0]
        self.check(file['status'] in ('ready', 'needs_review'), '真实 PDF 解析成功')
        batch = self.request('PATCH', prefix + '/files/' + file['id'], json={
            'expected_revision': file['revision'], 'included': True, 'text_only_accepted': True,
            'annotations': [{'role': 'reference', 'page_start': 1, 'page_end': 1,
                             'note': '只使用第一页 HTTP 文字；第二页 SQL 不在课程范围。图表不作为依据。'}]})
        plan = self.request('GET', prefix + '/analysis-plan')
        self.request('POST', prefix + '/analyze', json={
            'expected_revision': plan['revision'], 'routing_hash': plan['routing_hash']})
        materials.run_analysis(batch['id'], engine)
        batch = self.request('GET', prefix)
        self.save('materials', batch)
        self.check(batch['status'] == 'ready', '真实资料分析完成')

        self.stage = 'intake'
        intake = self.request('POST', '/course-intakes', json={
            'name': batch['name'], 'intro': INTRO, 'material_batch_id': batch['id']})
        self.save('depth', intake)
        intake_path = f"/course-intakes/{intake['id']}"
        intake = self.request('POST', intake_path + '/depth', json={'question_count': 1})
        for index in range(4):
            self.save(f'question-{index}', intake)
            if intake['status'] != 'interviewing':
                break
            question = intake['current_question']
            intake = self.request('POST', intake_path + '/answers', json={
                'question_id': question['id'], 'custom_answer': INTRO})
        self.save('intake', intake)
        self.check(intake['status'] == 'ready_to_confirm', '需求确认能收束到课程信息')
        result = self.request('POST', intake_path + '/confirm', json={})
        course = result['course']
        course_path = f"/courses/{course['id']}"
        again = self.request('POST', intake_path + '/confirm', json={})
        self.check(again['course']['id'] == course['id'], '重复确认不重复建课')

        self.stage = 'outline'
        response = self.client.post(course_path + '/outline-versions/stream', json={
            'additional_requirements': '只覆盖已确认的 20 分钟小主题，不扩展数据库或部署。'})
        self.check(response.status_code == 200, '大纲流接口成功')
        events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
        self.save('outline-events', events)
        self.check(not any(e.get('type') == 'error' for e in events), '流式大纲没有错误事件')
        versions = self.request('GET', course_path + '/outline-versions')
        self.check(bool(versions), '大纲版本已保存')
        version = versions[-1] if len(versions) == 1 else versions[0]
        version_id = version['id']
        active = self.request('POST', course_path + f'/outline-versions/{version_id}/activate')
        course = active['course']
        chapter = course['chapters'][0]
        self.stage = 'points'
        course = self.request('POST', course_path + f"/chapters/{chapter['id']}/points",
                              params={'outline_version_id': version_id})
        self.save('course', course)
        self.learn(engine, course)

    def learn(self, engine, course):
        # 生成知识点会发布新目录，必须采用返回值，不能沿用生成前的版本号。
        version_id = course['outline_version_id']
        course_path = f"/courses/{course['id']}"
        point = course['chapters'][0]['sections'][0]['points'][0]
        point_path = course_path + f"/points/{point['id']}"
        params = {'outline_version_id': version_id}
        self.stage = 'content'
        job = self.request('POST', point_path + '/content/jobs', params=params)
        duplicate = self.request('POST', point_path + '/content/jobs', params=params)
        self.check(job['id'] == duplicate['id'], '重复生成复用进行中的任务')
        run_learning_job(job['id'], engine)
        job = self.request('GET', f"/learning-jobs/{job['id']}")
        self.save('content-job', job)
        content = self.request('GET', point_path + '/content', params=params)
        self.save('content', content)

        self.stage = 'tutor'
        session = self.request('POST', point_path + '/tutor-session', params=params)
        session_path = f"/tutor-sessions/{session['id']}"
        self.check(len(session['card_tabs']) == 1, '讲课开始只打开一张卡片')
        payload = {'request_id': str(uuid4()), 'revision': session['revision'],
                   'card_id': session['current_card']['id'], 'action': 'message',
                   'message': '我刚开始学，请用一个日常例子解释这张卡片的核心意思，不要跳到下一张。'}
        pending = self.request('POST', session_path + '/actions', json=payload)
        repeated = self.request('POST', session_path + '/actions', json=payload)
        self.check(len(pending['turns']) == len(repeated['turns']), '重复提问不重复排队')
        run_tutor_turn(pending['turns'][-1]['id'], engine)
        session = self.request('GET', session_path)
        self.save('tutor', session)
        self.check(session['turns'][-1]['status'] == 'ready', '真实讲师回答已保存')
        self.check(session['current_card']['id'] == payload['card_id'], '答疑没有擅自翻页')
        reopened = self.request('POST', point_path + '/tutor-session', params=params)
        self.check(reopened['id'] == session['id'] and reopened['turns'] == session['turns'],
                   '退出重进恢复原对话')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-real-models', action='store_true', help='明确允许调用已配置的真实模型')
    parser.add_argument('--max-calls', type=int, default=24, choices=range(1, 25))
    parser.add_argument('--resume-content', type=Path, help='从指定隔离验收目录继续内容阶段，不重复调用已完成的模型')
    args = parser.parse_args()
    if not args.run_real_models:
        parser.error('必须显式提供 --run-real-models；普通测试不会触发外部调用。')
    (ROOT / 'tmp').mkdir(exist_ok=True)
    if args.resume_content:
        output = args.resume_content.resolve()
        if (output.parent != (ROOT / 'tmp').resolve() or not output.name.startswith('basic-live-')
                or not (output / 'course.json').is_file() or not (output / 'acceptance.db').is_file()):
            parser.error('只能继续 tmp/basic-live-* 下有已生成课程的验收库。')
    else:
        output = Path(tempfile.mkdtemp(prefix='basic-live-', dir=ROOT / 'tmp'))
    audit = Acceptance(output, args.max_calls, bool(args.resume_content))
    print(f'ARTIFACTS {output}', flush=True)
    try:
        audit.run()
    except Exception as error:
        audit.save('result', {'status': 'incomplete', 'stage': audit.stage,
                             'error_type': type(error).__name__,
                             'detail': error.detail if isinstance(error, HTTPException) else
                                       str(error) if isinstance(error, AssertionError) else '检查该阶段记录；未记录原始异常以保护凭据。'})
        print(f'INCOMPLETE {audit.stage} {type(error).__name__}', flush=True)
        return 1
    audit.save('result', {'status': 'software_flow_passed', 'quality_review': 'pending',
                         'model_calls': len(audit.calls)})
    print('FLOW PASSED; human quality review still required', flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
