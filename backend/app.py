import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from backend.ai.router import router as ai_router
from backend.courses.router import router as courses_router
from backend.database import Base, get_engine


def create_app(initialize_database: bool = True) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if initialize_database:
            # 只创建缺失表，不清空已有表；表结构变更以后使用迁移。
            Base.metadata.create_all(get_engine())
        yield

    app = FastAPI(title="个人 AI 学习工作台", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Content-Type"],
    )
    app.include_router(courses_router)
    app.include_router(ai_router)

    @app.get("/")
    def read_root():
        return {"msg": "HEY!"}

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, error: SQLAlchemyError):
        logging.getLogger(__name__).error("Database operation failed: %s", type(error).__name__)
        return JSONResponse(status_code=503, content={"detail": "数据库暂时不可用，请检查 PostgreSQL 后重试。"})

    return app
