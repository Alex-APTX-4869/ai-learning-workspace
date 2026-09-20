from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from fastapi.responses import StreamingResponse
from backend.intake.explanation import stream_explanation

from backend.database import get_db
from backend.intake import service
from backend.intake import extensions
from backend.intake.schemas import ExtensionDecision
from backend.intake.schemas import (
    AnswerSubmit,
    BriefConfirm,
    DepthSelect,
    ExtraQuestionRequest,
    IntakeConfirmation,
    IntakeCreate,
    IntakeRead,
    OptionExplanation,
)

router = APIRouter(prefix="/course-intakes", tags=["课程需求确认"])
Database = Annotated[Session, Depends(get_db)]


@router.post("", response_model=IntakeRead, status_code=201)
def create_intake(data: IntakeCreate, db: Database):
    return service.create_intake(db, data)


# 必须放在 /{intake_id} 前，避免 latest-active 被当成数字 ID。
@router.get("/latest-active", response_model=IntakeRead)
def get_latest_active_intake(db: Database):
    return service.get_latest_active_intake(db)


@router.get("/{intake_id}", response_model=IntakeRead)
def get_intake(intake_id: int, db: Database):
    return service.get_intake(db, intake_id)


@router.post("/{intake_id}/depth", response_model=IntakeRead)
def select_depth(intake_id: int, data: DepthSelect, db: Database):
    return service.select_depth(db, intake_id, data)


@router.post("/{intake_id}/answers", response_model=IntakeRead)
def submit_answer(intake_id: int, data: AnswerSubmit, db: Database):
    return service.submit_answer(db, intake_id, data)


@router.post(
    "/{intake_id}/questions/{question_id}/options/{option_id}/explain",
    response_model=OptionExplanation,
)
def explain_option(
    intake_id: int,
    question_id: str,
    option_id: str,
    db: Database,
):
    return service.explain_option(db, intake_id, question_id, option_id)


@router.post("/{intake_id}/extra-question", response_model=IntakeRead)
def add_extra_question(
    intake_id: int, data: ExtraQuestionRequest, db: Database
):
    raise HTTPException(410, "需要澄清时，访谈 Agent 会自动增加一道问题。")


@router.post("/{intake_id}/extension-decision", response_model=IntakeRead)
def decide_extension(intake_id: int, data: ExtensionDecision, db: Database):
    raise HTTPException(410, "补问已改为自动执行，请恢复访谈继续。")


@router.post("/{intake_id}/resume", response_model=IntakeRead)
def resume_intake(intake_id: int, db: Database):
    return extensions.resume_pending(db, intake_id)


@router.post("/{intake_id}/questions/{question_id}/options/{option_id}/explain-stream")
def explain_stream(intake_id: int, question_id: str, option_id: str, db: Database):
    return StreamingResponse(stream_explanation(db,intake_id,question_id,option_id),media_type='application/x-ndjson',
                             headers={'Cache-Control':'no-cache','X-Accel-Buffering':'no'})


@router.post("/{intake_id}/confirm", response_model=IntakeConfirmation)
def confirm_intake(intake_id: int, data: BriefConfirm, db: Database):
    return service.confirm_intake(db, intake_id, data.brief)
