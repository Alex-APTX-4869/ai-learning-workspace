"""仅用于人工浏览器验收的临时服务；绝不写入真实课程库。

运行：python -m backend.tests.serve_material_retrieval_fixture
前端代理指向 127.0.0.1:8002，结束后 Ctrl+C 自动清理临时数据。
"""
from copy import deepcopy
from sqlalchemy.orm import Session
import uvicorn
from backend.tests.test_material_retrieval import MaterialRetrievalTests
from backend.tests.test_intake import BRIEF
from backend.versions.models import DirectoryManifest
from backend.outlines.models import CourseOutlineSelection, OutlineVersion


def main():
    fixture=MaterialRetrievalTests()
    fixture.setUp()
    try:
        course,versions,_=fixture.linked('连接池通过复用连接减少开销。\nHTTPException 可以返回 422 错误。\n'+('这是原文上下文，不是 AI 生成的回答。\n'*350))
        with Session(fixture.engine) as db:
            for version in versions:
                row=db.get(DirectoryManifest,version)
                db.get(OutlineVersion,version).outline_json={'name':'隔离验收课程','chapters':[{'name':'数据库','sections':[{'name':'连接池'}]}]}
                row.tree_json={'id':course,'name':'隔离验收课程 · 合成资料','intro':'临时测试，非真实课程，结束后自动清理。','chapters':[]}
                if row.brief_json:
                    row.brief_json={**deepcopy(BRIEF),**row.brief_json}
            db.add(CourseOutlineSelection(course_id=course,version_id=versions[-1]))
            db.commit()
        uvicorn.run(fixture.app,host='127.0.0.1',port=8002,log_level='warning')
    finally:
        fixture.tearDown()


if __name__=='__main__':
    main()
