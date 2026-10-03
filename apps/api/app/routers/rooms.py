"""Classrooms. Teachers (accounts) run rooms; students join with a code and a nickname and receive a room-scoped token.

REST changes the room and the WebSocket (`/rooms/{id}/live`) pushes the new state to everyone connected. Scores are computed by the
server from submitted strokes with the same scorer as the daily challenge.
"""
import asyncio
import json
import secrets
from datetime import timedelta
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Header, Request, Response, WebSocket, WebSocketDisconnect
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, get_current_user_optional, write_guard
from app.errors import ApiError
from app.inference import get_scorer
from app.models import Room, RoomMember, RoomRound, RoundSubmission, User, utcnow
from app.schemas_rooms import (JoinIn, JoinOut, RoomCreate, RoomState, RoomSummary, RoundDrawing, RoundStart, SubmitIn, SubmitOut)
from app.security import decode_session_token
from app.services.apikeys import hash_key
from app.services.drawings import enforce_limits, ink_length, normalise
from app.services.room_hub import Conn, RoomHub
from app.services.rooms import Viewer, build_state, latest_round, new_code, round_phase
from app.services.scoring import looks_automated, score_timeline

router = APIRouter(prefix="/rooms", tags=["classrooms"])
WS_AUTH_SECONDS = 5


def _hub(request: Request) -> RoomHub:
    return request.app.state.hub


def _now(request: Request):
    return request.app.state.clock()


def _summary(db: Session, room: Room) -> RoomSummary:
    members = db.scalar(select(func.count(RoomMember.id)).where(RoomMember.room_id == room.id)) or 0
    rounds = db.scalar(select(func.count(RoomRound.id)).where(RoomRound.room_id == room.id)) or 0
    return RoomSummary(id=room.id, name=room.name, code=room.code, closed=room.closed_at is not None, members=members, rounds=rounds,
                       created_at=room.created_at.isoformat())


def _owned(db: Session, user: User, room_id: int) -> Room:
    room = db.get(Room, room_id)
    if room is None or room.owner_id != user.id:          # 404, never 403: other teachers' rooms cannot be probed
        raise ApiError(404, "not_found", "Room not found.")
    return room


def _member(db: Session, room_id: int, token: str | None) -> RoomMember:
    member = db.scalar(select(RoomMember).where(RoomMember.token_hash == hash_key(token))) if token else None
    if member is None or member.room_id != room_id:
        raise ApiError(401, "invalid_room_token", "You are not in this room. Join it again with the code.")
    return member


def _viewer(request: Request, db: Session, room_id: int, user: User | None, token: str | None) -> tuple[Room, Viewer]:
    """The teacher (signed in as the owner) or a student (room token)."""
    room = db.get(Room, room_id)
    if room is None:
        raise ApiError(404, "not_found", "Room not found.")
    if token:
        return room, Viewer("student", _member(db, room_id, token))
    if user is not None and room.owner_id == user.id:
        return room, Viewer("teacher")
    if user is not None:
        raise ApiError(404, "not_found", "Room not found.")
    raise ApiError(401, "unauthenticated", "Sign in as the teacher, or join with the room code.")


def _user_from_cookie(request_like, db: Session, settings) -> User | None:
    token = request_like.cookies.get(settings.cookie_name)
    user_id = decode_session_token(token, settings.secret_key) if token else None
    return db.get(User, user_id) if user_id is not None else None


# ------------------------------------------------------------------ teacher: rooms

@router.post("", response_model=RoomSummary, status_code=201)
def create_room(body: RoomCreate, request: Request, user: User = Depends(write_guard), db: Session = Depends(get_db)):
    s = request.app.state.settings
    open_rooms = db.scalar(select(func.count(Room.id)).where(Room.owner_id == user.id, Room.closed_at.is_(None))) or 0
    if open_rooms >= s.max_open_rooms:
        raise ApiError(409, "too_many_rooms", f"You can have {s.max_open_rooms} open rooms. Close one first.")
    for _ in range(8):                                                  # a code collision is possible but rare: just draw another
        room = Room(owner_id=user.id, name=body.name, code=new_code())
        db.add(room)
        try:
            db.commit()
            return _summary(db, room)
        except IntegrityError:
            db.rollback()
    raise ApiError(503, "code_unavailable", "Could not create a room code. Try again.")


