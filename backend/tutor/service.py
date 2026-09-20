from __future__ import annotations

import hashlib
import re
from copy import deepcopy

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.courses import service as courses
from backend.courses.models import Course, Point
from backend.intake.service import get_confirmed_brief
from backend.learning.models import PointContentVersion, SectionPlan
from backend.learning.schemas import PointContent
from backend.learning.service import get_current_content
from backend.providers.routing import resolve_routing_snapshot
from backend.tutor.cards import build_deck, grade_exercise, learner_card
from backend.tutor.models import TutorSession, TutorTurn
from backend.tutor.schemas import TutorAction, TutorSessionRead, TutorTurnRead


def clear_advance_intent(message: str) -> bool:
    # 保守判断：否定、疑问、附带问题都留在本卡。其余表达可直接点下一张。
    normalized = re.sub(r"[\s，,。.!！]", "", message)
    return normalized in {
        "下一张", "下一张卡片", "下一个", "继续", "继续讲", "可以继续",
        "明白了继续", "懂了继续", "没有问题继续", "没问题继续", "没有问题了继续",
        "没有问题", "没有问题了", "没问题了", "我理解了继续", "我明白了可以继续", "next",
    }


def get_session(db: Session, session_id: int, *, lock: bool = False) -> TutorSession:
    statement = select(TutorSession).where(TutorSession.id == session_id)
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    session = db.scalar(statement)
    if session is None:
        raise HTTPException(404, "没有找到这次学习记录。")
    return session


def session_content(db: Session, session: TutorSession) -> PointContent:
    version = db.get(PointContentVersion, session.content_version_id)
    if version is None or version.point_id != session.point_id or version.status != "ready":
        raise HTTPException(409, "这次学习使用的内容版本不可用，请重新打开知识点。")
    return PointContent.model_validate(version.content_json)


def visited_positions(db: Session, session: TutorSession, deck: list[dict]) -> set[int]:
    positions = {card['id']: index for index, card in enumerate(deck)}
    visited = {0, session.card_index}
    rows = db.execute(select(TutorTurn.card_id, TutorTurn.action, TutorTurn.teacher_action).where(
        TutorTurn.session_id == session.id, TutorTurn.status == 'ready',
    ).distinct()).all()
    for card_id, action, teacher_action in rows:
        index = positions.get(card_id)
        if index is None:
            continue
        visited.add(index)
        if action == 'next' or teacher_action == 'show_next_card':
            visited.add(min(len(deck) - 1, index + 1))
        elif action == 'previous':
            visited.add(max(0, index - 1))
    return visited


def read_session(db: Session, session: TutorSession) -> TutorSessionRead:
    deck = build_deck(session_content(db, session))
    card = deck[session.card_index]
    rows = db.scalars(
        select(TutorTurn).where(TutorTurn.session_id == session.id)
        .order_by(TutorTurn.id.desc()).limit(201)
    ).all()
    truncated = len(rows)>200
    rows = list(reversed(rows[:200]))
    positions = {item['id']:i for i,item in enumerate(deck)}
    timeline = []
    def append_card(index, event_id):
        item=deck[index]
        timeline.append({'type':'card','id':event_id,'card':learner_card(item),'response':session.responses.get(item['id'])})
    initial_index = positions.get(rows[0].card_id,0) if truncated and rows else 0
    append_card(initial_index,'initial')
    for row in rows:
        index=positions.get(row.card_id)
        if index is None:
            continue
        if row.action=='message':
            timeline.append({'type':'message','id':f'turn-{row.id}','turn':TutorTurnRead.model_validate(row,from_attributes=True).model_dump()})
        if row.status=='ready':
            destination = None
            if row.action=='previous': destination=max(0,index-1)
            elif row.action=='next' or row.teacher_action=='show_next_card': destination=min(len(deck)-1,index+1)
            if destination is not None and destination!=index:
                append_card(destination,f'card-after-{row.id}')
    last_card = next((e for e in reversed(timeline) if e['type']=='card'),None)
    if not last_card or last_card['card']['id'] != card['id']:
        append_card(session.card_index,f'current-{session.revision}')
    stages: list[dict] = []
    for item in deck:
        if not stages or stages[-1]["kind"] != item["kind"]:
            stages.append({"kind": item["kind"], "count": 0})
        stages[-1]["count"] += 1
    return TutorSessionRead(
        id=session.id, course_id=session.course_id, point_id=session.point_id,
        outline_version_id=session.outline_version_id,
        content_version_id=session.content_version_id, revision=session.revision,
        card_index=session.card_index, card_count=len(deck), completed=session.completed,
        busy=session.pending_request_id is not None,
        current_card=learner_card(card),
        card_tabs=[{'id': deck[i]['id'], 'title': deck[i]['title'], 'kind': deck[i]['kind']}
                   for i in sorted(visited_positions(db, session, deck))],
        stages=stages, response=session.responses.get(card["id"]),
        turns=[TutorTurnRead.model_validate(row, from_attributes=True) for row in rows if row.action=='message'],
        timeline=timeline, timeline_truncated=truncated,
    )


