"""The public REST API: ask the model what a drawing is. Authenticated with a secret API key, metered and rate limited."""
import time

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import authenticate_key, seconds_until_midnight_utc
from app.errors import ApiError
from app.inference import get_scorer
from app.models import ApiKey
from app.schemas import Guess, Limits, ModelInfo, PredictIn, PredictOut
from app.services.drawings import enforce_limits, ink_length, normalise
from app.services.metering import record, used_on

router = APIRouter(tags=["public api"])


@router.get("/model", response_model=ModelInfo)
def model_info(request: Request):
    """Which model answers predictions, the objects it knows, and the API limits. No key needed."""
    scorer, s = get_scorer(request), request.app.state.settings
    return ModelInfo(version=scorer.version, classes=scorer.classes, limits=Limits(
        requests_per_minute=s.api_per_minute, requests_per_day=s.api_daily_limit, max_strokes=s.max_strokes,
        max_points=s.max_points, max_active_keys=s.max_keys_per_user, top_k_max=10))


@router.post("/predict", response_model=PredictOut)
def predict(body: PredictIn, request: Request, response: Response, key: ApiKey = Depends(authenticate_key), db: Session = Depends(get_db)):
    """Ranked guesses for a drawing as it stands. Strokes use the 0..255 frame; send a partial drawing to get a partial-drawing guess."""
    now = request.app.state.clock()
    started = time.perf_counter()
    try:
        enforce_limits(body.strokes, request.app.state.settings)
        strokes = normalise(body.strokes)
        guesses = get_scorer(request).predict(strokes, body.top_k)
    except ApiError:
        key.last_used_at = now
        record(db, key.id, now.date(), ok=False, ms=(time.perf_counter() - started) * 1000)      # failed calls are metered too
        raise
    ms = (time.perf_counter() - started) * 1000
    key.last_used_at = now
    record(db, key.id, now.date(), ok=True, ms=ms)
    response.headers["RateLimit-Limit"] = str(key.daily_limit)
    response.headers["RateLimit-Remaining"] = str(max(0, key.daily_limit - used_on(db, key.id, now.date())))
    response.headers["RateLimit-Reset"] = str(seconds_until_midnight_utc(now))
    return PredictOut(model=get_scorer(request).version, ink=ink_length(strokes),
                      predictions=[Guess(label=label, probability=round(p, 5)) for label, p in guesses], inference_ms=round(ms, 2))
