"""浏览真实验收结果；仅打开 tmp/basic-live-* 中的独立测试库。

禁止模型生成、上传和配置修改；允许在测试数据上打开/翻阅学习卡片。
"""
import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    directory = args.directory.resolve()
    if (directory.parent != (ROOT / 'tmp').resolve() or
            not directory.name.startswith('basic-live-') or
            not (directory / 'acceptance.db').is_file()):
        parser.error('仅允许打开项目 tmp/basic-live-* 验收目录。')
    os.environ['MATERIAL_STORAGE_DIR'] = str(directory / 'materials')
    from fastapi.responses import JSONResponse
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    import uvicorn
    from backend.app import create_app
    from backend.database import get_db
    engine = create_engine(f"sqlite:///{directory / 'acceptance.db'}")
    app = create_app(initialize_database=False)
    def db():
        with Session(engine) as session:
            yield session
    app.dependency_overrides[get_db] = db

    @app.middleware('http')
    async def no_generation(request, call_next):
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            allowed = request.method == 'POST' and request.url.path.endswith('/tutor-session')
            if request.method == 'POST' and request.url.path.startswith('/tutor-sessions/') and request.url.path.endswith('/actions'):
                body = await request.json()
                allowed = body.get('action') in ('next', 'previous', 'open', 'answer')
            if not allowed:
                return JSONResponse(status_code=403, content={'detail': '验收预览不发起模型调用或修改配置。'})
        return await call_next(request)
    try:
        uvicorn.run(app, host='127.0.0.1', port=8002, log_level='warning')
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