def start_session(db: Session, course_id: int, point_id: int, *,
                  outline_version_id: int | None = None,
                  content_version_id: int | None = None) -> TutorSessionRead:
    # 与生成/保存内容保持相同 Course 行锁，开始学习时固定内容版本。
    course = courses.get_course(db, course_id, lock=True, outline_version_id=outline_version_id)
    outline_id = getattr(course, "outline_version_id", None)
    content = get_current_content(db, course_id, point_id, outline_version_id=outline_id)
    if content_version_id is not None and content.id != content_version_id:
        raise HTTPException(409, "当前目录选择的内容版本已经变化，请重新打开知识点。")
    build_deck(content.content)
    query = select(TutorSession).where(TutorSession.content_version_id == content.id, TutorSession.outline_version_id == outline_id)
    session = db.scalar(query)
    if session is None:
        session = TutorSession(course_id=course_id, point_id=point_id, content_version_id=content.id, outline_version_id=outline_id)
        db.add(session)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            session = db.scalar(query)
            if session is None:
                raise
    return read_session(db, session)


def show_next_card(session: TutorSession, deck: list[dict]) -> None:
    if session.card_index + 1 < len(deck):
        session.card_index += 1
        session.completed = False
    else:
        session.completed = True


def apply_action(db: Session, session_id: int, action: TutorAction) -> tuple[TutorSessionRead, int | None]:
    session = get_session(db, session_id, lock=True)
    request_id = str(action.request_id)
    payload_hash = hashlib.sha256(action.model_dump_json().encode()).hexdigest()
    existing = db.scalar(select(TutorTurn).where(
        TutorTurn.session_id == session_id, TutorTurn.request_id == request_id,
    ))
    if existing:
        if existing.payload_hash != payload_hash:
            raise HTTPException(409, "同一个请求编号不能用于不同操作。")
        return read_session(db, session), None
    deck = build_deck(session_content(db, session))
    card = deck[session.card_index]
    if session.revision != action.revision or card["id"] != action.card_id:
        raise HTTPException(409, "学习进度已在其他页面更新，请同步后继续。")
    if session.pending_request_id:
        raise HTTPException(409, "讲师正在回答，回答完成后可以继续操作。")
    turn = TutorTurn(
        session_id=session.id, request_id=request_id, payload_hash=payload_hash,
        revision_before=session.revision, card_id=card["id"], action=action.action,
        user_message=action.message, status="ready",
    )
    background_id = None
    if action.action == "message":
        turn.routing_snapshot_json = resolve_routing_snapshot(
            db,
            ["tutor.answer"],
            scope_type="course",
            scope_id=str(session.course_id),
        )
        turn.status = "queued"
        session.pending_request_id = request_id
    elif action.action == "answer":
        result = grade_exercise(card, action.selected, action.written_answer)
        session.responses = {**session.responses, card["id"]: result}
        session.revision += 1
    elif action.action == "open":
        target = next((i for i, item in enumerate(deck) if item['id'] == action.target_card_id), None)
        if target not in visited_positions(db, session, deck):
            raise HTTPException(422, "只能切换到已经打开的卡片对话。")
        session.card_index = target
        session.completed = False
        session.revision += 1
    elif action.action == "previous":
        session.card_index = max(0, session.card_index - 1)
        session.completed = False
        session.revision += 1
    else:
        show_next_card(session, deck)
        session.revision += 1
    db.add(turn)
    db.commit()
    if action.action == "message":
        background_id = turn.id
    return read_session(db, session), background_id