@router.get("", response_model=list[RoomSummary])
def my_rooms(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rooms = db.scalars(select(Room).where(Room.owner_id == user.id).order_by(Room.created_at.desc(), Room.id.desc()).limit(50))
    return [_summary(db, r) for r in rooms]


@router.post("/{room_id}/close", response_model=RoomSummary)
def close_room(room_id: int, request: Request, user: User = Depends(write_guard), db: Session = Depends(get_db)):
    room = _owned(db, user, room_id)
    rnd = latest_round(db, room.id)
    if rnd and round_phase(rnd, _now(request), request.app.state.settings) in ("drawing", "collecting"):
        rnd.ended_at = _now(request) - timedelta(seconds=request.app.state.settings.round_grace_s)     # no round outlives its room
    room.closed_at = room.closed_at or _now(request)
    db.commit()
    _hub(request).cancel_timers(room.id)
    _hub(request).notify(room.id)
    return _summary(db, room)


@router.delete("/{room_id}", status_code=204)
def delete_room(room_id: int, request: Request, user: User = Depends(write_guard), db: Session = Depends(get_db)):
    """Deletes the room with its students' nicknames and drawings."""
    room = _owned(db, user, room_id)
    db.delete(room)
    db.commit()
    _hub(request).close_room(room_id)
    return Response(status_code=204)


@router.post("/{room_id}/rounds", response_model=RoomState, status_code=201)
def start_round(room_id: int, body: RoundStart, request: Request, user: User = Depends(write_guard), db: Session = Depends(get_db)):
    s, now = request.app.state.settings, _now(request)
    room = _owned(db, user, room_id)
    if room.closed_at:
        raise ApiError(409, "room_closed", "This room is closed.")
    if not s.round_min_s <= body.duration_s <= s.round_max_s:
        raise ApiError(422, "bad_duration", f"A round lasts between {s.round_min_s} and {s.round_max_s} seconds.")
    current = latest_round(db, room.id)
    if current and round_phase(current, now, s) != "results":
        raise ApiError(409, "round_in_progress", "The current round has not finished yet.")
    classes = get_scorer(request).classes
    if body.target is not None and body.target not in classes:
        raise ApiError(422, "unknown_class", "The model does not know that object.", {"target": body.target})
    used = set(db.scalars(select(RoomRound.target).where(RoomRound.room_id == room.id)))
    target = body.target or secrets.choice([c for c in classes if c not in used] or classes)     # fresh words first
    number = (current.no if current else 0) + 1
    if number > s.max_rounds_per_room:
        raise ApiError(409, "too_many_rounds", f"A room can have {s.max_rounds_per_room} rounds. Create a new room to keep playing.")
    rnd = RoomRound(room_id=room.id, no=number, target=target, model_version=get_scorer(request).version, duration_s=body.duration_s,
                    started_at=now, ends_at=now + timedelta(seconds=body.duration_s))
    db.add(rnd)
    db.commit()
    hub = _hub(request)
    hub.schedule_round(room.id, rnd)
    hub.notify(room.id)
    return build_state(db, room, Viewer("teacher"), now, s, hub.online_members(room.id))


@router.post("/{room_id}/rounds/current/end", response_model=RoomState)
def end_round(room_id: int, request: Request, user: User = Depends(write_guard), db: Session = Depends(get_db)):
    s, now = request.app.state.settings, _now(request)
    room = _owned(db, user, room_id)
    rnd = latest_round(db, room.id)
    if rnd is None or round_phase(rnd, now, s) != "drawing":
        raise ApiError(409, "no_round_running", "No round is being drawn right now.")
    rnd.ended_at = now
    db.commit()
    hub = _hub(request)
    hub.schedule_round(room.id, rnd)
    hub.notify(room.id)
    return build_state(db, room, Viewer("teacher"), now, s, hub.online_members(room.id))


# ------------------------------------------------------------------ students

@router.post("/join", response_model=JoinOut, status_code=201)
def join(body: JoinIn, request: Request, db: Session = Depends(get_db)):
    s = request.app.state.settings
    request.app.state.join_limiter.check(request.client.host if request.client else "unknown")
    room = db.scalar(select(Room).where(Room.code == body.code))
    if room is None:
        raise ApiError(404, "room_not_found", "No room has that code. Check it with your teacher.")
    if room.closed_at:
        raise ApiError(409, "room_closed", "This room is closed.")
    count = db.scalar(select(func.count(RoomMember.id)).where(RoomMember.room_id == room.id)) or 0
    if count >= s.max_room_members:
        raise ApiError(409, "room_full", f"This room already has {s.max_room_members} students.")
    token = "prs_rm_" + secrets.token_urlsafe(24)
    db.add(RoomMember(room_id=room.id, nickname=body.nickname, nickname_key=body.nickname.lower(), token_hash=hash_key(token)))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "nickname_taken", "Someone in this room already uses that nickname. Pick another.")
    _hub(request).notify(room.id)
    return JoinOut(room_id=room.id, room_name=room.name, nickname=body.nickname, token=token)


