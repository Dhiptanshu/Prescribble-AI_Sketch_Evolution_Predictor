"""In-process fan-out of room state to connected WebSockets, and the timers that announce phase changes.

Single process by design (like the rate limiter): with several replicas, swap `notify` for a Redis pub/sub publish. REST handlers run in
worker threads, so `notify` is synchronous and hands each send to the event loop the socket lives on.
"""
import asyncio
import logging
import threading
from dataclasses import dataclass
from typing import Any

from fastapi import WebSocket

from app.models import Room, RoomRound
from app.services.rooms import Viewer, build_state, deadlines

log = logging.getLogger("prescribble.rooms")


@dataclass(eq=False)
class Conn:
    ws: WebSocket
    loop: asyncio.AbstractEventLoop
    viewer_role: str
    member_id: int | None


class RoomHub:
    def __init__(self, app):
        self._app = app
        self._lock = threading.Lock()
        self._conns: dict[int, set[Conn]] = {}
        self._timers: dict[int, list[threading.Timer]] = {}

    # ------------------------------------------------------------ connections
    def add(self, room_id: int, conn: Conn) -> None:
        with self._lock:
            self._conns.setdefault(room_id, set()).add(conn)

    def remove(self, room_id: int, conn: Conn) -> None:
        with self._lock:
            self._conns.get(room_id, set()).discard(conn)

    def online_members(self, room_id: int) -> set[int]:
        with self._lock:
            return {c.member_id for c in self._conns.get(room_id, ()) if c.member_id is not None}

    def connection_count(self, room_id: int) -> int:
        with self._lock:
            return len(self._conns.get(room_id, ()))

    # ------------------------------------------------------------ pushing state
    def notify(self, room_id: int) -> None:
        """Send every connected client its own fresh view of the room."""
        with self._lock:
            conns = list(self._conns.get(room_id, ()))
        if not conns:
            return
        app = self._app
        online = self.online_members(room_id)
        with app.state.session_factory() as db:
            room = db.get(Room, room_id)
            if room is None:
                return
            members = {m.id: m for m in room.members}
            now = app.state.clock()
            for conn in conns:
                viewer = Viewer(conn.viewer_role, members.get(conn.member_id) if conn.member_id else None)
                if conn.viewer_role == "student" and viewer.member is None:
                    continue                                                   # a kicked or deleted member: nothing to show
                payload = build_state(db, room, viewer, now, app.state.settings, online).model_dump(mode="json")
                self._send(conn, payload)

    @staticmethod
    def _send(conn: Conn, payload: Any) -> None:
        try:
            asyncio.run_coroutine_threadsafe(conn.ws.send_json(payload), conn.loop)
        except RuntimeError:                                                   # the loop is gone (shutting down)
            log.debug("could not send to a closed connection")

    def close_room(self, room_id: int) -> None:
        """Drop every socket of a deleted room."""
        with self._lock:
            conns = list(self._conns.pop(room_id, ()))
        for conn in conns:
            try:
                asyncio.run_coroutine_threadsafe(conn.ws.close(code=4404), conn.loop)
            except RuntimeError:
                pass
        self.cancel_timers(room_id)

    # ------------------------------------------------------------ round timers
    def cancel_timers(self, room_id: int) -> None:
        with self._lock:
            for t in self._timers.pop(room_id, []):
                t.cancel()

    def schedule_round(self, room_id: int, rnd: RoomRound) -> None:
        """Push when the drawing timer ends and again when results open. State itself never depends on these firing."""
        self.cancel_timers(room_id)
        delays = deadlines(rnd, self._app.state.clock(), self._app.state.settings)
        timers = [threading.Timer(d, self.notify, args=(room_id,)) for d in delays]
        for t in timers:
            t.daemon = True
        with self._lock:
            self._timers[room_id] = timers
        for t in timers:
            t.start()

    def shutdown(self) -> None:
        with self._lock:
            ids = list(self._timers)
        for rid in ids:
            self.cancel_timers(rid)

