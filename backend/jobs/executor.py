from __future__ import annotations

import logging
from threading import Event, Thread

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.learning.models import LearningGenerationJob
from backend.tutor.models import TutorTurn
from backend.tutor.workflow import run_tutor_turn
from backend.workflows.content import run_learning_job


class LocalJobWorker:
    """首版持久执行器：队列在数据库，线程只负责领取，不保存事实状态。"""

    lock_id = 2026090802

    def __init__(self, bind, poll_seconds: float = 0.5):
        self.bind = bind
        self.poll_seconds = poll_seconds
        self.stopping = Event()
        self.thread = Thread(target=self._loop, name="learning-job-worker", daemon=True)
        self.lock_connection = None
        self.acquired = False

    def acquire(self) -> bool:
        """PostgreSQL 全局锁保证同一数据库只有一个领取循环。"""
        if self.bind.dialect.name != "postgresql":
            self.acquired = True
            return True
        connection = self.bind.connect()
        acquired = bool(
            connection.exec_driver_sql(
                f"SELECT pg_try_advisory_lock({self.lock_id})"
            ).scalar()
        )
        if not acquired:
            connection.close()
            return False
        connection.commit()
        self.lock_connection = connection
        self.acquired = True
        return True

    def start(self):
        if not self.acquired:
            raise RuntimeError("持久工作进程尚未取得领取锁。")
        self.thread.start()

    def stop(self):
        if self.acquired:
            self.stopping.set()
            if self.thread.is_alive():
                self.thread.join(timeout=2)
            if self.thread.is_alive():
                # 在途模型调用不能被强制结束；保留 leader 锁直到进程退出。
                logging.getLogger(__name__).warning(
                    "Job worker is still finishing an in-flight request"
                )
                return
        if self.lock_connection is not None:
            self.lock_connection.exec_driver_sql(
                f"SELECT pg_advisory_unlock({self.lock_id})"
            )
            self.lock_connection.commit()
            self.lock_connection.close()
            self.lock_connection = None
        self.acquired = False

    def _next(self) -> tuple[str, int] | None:
        with Session(self.bind) as db:
            content_id = db.scalar(select(LearningGenerationJob.id).where(
                LearningGenerationJob.status == "queued"
            ).order_by(LearningGenerationJob.created_at, LearningGenerationJob.id).limit(1))
            if content_id is not None:
                return "content", content_id
            tutor_id = db.scalar(select(TutorTurn.id).where(
                TutorTurn.status == "queued"
            ).order_by(TutorTurn.id).limit(1))
            if tutor_id is not None:
                return "tutor", tutor_id
        return None

    def _loop(self):
        while not self.stopping.is_set():
            try:
                item = self._next()
            except Exception as error:
                logging.getLogger(__name__).error(
                    "Persistent queue lookup failed: %s", type(error).__name__
                )
                self.stopping.wait(self.poll_seconds)
                continue
            if item is None:
                self.stopping.wait(self.poll_seconds)
                continue
            kind, item_id = item
            try:
                self._execute(kind, item_id)
            except Exception as error:
                # 具体工作流负责持久化失败；这里只保护领取循环。
                logging.getLogger(__name__).error("Persistent worker failed: %s", type(error).__name__)

    def _execute(self, kind, item_id):
        if kind == "content":
            run_learning_job(item_id, self.bind)
        else:
            run_tutor_turn(item_id, self.bind)
