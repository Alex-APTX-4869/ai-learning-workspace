"""隔离章节追加 UI 验收；仅临时 SQLite 和合成资料，不修改用户课程。"""
from unittest.mock import patch
import uvicorn
from backend.tests.test_chapter_expansion import ChapterExpansionTests
from backend.versions.expansion import NewChapter, NewSection


def main():
    fixture = ChapterExpansionTests(); fixture.setUp()
    try:
        batch_id, _ = fixture.batch()
        app = fixture.client.app
        @app.get('/fixture-expansion')
        def identity():
            return {'course_id':fixture.course_id,'version_id':fixture.o1,'batch_id':batch_id}
        with patch('backend.versions.expansion.generate_json_messages',return_value=NewChapter(
                name='合成章节',sections=[NewSection(name='追加资料内容'),NewSection(name='综合应用')])):
            uvicorn.run(app,host='127.0.0.1',port=8002,log_level='warning')
    finally:
        fixture.tearDown()


if __name__ == '__main__': main()
