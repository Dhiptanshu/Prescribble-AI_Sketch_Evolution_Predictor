from datetime import date, datetime, timedelta, timezone

from app.services.stats import Facts, compute_stats, streaks
from tests.conftest import PASSWORD
from tests.test_drawings import URL, payload

TODAY = date(2026, 10, 3)


def at(days_ago, hour=12):
    return datetime(2026, 10, 3, hour, tzinfo=timezone.utc) - timedelta(days=days_ago)


def test_streaks():
    d = lambda *ago: {TODAY - timedelta(days=n) for n in ago}
    assert streaks(set(), TODAY) == (0, 0)
    assert streaks(d(0), TODAY) == (1, 1)
    assert streaks(d(0, 1, 2), TODAY) == (3, 3)
    assert streaks(d(1, 2), TODAY) == (2, 2)                  # nothing yet today: the streak is still alive until midnight
    assert streaks(d(2, 3), TODAY) == (0, 2)                  # missed yesterday: broken, longest remembered
    assert streaks(d(0, 1, 5, 6, 7, 8), TODAY) == (2, 4)


def test_compute_stats_from_known_facts():
    facts = [
        Facts(at(0), "house", "house", 0.2),
        Facts(at(0, 8), "house", "tree", 0.5),
        Facts(at(1), "cat", "dog", None),                      # the AI never got it
        Facts(at(1, 9), None, "sun", None),                    # unlabelled
    ]
    s = compute_stats(facts, TODAY)
    assert (s["total"], s["labelled"], s["ai_final_correct"], s["ai_ever_recognised"]) == (4, 3, 1, 2)
    assert s["avg_recognised_at"] == 0.35
    assert s["early_rate"] == round(1 / 3, 3)                  # one of three labelled drawings was recognised by 30% of the ink
    assert s["by_class"] == [{"label": "house", "count": 2, "avg_recognised_at": 0.35}, {"label": "cat", "count": 1, "avg_recognised_at": None}]
    assert s["streak"] == {"current": 2, "longest": 2}
    assert len(s["activity"]) == 30 and s["activity"][-1] == {"date": "2026-10-03", "count": 2} and s["activity"][-2]["count"] == 2
    assert sum(a["count"] for a in s["activity"]) == 4
    assert s["first_drawing_at"] == at(1, 9) and s["last_drawing_at"] == at(0)


def test_empty_stats_have_no_invented_numbers():
    s = compute_stats([], TODAY)
    assert s["total"] == 0 and s["avg_recognised_at"] is None and s["early_rate"] is None and s["by_class"] == []
    assert s["streak"] == {"current": 0, "longest": 0} and s["first_drawing_at"] is None
    assert len(s["activity"]) == 30 and all(a["count"] == 0 for a in s["activity"])


def test_stats_endpoint_counts_only_my_drawings(client, other_client, make_user):
    make_user("a@example.com")
    for kw in (dict(), dict(recognised_at=0.5), dict(label="cat", ai_guess="dog", recognised_at=None)):
        assert client.post(URL, json=payload(**kw)).status_code == 201
    other_client.post("/api/v1/auth/register", json={"email": "b@example.com", "password": PASSWORD, "display_name": "Bea"})
    other_client.post(URL, json=payload())

    s = client.get("/api/v1/me/stats").json()
    assert (s["total"], s["labelled"], s["ai_final_correct"], s["ai_ever_recognised"]) == (3, 3, 2, 2)
    assert s["avg_recognised_at"] == 0.375 and s["early_rate"] == round(1 / 3, 3)
    assert s["by_class"][0] == {"label": "house", "count": 2, "avg_recognised_at": 0.375}
    assert s["streak"] == {"current": 1, "longest": 1}
    assert len(s["activity"]) == 30 and s["activity"][-1]["count"] == 3
    assert other_client.get("/api/v1/me/stats").json()["total"] == 1
