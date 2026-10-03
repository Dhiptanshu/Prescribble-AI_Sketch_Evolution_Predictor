# Classrooms (Phase 5)

A teacher (account) opens a **room**; students join with a 6-character **code** and a **nickname**, no account. The teacher starts **rounds**
(one word, one timer). Students draw in their own browser, where the AI guesses live; their drawing is handed in and **scored by the server**
with the same scorer as the daily challenge (`app/services/scoring.py`, the ONNX model, the training pipeline code). Scores stay hidden until
the round ends, then everybody sees the ranking, the AI's record on the round and the class's drawings.

## Round lifecycle
| Phase | Until | What happens |
|---|---|---|
| `lobby` | teacher starts a round | students wait, roster shows who is online |
| `drawing` | `ends_at`, or the teacher presses End | boards unlocked, clock runs, teacher sees "n of m handed in" |
| `collecting` | + `round_grace_s` (3 s) | clients auto-submit what is on the board; late drawings still count |
| `results` | next round starts | ranking, AI summary, drawings, class standings |
| `closed` | | room closed: no joins, no submissions; results stay readable |

The phase is **derived from timestamps and the app clock** (`app/services/rooms.py`), never from a background job, so state is identical whether
or not a timer fired. Timers (`room_hub.py`) only decide *when to push*.

## API (all under `/api/v1/rooms`)
Teacher (session cookie): `POST /` create, `GET /` list, `POST /{id}/rounds` start, `POST /{id}/rounds/current/end`, `POST /{id}/close`, `DELETE /{id}`.
Student: `POST /join {code, nickname}` returns a room token once (hash stored); `POST /{id}/submit` with `X-Room-Token`.
Both: `GET /{id}/state`, `GET /{id}/rounds/{no}/drawings` (finished rounds only), `WS /{id}/live`.

**WebSocket:** teachers are recognised by their cookie; students send `{"token": "..."}` as the first message (never in the URL). Every change
pushes a fresh `RoomState` to every connected client. Browser `Origin` must match the site (or a configured CORS origin). Close codes: 4401 not
allowed, 4403 foreign origin, 4404 room deleted. The web client reconnects with back-off and also re-reads the state over HTTP every 5 s.

## Rules and limits (`PRESCRIBBLE_*`)
`MAX_OPEN_ROOMS` 10 per teacher, `MAX_ROOM_MEMBERS` 60, `MAX_ROUNDS_PER_ROOM` 30, `ROUND_MIN_S`/`ROUND_MAX_S` 10..300, `ROUND_GRACE_S` 3,
`JOINS_PER_MINUTE` 20 per IP (also slows code guessing). Nicknames are unique per room, case-insensitive. A drawing made implausibly fast is
stored but flagged, listed as "not counted" and earns no points (best-effort, like the daily challenge). Random words do not repeat within a room
until the model's classes run out.

## Privacy
Students give only a nickname. Their drawings are stored because they handed them in, visible to that room's teacher and classmates, and deleted
with the room (`DELETE /{id}`) or the teacher's account (cascade). Room tokens live in the student's browser `localStorage`.

## Known limits (honest)
- **Single process:** the hub keeps sockets in memory. Several API replicas need a shared pub/sub (Redis) behind `RoomHub.notify`.
- No student removal by the teacher and no nickname moderation yet (the same open item as display names).
- A student who clears browser storage loses their seat (the nickname stays taken until the room is deleted).
- Tested with two students in real Edge and with the API's test client; not load-tested with a full class of 60.

## Tests
API: `apps/api/tests/test_rooms.py` (31 tests: ownership, limits, timing with an injected clock, scoring against an independent computation,
hidden-until-end, socket pushes, foreign origin, real-clock timer). Web: `src/lib/rooms.test.ts`. Browser: `apps/web/e2e/full.phase5.spec.ts`
(teacher plus two students in separate browser profiles through a whole round).
