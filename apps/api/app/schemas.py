"""Request / response schemas (the public contract of the API)."""
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


def _clean_name(v: str) -> str:
    v = " ".join(v.split())
    if not v:
        raise ValueError("display name cannot be empty")
    return v


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(min_length=1, max_length=40)

    _name = field_validator("display_name")(_clean_name)

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.strip().lower()


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.strip().lower()


class ProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=40)
    consent_training: bool | None = None
    show_on_leaderboard: bool | None = None

    @field_validator("display_name")
    @classmethod
    def _name(cls, v: str | None) -> str | None:
        return None if v is None else _clean_name(v)


class DeleteAccountIn(BaseModel):
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    display_name: str
    is_admin: bool
    consent_training: bool
    show_on_leaderboard: bool
    created_at: datetime


class SessionOut(BaseModel):
    """Who is signed in right now. Always HTTP 200: `user` is null for visitors (no 401 noise in the browser console)."""

    user: UserOut | None


# ---------- drawings ----------
Coord = Annotated[float, Field(ge=0, le=255)]
Point = tuple[Coord, Coord]


class DrawingCreate(BaseModel):
    strokes: list[Annotated[list[Point], Field(min_length=1)]] = Field(min_length=1)
    label: str | None = Field(default=None, max_length=40)
    ai_guess: str = Field(min_length=1, max_length=40)
    ai_confidence: float = Field(ge=0, le=1)
    recognised_at: float | None = Field(default=None, ge=0, le=1)
    mode: Literal["free", "challenge"] = "free"
    duration_ms: int | None = Field(default=None, ge=0, le=3_600_000)
    model_version: str = Field(pattern=r"^v\d{1,3}$")


class DrawingPatch(BaseModel):
    label: str | None = Field(max_length=40)      # required key; null clears the label


class DrawingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    label: str | None
    ai_guess: str
    ai_confidence: float
    recognised_at: float | None
    mode: str
    model_version: str
    strokes: list[list[tuple[float, float]]]
    n_strokes: int
    ink: float
    duration_ms: int | None
    share_token: str | None


class DrawingPage(BaseModel):
    items: list[DrawingOut]
    next_before: int | None


class ShareOut(BaseModel):
    token: str


class PublicDrawingOut(BaseModel):
    """What anyone with the link may see. No email, no user id."""

    strokes: list[list[tuple[float, float]]]
    label: str | None
    ai_guess: str
    ai_confidence: float
    recognised_at: float | None
    created_at: datetime
    model_version: str
    author: str


# ---------- stats ----------
class ClassStat(BaseModel):
    label: str
    count: int
    avg_recognised_at: float | None


class Streak(BaseModel):
    current: int
    longest: int


class DayCount(BaseModel):
    date: date
    count: int


class StatsOut(BaseModel):
    total: int
    labelled: int
    ai_final_correct: int
    ai_ever_recognised: int
    avg_recognised_at: float | None
    early_rate: float | None
    by_class: list[ClassStat]
    streak: Streak
    activity: list[DayCount]
    first_drawing_at: datetime | None
    last_drawing_at: datetime | None


# ---------- daily challenge ----------
class AttemptIn(BaseModel):
    strokes: list[Annotated[list[Point], Field(min_length=1)]] = Field(min_length=1)
    duration_ms: int | None = Field(default=None, ge=0, le=3_600_000)


class AttemptSummary(BaseModel):
    attempt_no: int
    score: int
    recognised_at: float | None
    counted: bool                      # false when the attempt looked automated and is kept off the leaderboard
    created_at: datetime


class MyDay(BaseModel):
    attempts_used: int
    best_score: int | None
    attempts: list[AttemptSummary]


class TodayOut(BaseModel):
    day: date
    target: str
    model_version: str
    attempts_max: int
    seconds_left: int
    me: MyDay | None                   # null for visitors


class TimelineStep(BaseModel):
    fraction: float
    top1: str
    top1_p: float
    p_target: float


class AttemptOut(BaseModel):
    attempt_no: int
    attempts_left: int
    score: int
    recognised_at: float | None
    confidence_at_hit: float | None
    final_guess: str
    final_confidence: float
    counted: bool
    best_score: int | None
    rank: int | None
    participants: int
    timeline: list[TimelineStep]


class LeaderboardEntry(BaseModel):
    rank: int
    name: str
    score: int
    recognised_at: float | None
    is_me: bool


class LeaderboardOut(BaseModel):
    day: date
    target: str
    participants: int
    entries: list[LeaderboardEntry]
    me: LeaderboardEntry | None


class ChallengeDay(BaseModel):
    day: date
    target: str
    best_score: int


class ChallengeStats(BaseModel):
    played: int
    best_score: int | None
    average_best: float | None
    streak: Streak
    history: list[ChallengeDay]


# ---------- developer platform: API keys, public predict, admin ----------
class KeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)

    _name = field_validator("name")(_clean_name)


class KeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    prefix: str
    daily_limit: int
    used_today: int = 0
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


class KeyCreated(KeyOut):
    key: str                           # the only time the full key is ever returned


class UsageDay(BaseModel):
    day: date
    requests: int
    errors: int
    avg_ms: float | None


class PredictIn(BaseModel):
    strokes: list[Annotated[list[Point], Field(min_length=1)]] = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=10)


class Guess(BaseModel):
    label: str
    probability: float


class PredictOut(BaseModel):
    model: str
    ink: float
    predictions: list[Guess]
    inference_ms: float


class Limits(BaseModel):
    requests_per_minute: int
    requests_per_day: int
    max_strokes: int
    max_points: int
    max_active_keys: int
    top_k_max: int


class ModelInfo(BaseModel):
    version: str
    classes: list[str]
    limits: Limits                     # what the developer docs quote, read from the live settings so they cannot drift


class CountPair(BaseModel):
    total: int
    last_7_days: int


class ChallengeToday(BaseModel):
    players: int
    attempts: int
    flagged: int


class TopKey(BaseModel):
    prefix: str
    name: str
    owner: str
    requests_7d: int


class ApiMetrics(BaseModel):
    active_keys: int
    requests_today: int
    requests_7d: int
    errors_7d: int
    avg_ms_7d: float | None
    daily: list[UsageDay]
    top_keys: list[TopKey]


class AdminMetrics(BaseModel):
    users: CountPair
    drawings: CountPair
    challenge_today: ChallengeToday
    api: ApiMetrics
    model_version: str
    model_loaded: bool
