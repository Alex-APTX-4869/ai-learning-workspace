from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Request
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.tutor import service
from backend.tutor.schemas import TutorAction, TutorSessionRead
from backend.tutor.workflow import run_tutor_turn

router = APIRouter(tags=["交互讲师"])
Database = Annotated[Session, Depends(get_db)]


@router.post("/courses/{course_id}/points/{point_id}/tutor-session", response_model=TutorSessionRead)
def start_session(course_id: int, point_id: int, db: Database,
                  outline_version_id: int | None = Query(default=None, ge=1),
                  content_version_id: int | None = Query(default=None, ge=1)):
    return service.start_session(db, course_id, point_id,
                                 outline_version_id=outline_version_id,
                                 content_version_id=content_version_id)


@router.get("/tutor-sessions/{session_id}", response_model=TutorSessionRead)
def read_session(session_id: int, db: Database):
    return service.read_session(db, service.get_session(db, session_id))


@router.post("/tutor-sessions/{session_id}/actions", response_model=TutorSessionRead, status_code=202)
def act(session_id: int, action: TutorAction, request: Request,
        background: BackgroundTasks, db: Database):
    result, turn_id = service.apply_action(db, session_id, action)
    if turn_id is not None and request.app.state.inline_jobs:
        background.add_task(run_tutor_turn, turn_id, db.get_bind())
    return result
