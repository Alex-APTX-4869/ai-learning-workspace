"""隔离浏览器验收：四色测试图和固定结果，不是真实识别效果，不调用外部模型。"""
from time import sleep
from unittest.mock import patch
import uvicorn
from sqlalchemy.orm import Session
from backend.tests.test_page_recognition import PageRecognitionTests, RESULT
from backend.materials.models import MaterialBatch
from backend.materials.queue import MaterialWorker
from backend.courses.models import Course
from backend.intake.models import IntakeSession


def main():
    fixture=PageRecognitionTests();fixture.setUp()
    worker=MaterialWorker(fixture.engine)
    try:
        with Session(fixture.engine) as db:
            course=Course(name='隔离验收 · PDF 单页识别',intro='合成图片与固定模型替身结果，仅验证交互流程，不代表识别质量。')
            db.add(course);db.flush()
            intake=IntakeSession(initial_name=course.name,initial_intro=course.intro,status='completed',course_id=course.id)
            db.add(intake);db.flush()
            batch=db.get(MaterialBatch,fixture.batch['id']);batch.intake_id=intake.id;batch.status='linked';db.commit()
        def synthetic_reply(*args):
            sleep(3)
            return RESULT
        with patch('backend.materials.vision_service.recognize',side_effect=synthetic_reply):
            worker.acquire();worker.start()
            uvicorn.run(fixture.fixture.app,host='127.0.0.1',port=8002,log_level='warning')
    finally:
        worker.stop();fixture.tearDown()


if __name__=='__main__':main()