@router.post("/{room_id}/submit", response_model=SubmitOut)
def submit(room_id: int, body: SubmitIn, request: Request, x_room_token: str | None = Header(default=None),
           db: Session = Depends(get_db)):
    s, now = request.app.state.settings, _now(request)
    member = _member(db, room_id, x_room_token)
    request.app.state.write_limiter.check(f"member:{member.id}")
    room = db.get(Room, room_id)
    rnd = latest_round(db, room_id)
    phase = round_phase(rnd, now, s)
    if room.closed_at or phase not in ("drawing", "collecting"):
        raise ApiError(409, "no_round_running", "There is no round to submit to right now.")
    if db.scalar(select(RoundSubmission.id).where(RoundSubmission.round_id == rnd.id, RoundSubmission.member_id == member.id)):
        raise ApiError(409, "already_submitted", "You already handed in a drawing for this round.")
    enforce_limits(body.strokes, s)
    strokes = normalise(body.strokes)
    timeline = get_scorer(request, rnd.model_version).timeline(strokes, rnd.target)
    score, hit = score_timeline(timeline, rnd.target)
    ink = ink_length(strokes)
    sub = RoundSubmission(round_id=rnd.id, member_id=member.id, score=score, recognised_at=hit.fraction if hit else None,
                          final_guess=timeline[-1].top1, final_confidence=timeline[-1].top1_p,
                          suspect=looks_automated(ink, body.duration_ms, s.min_attempt_ms, s.max_ink_per_ms),
                          strokes=strokes, n_strokes=len(strokes), ink=ink, duration_ms=body.duration_ms)
    db.add(sub)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "already_submitted", "You already handed in a drawing for this round.")
    _hub(request).notify(room_id)
    return SubmitOut(round_no=rnd.no)


# ------------------------------------------------------------------ both: state and drawings

@router.get("/{room_id}/state", response_model=RoomState)
def state(room_id: int, request: Request, x_room_token: str | None = Header(default=None),
          user: User | None = Depends(get_current_user_optional), db: Session = Depends(get_db)):
    room, viewer = _viewer(request, db, room_id, user, x_room_token)
    return build_state(db, room, viewer, _now(request), request.app.state.settings, _hub(request).online_members(room_id))


@router.get("/{room_id}/rounds/{no}/drawings", response_model=list[RoundDrawing])
def round_drawings(room_id: int, no: int, request: Request, x_room_token: str | None = Header(default=None),
                   user: User | None = Depends(get_current_user_optional), db: Session = Depends(get_db)):
    """The class's drawings for a finished round (hidden while the round runs, so nobody copies a neighbour)."""
    room, _ = _viewer(request, db, room_id, user, x_room_token)
    rnd = db.scalar(select(RoomRound).where(RoomRound.room_id == room.id, RoomRound.no == no))
    if rnd is None:
        raise ApiError(404, "not_found", "Round not found.")
    if round_phase(rnd, _now(request), request.app.state.settings) != "results":
        raise ApiError(409, "round_not_finished", "Drawings are shown when the round ends.")
    rows = db.execute(select(RoundSubmission.id, RoomMember.nickname, RoundSubmission.strokes)
                      .join(RoomMember, RoomMember.id == RoundSubmission.member_id).where(RoundSubmission.round_id == rnd.id)
                      .order_by(RoundSubmission.id)).all()
    return [RoundDrawing(submission_id=r.id, nickname=r.nickname, strokes=r.strokes) for r in rows]


# ------------------------------------------------------------------ live socket

def _origin_ok(ws: WebSocket) -> bool:
    """Browsers always send Origin on a WebSocket handshake. Accept only this site (or a configured one), so another page cannot
    open a socket with a teacher's cookie."""
    origin = ws.headers.get("origin")
    if not origin:
        return True                                                       # not a browser (tests, scripts): no ambient cookie to abuse
    host = urlparse(origin).netloc
    return host == ws.headers.get("host") or origin in ws.app.state.settings.cors_origins


@router.websocket("/{room_id}/live")
async def live(ws: WebSocket, room_id: int):
    """Teachers are recognised by their session cookie. Students send {"token": "..."} as the first message (never in the URL)."""
    app = ws.app
    if not _origin_ok(ws):
        await ws.close(code=4403)
        return
    await ws.accept()
    conn: Conn | None = None
    try:
        def authenticate(token: str | None) -> tuple[str, int | None] | None:
            with app.state.session_factory() as db:
                room = db.get(Room, room_id)
                if room is None:
                    return None
                if token:
                    member = db.scalar(select(RoomMember).where(RoomMember.token_hash == hash_key(token)))
                    return ("student", member.id) if member and member.room_id == room_id else None
                user = _user_from_cookie(ws, db, app.state.settings)
                return ("teacher", None) if user and user.id == room.owner_id else None

        who = await asyncio.get_running_loop().run_in_executor(None, authenticate, None)
        if who is None:                                                   # not the teacher: expect a student token
            try:
                first = json.loads(await asyncio.wait_for(ws.receive_text(), WS_AUTH_SECONDS))
                token = first.get("token") if isinstance(first, dict) else None
            except (asyncio.TimeoutError, ValueError):
                token = None
            who = await asyncio.get_running_loop().run_in_executor(None, authenticate, token if isinstance(token, str) else None)
            if who is None:
                await ws.close(code=4401)
                return
        conn = Conn(ws, asyncio.get_running_loop(), who[0], who[1])
        app.state.hub.add(room_id, conn)
        await asyncio.get_running_loop().run_in_executor(None, app.state.hub.notify, room_id)       # everyone sees who came online
        while True:
            await ws.receive_text()                                       # clients only keep the socket alive; all changes arrive over REST
    except WebSocketDisconnect:
        pass
    finally:
        if conn is not None:
            app.state.hub.remove(room_id, conn)
            await asyncio.get_running_loop().run_in_executor(None, app.state.hub.notify, room_id)