def teacher_context(db: Session, session: TutorSession, turn: TutorTurn) -> dict:
    content = session_content(db, session)
    deck = build_deck(content)
    current = learner_card(deck[session.card_index])
    if current["kind"] == "code_lab":
        current["lab"].pop("solution_code", None)
    version = db.get(PointContentVersion, session.content_version_id)
    plan = db.get(SectionPlan, version.plan_id) if version.plan_id else None
    point_scope = next((item for item in (plan.plan_json.get("point_plans", []) if plan else [])
                        if item["point_id"] == session.point_id), None)
    course = courses.get_course(db, session.course_id, outline_version_id=session.outline_version_id)
    if session.outline_version_id is not None:
        brief_json = course.brief_json
    else:
        brief = get_confirmed_brief(db, session.course_id)
        brief_json = brief.model_dump(mode="json") if brief else None
    point = db.get(Point, session.point_id)
    # 少量前文支持“上一张为什么……”类追问，不把整个课程正文重复送入模型。
    recent_cards = [learner_card(card) for card in deck[max(0, session.card_index - 2):session.card_index]]
    for card in recent_cards:
        if card["kind"] == "code_lab":
            card["lab"].pop("solution_code", None)
    rows = db.scalars(select(TutorTurn).where(
        TutorTurn.session_id == session.id, TutorTurn.id < turn.id,
        TutorTurn.action == "message", TutorTurn.status == "ready",
    ).order_by(TutorTurn.id.desc()).limit(12)).all()
    return {
        "course": {"name": course.name, "intro": course.intro},
        "point": {"name": point.name, "intro": point.intro},
        "course_brief": brief_json,
        "learning_goals": content.learning_goals,
        "scope": deepcopy(point_scope),
        "current_card": current,
        # Original passages come from the content version, never the latest file.
        "material_evidence": deepcopy(content.material_evidence),
        "recent_cards": recent_cards,
        "previous_card_titles": [item["title"] for item in deck[:session.card_index]],
        "upcoming_card_titles": [item["title"] for item in deck[session.card_index + 1:]],
        "exercise_response": deepcopy(session.responses.get(current["id"])),
        "conversation": [{"card_id": row.card_id, "user": (row.user_message or "")[:2000],
                          "teacher": (row.reply_markdown or "")[:3000]} for row in reversed(rows)],
        "user_message": turn.user_message,
        "advance_authorized": clear_advance_intent(turn.user_message or ""),
    }


def recover_interrupted_turns(bind) -> int:
    with Session(bind) as db:
        sessions = db.scalars(select(TutorSession).where(TutorSession.pending_request_id.is_not(None))).all()
        recovered = 0
        for session in sessions:
            turn = db.scalar(select(TutorTurn).where(
                TutorTurn.session_id == session.id, TutorTurn.request_id == session.pending_request_id,
            ))
            if turn and turn.status == "queued":
                # 请求尚未送出，由持久工作进程安全继续。
                recovered += 1
                continue
            if turn and turn.status == "running":
                turn.status = "failed"
                turn.error = "服务重启时模型请求结果不确定。为避免重复调用，请重新发送问题。"
            session.pending_request_id = None
            session.revision += 1
            recovered += 1
        db.commit()
        return recovered
