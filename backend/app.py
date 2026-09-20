import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from backend.ai.router import router as ai_router
from backend.courses.router import router as courses_router
from backend.database import Base, get_engine
from backend.intake.router import router as intake_router
from backend.learning.router import router as learning_router
from backend.learning.service import recover_interrupted_jobs
from backend.outlines.router import router as outlines_router
from backend.providers.router import router as providers_router
from backend.providers.security import redact_validation_errors
from backend.tutor.router import router as tutor_router
from backend.tutor.service import recover_interrupted_turns
from backend.versions.router import router as versions_router
from backend.migrations.runner import migrate
from backend.jobs.executor import LocalJobWorker
from backend.materials.router import router as materials_router
from backend.materials.queue import MaterialWorker
from backend.materials.workflow import recover as recover_materials
from backend.materials.vision_service import recover as recover_page_recognition


def create_app(initialize_database: bool = True, *, inline_jobs: bool = False) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        material_worker = None
        if initialize_database:
            # 只创建缺失表，不清空已有表；表结构变更以后使用迁移。
            engine = get_engine()
            migrate(engine)
            worker = LocalJobWorker(engine)
            if worker.acquire():
                recover_interrupted_jobs(engine)
                recover_interrupted_turns(engine)
                worker.start()
            else:
                worker = None
            material_worker = MaterialWorker(engine)
            if material_worker.acquire():
                recover_materials(engine)
                recover_page_recognition(engine)
                material_worker.start()
            else:
                material_worker = None
        else:
            worker = None
        try:
            yield
        finally:
            if material_worker is not None:
                material_worker.stop()
            if worker is not None:
                worker.stop()

    app = FastAPI(title="个人 AI 学习工作台", lifespan=lifespan)
    # 仅隔离测试可同步执行；真实应用统一由持久队列的 leader worker 领取。
    app.state.inline_jobs = inline_jobs
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        # 模型职责绑定使用 PUT，恢复继承使用 DELETE。
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["Content-Type"],
    )
    app.include_router(courses_router)
    app.include_router(ai_router)
    app.include_router(intake_router)
    app.include_router(learning_router)
    app.include_router(providers_router)
    app.include_router(outlines_router)
    app.include_router(tutor_router)
    app.include_router(versions_router)
    app.include_router(materials_router)

    @app.get("/")
    def read_root():
        return {"msg": "HEY!"}

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, error: SQLAlchemyError):
        logging.getLogger(__name__).error("Database operation failed: %s", type(error).__name__)
        return JSONResponse(status_code=503, content={"detail": "数据库暂时不可用，请检查 PostgreSQL 后重试。"})

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError):
        # 校验失败也不能把请求中的 API key 或 URL 内嵌凭据原样回显。
        detail = redact_validation_errors(error.errors())
        return JSONResponse(
            status_code=422,
            content={"detail": jsonable_encoder(detail)},
        )

    return app
