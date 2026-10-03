"""Request / response schemas for classrooms."""
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas import Point


def _one_line(v: str) -> str:
    v = " ".join(v.split())
    if not v:
        raise ValueError("cannot be empty")
    return v


class RoomCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    _name = field_validator("name")(_one_line)


class JoinIn(BaseModel):
    code: str = Field(min_length=1, max_length=16)
    nickname: str = Field(min_length=1, max_length=24)
    _nick = field_validator("nickname")(_one_line)

    @field_validator("code")
    @classmethod
    def _code(cls, v: str) -> str:
        return v.replace(" ", "").replace("-", "").upper()


class RoundStart(BaseModel):
    target: str | None = Field(default=None, max_length=40)      # a class the model knows; random when omitted
    duration_s: int = Field(default=60, ge=1, le=3600)           # checked against the server's allowed range


class SubmitIn(BaseModel):
    strokes: list[Annotated[list[Point], Field(min_length=1)]] = Field(min_length=1)
    duration_ms: int | None = Field(default=None, ge=0, le=3_600_000)


class RoomSummary(BaseModel):
    id: int
    name: str
    code: str
    closed: bool
    members: int
    rounds: int
    created_at: str


class JoinOut(BaseModel):
    room_id: int
    room_name: str
    nickname: str
    token: str                      # shown once; the browser keeps it to stay in the room


class RoomInfo(BaseModel):
    id: int
    name: str
    code: str
    closed: bool


class RoundInfo(BaseModel):
    no: int
    target: str
    duration_s: int
    seconds_left: float             # until the timer ends (0 once it has)


class MemberInfo(BaseModel):
    nickname: str
    online: bool
    submitted: bool                 # for the current round
    is_me: bool = False


class ResultEntry(BaseModel):
    rank: int | None                # None when the drawing was flagged and is not counted
    submission_id: int
    nickname: str
    score: int
    recognised_at: float | None
    final_guess: str
    counted: bool
    is_me: bool = False


class AiSummary(BaseModel):
    """How the AI did on this round, from the scored drawings only."""
    drawings: int
    named: int                                  # drawings where the AI got the word at some point
    median_recognised_at: float | None          # among those, the median fraction of the ink it needed


class RoundResults(BaseModel):
    round_no: int
    target: str
    entries: list[ResultEntry]
    ai: AiSummary


class TotalEntry(BaseModel):
    rank: int
    nickname: str
    points: int
    rounds_played: int
    is_me: bool = False


class RoomState(BaseModel):
    role: Literal["teacher", "student"]
    room: RoomInfo
    phase: Literal["lobby", "drawing", "collecting", "results", "closed"]
    round: RoundInfo | None
    me: MemberInfo | None
    members: list[MemberInfo]
    results: RoundResults | None
    totals: list[TotalEntry]
    rounds_finished: int


class RoundDrawing(BaseModel):
    submission_id: int
    nickname: str
    strokes: list


class SubmitOut(BaseModel):
    submitted: bool = True
    round_no: int
