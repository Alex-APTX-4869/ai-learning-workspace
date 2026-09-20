import logging
from copy import deepcopy

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.ai.client import generate_json_messages
from backend.tutor.cards import build_deck
from backend.tutor.models import TutorTurn
from backend.tutor.prompts import tutor_messages
from backend.tutor.schemas import TutorDecision
from backend.tutor.service import (
    clear_advance_intent, get_session, session_content, show_next_card, teacher_context,
)


def generate_reply(
    context: dict, *, routing_snapshot: dict | None = None
) -> TutorDecision:
    system, human = tutor_messages(context)
    return generate_json_messages(
        system,
        human,
        TutorDecision,
        role="tutor.answer",
        snapshot=routing_snapshot,
    )


def run_tutor_turn(turn_id: int, bind) -> None:
    """答疑独立于页面生命周期；状态锁在模型调用前释放。"""
    try:
        with Session(bind) as db:
            peek = db.get(TutorTurn, turn_id)
            if peek is None:
                return
            session = get_session(db, peek.session_id, lock=True)
            turn = db.get(TutorTurn, turn_id, populate_existing=True)
            if turn.status != "queued" or session.pending_request_id != turn.request_id:
                return
            context = teacher_context(db, session, turn)
            routing_snapshot = deepcopy(turn.routing_snapshot_json)
            turn.status = "running"
            db.commit()
        reply = generate_reply(context, routing_snapshot=routing_snapshot)
        with Session(bind) as db:
            peek = db.get(TutorTurn, turn_id)
            session = get_session(db, peek.session_id, lock=True)
            turn = db.get(TutorTurn, turn_id, populate_existing=True)
            if turn.status != "running" or session.pending_request_id != turn.request_id:
                return
            if session.revision != turn.revision_before:
                raise HTTPException(409, "学习进度已变化，这次回答未应用。")
            requested_next = reply.action == "show_next_card"
            may_advance = clear_advance_intent(turn.user_message or "")
            if requested_next and not may_advance:
                # 不只是忽略错误动作，还避免展示模型误称“已翻页”的文字。
                raise HTTPException(502, "讲师误判了继续意图，请重新提问；当前卡片保持不变。")
            if requested_next:
                show_next_card(session, build_deck(session_content(db, session)))
            turn.reply_markdown = reply.reply_markdown
            turn.teacher_action = reply.action
            turn.status = "ready"
            session.pending_request_id = None
            session.revision += 1
            db.commit()
    except Exception as error:
        logging.getLogger(__name__).warning("Tutor reply failed: %s", type(error).__name__)
        message = error.detail if isinstance(error, HTTPException) else "讲师暂时未能回答，请稍后重试。"
        with Session(bind) as db:
            peek = db.get(TutorTurn, turn_id)
            if peek is None:
                return
            session = get_session(db, peek.session_id, lock=True)
            turn = db.get(TutorTurn, turn_id, populate_existing=True)
            if session.pending_request_id == turn.request_id:
                turn.status = "failed"
                turn.error = str(message)
                session.pending_request_id = None
                session.revision += 1
                db.commit()
