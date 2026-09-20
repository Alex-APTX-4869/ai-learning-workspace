"""临时 SQLite、合成页面与模型替身；仅供 8002/5175 隔离 UI 验收。"""
from unittest.mock import patch
import uvicorn
from backend.tests.test_page_adoption import PageAdoptionTests
from backend.materials.queue import MaterialWorker
from backend.materials.requests import AnalysisSummary


def main():
    fixture=PageAdoptionTests();fixture.setUp()
    worker=MaterialWorker(fixture.engine)
    try:
        fixture.ready_job()
        app=fixture.v.fixture.app
        @app.get('/fixture-adoption')
        def identity():
            return {'batch_id':fixture.bid}
        with patch('backend.materials.workflow.generate_json_messages',return_value=AnalysisSummary(
            summary='合成公式与合成表格，仅验收流程。',topics=['合成公式'],gaps=[])):
            worker.acquire();worker.start()
            uvicorn.run(app,host='127.0.0.1',port=8002,log_level='warning')
    finally:
        worker.stop();fixture.tearDown()


if __name__=='__main__':main()
