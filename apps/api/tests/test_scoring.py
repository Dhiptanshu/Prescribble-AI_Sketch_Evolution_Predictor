from datetime import date, timedelta

from app.services.daily import pick_target
from app.services.scoring import FRACTIONS, Step, first_hit, looks_automated, score_timeline


def timeline(target, top_by_step, p=0.9):
    """A 20-step timeline where `top_by_step[i]` is the AI's #1 guess at step i (missing steps repeat the last one)."""
    tops = list(top_by_step) + [top_by_step[-1]] * (len(FRACTIONS) - len(top_by_step))
    return [Step(f, t, p, p if t == target else 0.05) for f, t in zip(FRACTIONS, tops)]


def test_fractions_are_twenty_steps_of_five_percent():
    assert len(FRACTIONS) == 20 and FRACTIONS[0] == 0.05 and FRACTIONS[-1] == 1.0


def test_score_is_100_at_the_first_step_and_falls_by_5_per_step():
    assert score_timeline(timeline("cat", ["cat"]), "cat")[0] == 100
    assert score_timeline(timeline("cat", ["dog", "dog", "dog", "cat"]), "cat")[0] == 85        # 4th step = 20% of the ink: 100, 95, 90, 85
    late = timeline("cat", ["dog"] * 19 + ["cat"])
    assert score_timeline(late, "cat")[0] == 5                                                   # only once the drawing was finished


def test_never_recognised_scores_zero():
    score, hit = score_timeline(timeline("cat", ["dog"]), "cat")
    assert score == 0 and hit is None


def test_a_hit_needs_to_be_the_top_guess_with_at_least_half_confidence():
    shaky = [Step(f, "cat", 0.49, 0.49) for f in FRACTIONS]                                      # top guess but under 50%
    assert first_hit(shaky, "cat") is None
    runner_up = [Step(f, "dog", 0.6, 0.35) for f in FRACTIONS]                                   # target is not the top guess
    assert first_hit(runner_up, "cat") is None
    exact = [Step(FRACTIONS[0], "cat", 0.5, 0.5)] + [Step(f, "dog", 0.9, 0.0) for f in FRACTIONS[1:]]
    assert first_hit(exact, "cat").fraction == 0.05                                              # exactly 50% counts


def test_the_first_hit_counts_even_if_the_ai_later_changes_its_mind():
    steps = timeline("cat", ["dog", "cat", "dog", "dog"])
    score, hit = score_timeline(steps, "cat")
    assert hit.fraction == FRACTIONS[1] and score == 95


def test_automated_input_is_flagged():
    assert looks_automated(500, None, 400, 8.0)               # no drawing time reported
    assert looks_automated(500, 100, 400, 8.0)                # faster than a human can draw
    assert looks_automated(5000, 600, 400, 8.0)               # ~8.3 px/ms: a pasted path
    assert not looks_automated(600, 3000, 400, 8.0)           # an ordinary drawing: 0.2 px/ms
    assert not looks_automated(1200, 1200, 400, 8.0)          # a fast scribbler at 1 px/ms


CLASSES = ["cat", "dog", "house", "sun", "tree", "car", "star", "moon"]


def test_daily_word_is_deterministic_and_depends_on_the_secret():
    d = date(2026, 10, 3)
    assert pick_target(CLASSES, d, "s1", None) == pick_target(CLASSES, d, "s1", None)
    assert pick_target(CLASSES, d, "s1", None) == pick_target(list(reversed(CLASSES)), d, "s1", None)       # class order is irrelevant
    assert {pick_target(CLASSES, d, f"secret-{i}", None) for i in range(40)} == set(CLASSES)               # a different secret, a different word


def test_daily_word_never_repeats_yesterdays_and_eventually_covers_every_class():
    seen, previous = set(), None
    for i in range(400):
        word = pick_target(CLASSES, date(2026, 1, 1) + timedelta(days=i), "s", previous)
        assert word != previous
        seen.add(word)
        previous = word
    assert seen == set(CLASSES)
