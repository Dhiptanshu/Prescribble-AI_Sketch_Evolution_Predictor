import time

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.models import Room, RoomMember, RoundSubmission, User
from app.services.scoring import score_timeline
from tests.conftest import PASSWORD, build_app, make_settings, strokes_of

API = "/api/v1/rooms"


def teacher(app, name="Ms Rivera"):
    c = TestClient(app)
    r = c.post("/api/v1/auth/register", json={"email": f"{name.lower().replace(' ', '.')}@example.com", "password": PASSWORD, "display_name": name})
    assert r.status_code == 201, r.text
    return c


def make_room(c, name="Period 3 art"):
    r = c.post(API, json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()


def join(c, code, nickname):
    r = c.post(f"{API}/join", json={"code": code, "nickname": nickname})
    assert r.status_code == 201, r.text
    return r.json()


def student(app, code, nickname):
    c = TestClient(app)
    j = join(c, code, nickname)
    return c, {"X-Room-Token": j["token"]}, j


def draw(c, room_id, headers, strokes, ms=3000):
    return c.post(f"{API}/{room_id}/submit", json={"strokes": strokes, "duration_ms": ms}, headers=headers)


@pytest.fixture
def tc(client):
    """A teacher's browser on the shared app (cookie session)."""
    return teacher(client.app)


def start(c, room_id, target="cat", seconds=30):
    r = c.post(f"{API}/{room_id}/rounds", json={"target": target, "duration_s": seconds})
    assert r.status_code == 201, r.text
    return r.json()


# ---------------------------------------------------------------- rooms and joining

def test_a_teacher_creates_a_room_with_a_readable_code(tc):
    room = make_room(tc)
    assert len(room["code"]) == 6 and not set(room["code"]) & set("01OIL") and room["members"] == 0 and room["rounds"] == 0
    assert tc.get(API).json()[0]["code"] == room["code"]


def test_creating_a_room_needs_an_account(client):
    assert client.post(API, json={"name": "x"}).status_code == 401


def test_students_join_with_a_code_and_a_nickname_and_no_account(client, tc):
    room = make_room(tc)
    s = TestClient(client.app)
    j = join(s, room["code"].lower(), "  Sam  ")             # the code is forgiving about case; names are tidied
    assert j["nickname"] == "Sam" and j["token"].startswith("prs_rm_") and j["room_id"] == room["id"]
    assert s.get("/api/v1/auth/session").json()["user"] is None          # still a visitor
    assert tc.get(API).json()[0]["members"] == 1


def test_nicknames_are_unique_per_room_ignoring_case(client, tc):
    code = make_room(tc)["code"]
    join(TestClient(client.app), code, "Sam")
    r = TestClient(client.app).post(f"{API}/join", json={"code": code, "nickname": "sAM"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "nickname_taken"
    other = make_room(tc, "Other room")["code"]
    join(TestClient(client.app), other, "Sam")                          # the same name is fine in another room


def test_unknown_code_closed_room_and_full_room_are_refused(client, tc):
    assert client.post(f"{API}/join", json={"code": "ZZZZZZ", "nickname": "a"}).json()["error"]["code"] == "room_not_found"
    room = make_room(tc)
    assert tc.post(f"{API}/{room['id']}/close").status_code == 200
    assert client.post(f"{API}/join", json={"code": room["code"], "nickname": "a"}).json()["error"]["code"] == "room_closed"


def test_room_capacity(clock, scorer):
    app = build_app(clock, scorer, max_room_members=2)
    t = teacher(app)
    code = make_room(t)["code"]
    join(TestClient(app), code, "a"); join(TestClient(app), code, "b")
    assert TestClient(app).post(f"{API}/join", json={"code": code, "nickname": "c"}).json()["error"]["code"] == "room_full"


def test_join_attempts_are_rate_limited(clock, scorer):
    app = build_app(clock, scorer, joins_per_minute=3)
    codes = [TestClient(app).post(f"{API}/join", json={"code": "AAAAAA", "nickname": "x"}).status_code for _ in range(5)]
    assert codes == [404, 404, 404, 429, 429]               # guessing codes is throttled per client


def test_open_room_limit(clock, scorer):
    app = build_app(clock, scorer, max_open_rooms=2)
    t = teacher(app)
    make_room(t); make_room(t)
    assert t.post(API, json={"name": "third"}).json()["error"]["code"] == "too_many_rooms"


# ---------------------------------------------------------------- ownership

def test_another_teacher_cannot_see_or_run_my_room(client, tc):
    room = make_room(tc)
    rival = teacher(client.app, "Mr Rival")
    assert rival.get(f"{API}/{room['id']}/state").status_code == 404
    assert rival.post(f"{API}/{room['id']}/rounds", json={"target": "cat", "duration_s": 30}).status_code == 404
    assert rival.post(f"{API}/{room['id']}/close").status_code == 404
    assert rival.delete(f"{API}/{room['id']}").status_code == 404
    assert rival.get(API).json() == []


def test_a_student_token_works_only_in_its_own_room(client, tc):
    a, b = make_room(tc, "A"), make_room(tc, "B")
    _, headers, _ = student(client.app, a["code"], "Sam")
    s = TestClient(client.app)
    assert s.get(f"{API}/{a['id']}/state", headers=headers).status_code == 200
    assert s.get(f"{API}/{b['id']}/state", headers=headers).status_code == 401
    assert s.get(f"{API}/{a['id']}/state").status_code == 401


def test_students_cannot_start_rounds(client, tc):
    room = make_room(tc)
    s, headers, _ = student(client.app, room["code"], "Sam")
    assert s.post(f"{API}/{room['id']}/rounds", json={"duration_s": 30}, headers=headers).status_code == 401


# ---------------------------------------------------------------- rounds

def test_a_round_has_a_word_a_timer_and_one_at_a_time(client, tc, scorer):
    room = make_room(tc)
    st = start(tc, room["id"], "cat", 40)
    assert st["phase"] == "drawing" and st["round"]["target"] == "cat" and st["round"]["no"] == 1 and st["round"]["seconds_left"] == 40
    r = tc.post(f"{API}/{room['id']}/rounds", json={"duration_s": 30})
    assert r.status_code == 409 and r.json()["error"]["code"] == "round_in_progress"


def test_word_and_duration_are_validated(client, tc, scorer):
    room = make_room(tc)
    assert tc.post(f"{API}/{room['id']}/rounds", json={"target": "unicorn", "duration_s": 30}).json()["error"]["code"] == "unknown_class"
    assert tc.post(f"{API}/{room['id']}/rounds", json={"target": "cat", "duration_s": 5}).json()["error"]["code"] == "bad_duration"
    assert tc.post(f"{API}/{room['id']}/rounds", json={"target": "cat", "duration_s": 999}).json()["error"]["code"] == "bad_duration"
    r = tc.post(f"{API}/{room['id']}/rounds", json={"duration_s": 30})                 # no word given: the server picks one the model knows
    assert r.status_code == 201 and r.json()["round"]["target"] in scorer.classes


def test_random_words_do_not_repeat_within_a_room(client, tc, clock, scorer):
    room = make_room(tc)
    seen = []
    for _ in range(4):
        seen.append(tc.post(f"{API}/{room['id']}/rounds", json={"duration_s": 20}).json()["round"]["target"])
        clock.advance(seconds=30)
    assert len(set(seen)) == 4


def test_timer_collecting_and_results_follow_the_clock(client, tc, clock):
    room = make_room(tc)
    start(tc, room["id"], "cat", 30)
    state = lambda: tc.get(f"{API}/{room['id']}/state").json()           # noqa: E731
    clock.advance(seconds=10)
    assert state()["phase"] == "drawing" and state()["round"]["seconds_left"] == 20
    clock.advance(seconds=20)                                             # timer reached zero: last drawings may still arrive
    assert state()["phase"] == "collecting" and state()["round"]["seconds_left"] == 0
    clock.advance(seconds=3)
    assert state()["phase"] == "results"


def test_teacher_can_end_a_round_early_and_start_the_next(client, tc, clock):
    room = make_room(tc)
    start(tc, room["id"], "cat", 120)
    assert tc.post(f"{API}/{room['id']}/rounds/current/end").json()["phase"] == "collecting"
    clock.advance(seconds=3)
    assert tc.get(f"{API}/{room['id']}/state").json()["phase"] == "results"
    assert tc.post(f"{API}/{room['id']}/rounds/current/end").json()["error"]["code"] == "no_round_running"
    second = start(tc, room["id"], "dog", 30)
    assert second["round"]["no"] == 2


def test_round_limit(clock, scorer):
    app = build_app(clock, scorer, max_rounds_per_room=1)
    t = teacher(app)
    room = make_room(t)
    start(t, room["id"], "cat", 20)
    clock.advance(seconds=30)
    assert t.post(f"{API}/{room['id']}/rounds", json={"target": "dog", "duration_s": 20}).json()["error"]["code"] == "too_many_rounds"


# ---------------------------------------------------------------- submitting and results

def test_the_server_scores_a_submission_and_hides_it_until_the_round_ends(client, tc, clock, scorer):
    room = make_room(tc)
    sam, h, _ = student(client.app, room["code"], "Sam")
    sketch = strokes_of("cat")[0]
    start(tc, room["id"], "cat", 30)
    assert draw(sam, room["id"], h, sketch).json() == {"submitted": True, "round_no": 1}

    mid = sam.get(f"{API}/{room['id']}/state", headers=h).json()
    assert mid["phase"] == "drawing" and mid["results"] is None and mid["me"]["submitted"] is True      # no score before the end
    assert sam.get(f"{API}/{room['id']}/rounds/1/drawings", headers=h).json()["error"]["code"] == "round_not_finished"

    clock.advance(seconds=40)
    end = sam.get(f"{API}/{room['id']}/state", headers=h).json()
    expected, hit = score_timeline(scorer.timeline(sketch, "cat"), "cat")                # the same maths, independently
    entry = end["results"]["entries"][0]
    assert end["phase"] == "results" and entry["score"] == expected and entry["rank"] == 1 and entry["is_me"] is True
    assert entry["recognised_at"] == (hit.fraction if hit else None)
    assert end["results"]["ai"]["drawings"] == 1 and end["results"]["ai"]["named"] == (1 if hit else 0)
    drawings = sam.get(f"{API}/{room['id']}/rounds/1/drawings", headers=h).json()
    assert drawings[0]["nickname"] == "Sam" and drawings[0]["strokes"]


def test_one_drawing_per_student_per_round(client, tc):
    room = make_room(tc)
    sam, h, _ = student(client.app, room["code"], "Sam")
    start(tc, room["id"], "cat", 30)
    assert draw(sam, room["id"], h, strokes_of("cat")[0]).status_code == 200
    r = draw(sam, room["id"], h, strokes_of("cat")[1])
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_submitted"


def test_no_submission_without_a_running_round_or_after_the_grace_period(client, tc, clock):
    room = make_room(tc)
    sam, h, _ = student(client.app, room["code"], "Sam")
    assert draw(sam, room["id"], h, strokes_of("cat")[0]).json()["error"]["code"] == "no_round_running"       # lobby
    start(tc, room["id"], "cat", 30)
    clock.advance(seconds=31)                                                                                # inside the grace period
    assert draw(sam, room["id"], h, strokes_of("cat")[0]).status_code == 200
    late, h2, _ = student(client.app, room["code"], "Late")
    clock.advance(seconds=5)
    assert draw(late, room["id"], h2, strokes_of("cat")[0]).json()["error"]["code"] == "no_round_running"


def test_submission_limits_and_the_instant_scripted_drawing(client, tc, clock):
    room = make_room(tc)
    sam, h, _ = student(client.app, room["code"], "Sam")
    bot, hb, _ = student(client.app, room["code"], "Bot")
    start(tc, room["id"], "cat", 30)
    assert draw(sam, room["id"], h, [[[1, 1]] * 3000]).status_code == 422                       # too many points
    assert draw(sam, room["id"], h, [[[300, 1], [2, 2]]]).status_code == 422                    # outside the frame
    assert draw(sam, room["id"], h, strokes_of("cat")[0]).status_code == 200
    assert draw(bot, room["id"], hb, strokes_of("cat")[1], ms=5).status_code == 200            # 5 ms is not a human drawing
    clock.advance(seconds=40)
    entries = tc.get(f"{API}/{room['id']}/state").json()["results"]["entries"]
    by_name = {e["nickname"]: e for e in entries}
    assert by_name["Bot"]["counted"] is False and by_name["Bot"]["rank"] is None and by_name["Sam"]["rank"] == 1
    assert entries[-1]["nickname"] == "Bot"                                                    # flagged drawings sit below the ranking


def test_ranking_ties_go_to_the_earlier_submission_and_totals_add_up(client, tc, clock):
    room = make_room(tc)
    a, ha, _ = student(client.app, room["code"], "Ana")
    b, hb, _ = student(client.app, room["code"], "Ben")
    start(tc, room["id"], "cat", 30)
    draw(a, room["id"], ha, strokes_of("cat")[0]); draw(b, room["id"], hb, strokes_of("cat")[0])      # identical drawings, Ana first
    clock.advance(seconds=40)
    st = tc.get(f"{API}/{room['id']}/state").json()
    assert [e["nickname"] for e in st["results"]["entries"]] == ["Ana", "Ben"] and st["results"]["entries"][0]["score"] == st["results"]["entries"][1]["score"]
    score = st["results"]["entries"][0]["score"]
    start(tc, room["id"], "dog", 30)
    draw(b, room["id"], hb, strokes_of("dog")[0])
    clock.advance(seconds=40)
    totals = tc.get(f"{API}/{room['id']}/state").json()["totals"]
    by = {t["nickname"]: t for t in totals}
    assert st["totals"][0]["points"] == score and by["Ben"]["rounds_played"] == 2 and by["Ana"]["rounds_played"] == 1
    assert sum(t["points"] for t in totals) == score * 2 + by["Ben"]["points"] - score
    assert [t["rank"] for t in totals] == [1, 2]


def test_a_flagged_drawing_earns_no_points(client, tc, clock):
    room = make_room(tc)
    bot, hb, _ = student(client.app, room["code"], "Bot")
    start(tc, room["id"], "cat", 30)
    draw(bot, room["id"], hb, strokes_of("cat")[0], ms=5)
    clock.advance(seconds=40)
    assert tc.get(f"{API}/{room['id']}/state").json()["totals"] == []


def test_teacher_sees_progress_before_the_end(client, tc):
    room = make_room(tc)
    a, ha, _ = student(client.app, room["code"], "Ana")
    student(client.app, room["code"], "Ben")
    start(tc, room["id"], "cat", 30)
    draw(a, room["id"], ha, strokes_of("cat")[0])
    members = tc.get(f"{API}/{room['id']}/state").json()["members"]
    assert {m["nickname"]: m["submitted"] for m in members} == {"Ana": True, "Ben": False}


# ---------------------------------------------------------------- closing and deleting

def test_closing_ends_a_running_round_and_blocks_joining(client, tc):
    room = make_room(tc)
    sam, h, _ = student(client.app, room["code"], "Sam")
    start(tc, room["id"], "cat", 60)
    assert tc.post(f"{API}/{room['id']}/close").json()["closed"] is True
    st = sam.get(f"{API}/{room['id']}/state", headers=h).json()
    assert st["phase"] == "closed" and st["room"]["closed"] is True
    assert draw(sam, room["id"], h, strokes_of("cat")[0]).json()["error"]["code"] == "no_round_running"
    assert tc.post(f"{API}/{room['id']}/rounds", json={"duration_s": 30}).json()["error"]["code"] == "room_closed"


def test_deleting_a_room_removes_students_and_drawings(client, tc, app):
    room = make_room(tc)
    sam, h, _ = student(client.app, room["code"], "Sam")
    start(tc, room["id"], "cat", 30)
    draw(sam, room["id"], h, strokes_of("cat")[0])
    assert tc.delete(f"{API}/{room['id']}").status_code == 204
    with app.state.session_factory() as db:
        assert db.query(Room).count() == db.query(RoomMember).count() == db.query(RoundSubmission).count() == 0
    assert sam.get(f"{API}/{room['id']}/state", headers=h).status_code == 404


def test_deleting_the_teacher_account_removes_the_room(client, tc, app):
    make_room(tc)
    assert tc.request("DELETE", "/api/v1/me", json={"password": PASSWORD}).status_code in (200, 204)
    with app.state.session_factory() as db:
        assert db.query(Room).count() == 0 and db.query(User).count() == 0


# ---------------------------------------------------------------- live socket

def next_state(ws, phase=None, tries=8, until=lambda m: True):
    """Read pushed messages until one satisfies the condition (several pushes can queue up)."""
    for _ in range(tries):
        msg = ws.receive_json()
        if (phase is None or msg["phase"] == phase) and until(msg):
            return msg
    raise AssertionError(f"never saw phase {phase}")


def test_websocket_pushes_every_change_to_teacher_and_students(client, tc):
    room = make_room(tc)
    with tc.websocket_connect(f"{API}/{room['id']}/live") as t_ws:
        first = t_ws.receive_json()
        assert first["role"] == "teacher" and first["phase"] == "lobby" and first["members"] == []

        sam, h, j = student(client.app, room["code"], "Sam")
        assert [m["nickname"] for m in next_state(t_ws)["members"]] == ["Sam"]               # the join arrives live

        with sam.websocket_connect(f"{API}/{room['id']}/live") as s_ws:
            s_ws.send_json({"token": j["token"]})
            mine = s_ws.receive_json()
            assert mine["role"] == "student" and mine["me"]["nickname"] == "Sam"
            seen = [t_ws.receive_json() for _ in range(1)]
            assert seen[0]["members"][0]["online"] is True                                    # presence is real

            start(tc, room["id"], "cat", 30)
            assert next_state(s_ws, "drawing")["round"]["target"] == "cat"
            assert draw(sam, room["id"], h, strokes_of("cat")[0]).status_code == 200
            assert next_state(t_ws, "drawing", until=lambda m: m["members"][0]["submitted"])["members"][0]["submitted"] is True


def test_websocket_refuses_strangers_and_wrong_tokens(client, tc):
    room = make_room(tc)
    stranger = TestClient(client.app)
    with pytest.raises(Exception):
        with stranger.websocket_connect(f"{API}/{room['id']}/live") as ws:
            ws.send_json({"token": "prs_rm_nope"})
            ws.receive_json()
    rival = teacher(client.app, "Mr Rival")
    with pytest.raises(Exception):
        with rival.websocket_connect(f"{API}/{room['id']}/live") as ws:
            ws.send_json({"token": "x"})
            ws.receive_json()


def test_websocket_rejects_a_foreign_origin(client, tc):
    room = make_room(tc)
    with pytest.raises(Exception):
        with tc.websocket_connect(f"{API}/{room['id']}/live", headers={"origin": "https://evil.example"}) as ws:
            ws.receive_json()


def test_the_round_timer_pushes_phase_changes_on_its_own(scorer):
    """Real clock, short round: nobody calls the API, yet connected clients are told when drawing stops and results open."""
    app = create_app(make_settings(round_min_s=1, round_grace_s=1))
    app.state.scorer = scorer
    t = teacher(app)
    room = make_room(t)
    with t.websocket_connect(f"{API}/{room['id']}/live") as ws:
        ws.receive_json()
        assert t.post(f"{API}/{room['id']}/rounds", json={"target": "cat", "duration_s": 1}).status_code == 201
        started = time.monotonic()
        assert next_state(ws, "drawing")["round"]["target"] == "cat"
        assert next_state(ws, "collecting")["phase"] == "collecting"
        assert next_state(ws, "results")["results"]["entries"] == []
        assert 1.5 < time.monotonic() - started < 6
