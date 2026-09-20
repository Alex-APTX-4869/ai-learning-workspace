from sqlalchemy import select
from sqlalchemy.orm import Session
from backend.jobs.executor import LocalJobWorker
from backend.materials.models import MaterialBatch, MaterialProcess
from backend.materials.workflow import run_analysis, run_parse
from backend.materials.vision_models import PageRecognition
from backend.materials.vision_service import run as run_vision

class MaterialWorker(LocalJobWorker):
    # 单独领取资料队列，长文档解析不占用讲师/内容队列的执行线程。
    lock_id = 2026090903

    def _next(self):
        with Session(self.bind) as db:
            process_id = db.scalar(select(MaterialProcess.id).where(MaterialProcess.status == "queued")
                                   .order_by(MaterialProcess.created_at).limit(1))
            if process_id:
                return "parse", process_id
            vision_id = db.scalar(select(PageRecognition.id).where(PageRecognition.status == "queued")
                                  .order_by(PageRecognition.created_at).limit(1))
            if vision_id:
                return "vision", vision_id
            batch_id = db.scalar(select(MaterialBatch.id).where(MaterialBatch.status == "queued")
                                 .order_by(MaterialBatch.created_at).limit(1))
            if batch_id:
                return "analysis", batch_id

    def _execute(self, kind, item_id):
        if kind == "parse":
            run_parse(item_id, self.bind)
        elif kind == "vision":
            run_vision(item_id, self.bind)
        else:
            run_analysis(item_id, self.bind)
