"""Load test for the three expensive paths, against a server started with the rate limits raised (so it measures capacity, not the limiter):

  PRESCRIBBLE_ENV=dev PRESCRIBBLE_DATABASE_URL=sqlite:///load.db PRESCRIBBLE_API_PER_MINUTE=1000000 PRESCRIBBLE_API_DAILY_LIMIT=10000000 \\
  PRESCRIBBLE_AUTH_ATTEMPTS_PER_MINUTE=1000000 PRESCRIBBLE_WRITES_PER_MINUTE=1000000 PRESCRIBBLE_JOINS_PER_MINUTE=1000000 \\
  PRESCRIBBLE_ATTEMPTS_PER_DAY=1000000 python -m uvicorn app.main:create_app --factory --port 8300        (run from apps/api)
  python scripts/loadtest.py http://127.0.0.1:8300 [--out docs/results/loadtest.json]

A. predict      N workers call POST /api/v1/predict with an API key for a fixed time (real held-out sketches)
B. classroom    a room with S students who all join, open the live WebSocket, then submit a drawing in the same instant
C. challenge    U accounts submit a scored daily-challenge attempt in the same instant
Reports throughput and the latency percentiles each caller sees. Every number is measured by this script on the machine it runs on.
"""
import argparse
import asyncio
import json
import statistics
import time
from pathlib import Path

import httpx
import websockets

ROOT = Path(__file__).resolve().parent.parent
PASSWORD = "Load-Test-Passphrase-99"


def pct(values: list[float], p: float) -> float:
    return sorted(values)[min(len(values) - 1, int(len(values) * p))] if values else float("nan")


def summary(name: str, latencies: list[float], errors: int, seconds: float) -> dict:
    ms = [x * 1000 for x in latencies]
    out = {"scenario": name, "requests": len(ms) + errors, "errors": errors, "seconds": round(seconds, 2), "per_second": round(len(ms) / seconds, 1) if seconds else 0,
           "p50_ms": round(pct(ms, .5)), "p95_ms": round(pct(ms, .95)), "p99_ms": round(pct(ms, .99)), "max_ms": round(max(ms)) if ms else 0, "mean_ms": round(statistics.mean(ms)) if ms else 0}
    print(f"{name:34} {out['requests']:>6} req  {out['errors']:>3} errors  {out['per_second']:>7}/s  p50 {out['p50_ms']:>5} ms  p95 {out['p95_ms']:>5} ms  p99 {out['p99_ms']:>5} ms  max {out['max_ms']:>5} ms", flush=True)
    return out


async def register(c: httpx.AsyncClient, name: str) -> None:
    r = await c.post("/api/v1/auth/register", json={"email": f"{name}@load.example", "password": PASSWORD, "display_name": name[:30]})
    r.raise_for_status()


async def predict_scenario(base: str, sketches: list, workers: int, seconds: float) -> dict:
    async with httpx.AsyncClient(base_url=base, timeout=60) as admin:
        await register(admin, f"pred{time.time_ns()}")
        key = (await admin.post("/api/v1/keys", json={"name": "load"})).json()["key"]
    latencies, errors = [], 0
    stop = time.perf_counter() + seconds

    async def worker(i: int):
        nonlocal errors
        async with httpx.AsyncClient(base_url=base, timeout=60, headers={"Authorization": f"Bearer {key}"}) as c:
            n = i
            while time.perf_counter() < stop:
                t = time.perf_counter()
                r = await c.post("/api/v1/predict", json={"strokes": sketches[n % len(sketches)], "top_k": 5})
                (latencies.append(time.perf_counter() - t) if r.status_code == 200 else None)
                errors += r.status_code != 200
                n += workers

    t0 = time.perf_counter()
    await asyncio.gather(*[worker(i) for i in range(workers)])
    return summary(f"predict API, {workers} concurrent callers", latencies, errors, time.perf_counter() - t0)


async def classroom_scenario(base: str, sketches: list, students: int) -> list[dict]:
    async with httpx.AsyncClient(base_url=base, timeout=120) as teacher:
        await register(teacher, f"teacher{time.time_ns()}")
        room = (await teacher.post("/api/v1/rooms", json={"name": "load test"})).json()
        cookie = "; ".join(f"{k}={v}" for k, v in teacher.cookies.items())

        # One pooled client, like a browser that reuses connections. Opening a fresh TCP connection per request measures the load tester's
        # own Windows loopback connect rate (about 1 per second under a burst), not the server: the same 20 requests took 16 s that way and 0.09 s pooled.
        pool = httpx.AsyncClient(base_url=base, timeout=300, limits=httpx.Limits(max_connections=students + 10))

        async def join(i: int):
            r = await pool.post("/api/v1/rooms/join", json={"code": room["code"], "nickname": f"kid{i}"})
            r.raise_for_status()
            return r.json()["token"]

        t = time.perf_counter()
        tokens = await asyncio.gather(*[join(i) for i in range(students)])
        join_s = time.perf_counter() - t

        pushes: list[float] = []
        async with websockets.connect(base.replace("http", "ws", 1) + f"/api/v1/rooms/{room['id']}/live", additional_headers={"Cookie": cookie}, max_size=None) as tws:
            latest = {"members": []}

            async def drain():                                                                     # the teacher's screen keeps reading, as a browser does
                nonlocal latest
                async for message in tws:
                    latest = json.loads(message)

            reader = asyncio.create_task(drain())
            sockets = [await websockets.connect(base.replace("http", "ws", 1) + f"/api/v1/rooms/{room['id']}/live", max_size=None) for _ in tokens]
            for ws, token in zip(sockets, tokens):
                await ws.send(json.dumps({"token": token}))
            await asyncio.gather(*[ws.recv() for ws in sockets])                               # every student has its first state push
            started = time.perf_counter()
            r = await teacher.post(f"/api/v1/rooms/{room['id']}/rounds", json={"duration_s": 60})
            r.raise_for_status()
            target = r.json()["round"]["target"]
            await asyncio.gather(*[ws.recv() for ws in sockets])                               # every student is told, live, that the round began
            pushes.append(time.perf_counter() - started)

            lat, errors = [], 0

            async def submit(token: str, n: int):
                nonlocal errors
                t0 = time.perf_counter()
                r = await pool.post(f"/api/v1/rooms/{room['id']}/submit", json={"strokes": sketches[n % len(sketches)], "duration_ms": 3000}, headers={"X-Room-Token": token})
                (lat.append(time.perf_counter() - t0) if r.status_code == 200 else None)
                errors += r.status_code != 200

            t0 = time.perf_counter()
            await asyncio.gather(*[submit(tok, i) for i, tok in enumerate(tokens)])
            burst = time.perf_counter() - t0
            handed_in = 0
            while handed_in < students - errors and time.perf_counter() - t0 < 120:              # the teacher's screen counts the hand-ins as pushes arrive
                handed_in = sum(m["submitted"] for m in latest["members"])
                await asyncio.sleep(0.05)
            teacher_saw_all = time.perf_counter() - t0
            reader.cancel()
            for ws in sockets:
                await ws.close()
        await pool.aclose()
        print(f"  joined {students} students in {join_s:.1f} s; round start reached all {students} sockets in {pushes[0] * 1000:.0f} ms; "
              f"the teacher's screen showed {handed_in} hand-ins {teacher_saw_all:.1f} s after the burst began (target word: {target})", flush=True)
        return [summary(f"classroom: {students} simultaneous submissions", lat, errors, burst),
                {"scenario": "classroom live pushes", "students": students, "join_seconds": round(join_s, 2), "round_start_to_all_sockets_ms": round(pushes[0] * 1000),
                 "teacher_saw_all_handins_seconds": round(teacher_saw_all, 2), "handins_seen": handed_in}]


async def challenge_scenario(base: str, sketches: list, users: int) -> dict:
    day = httpx.get(base + "/api/v1/challenge/today").json()
    own = [s for s in json.loads((ROOT / "models" / json.loads((ROOT / "models" / "registry.json").read_text())["active"] / "samples.json").read_text()) if s["label"] == day["target"]]
    strokes = [s["strokes"] for s in own] or sketches
    clients = []
    for i in range(users):
        c = httpx.AsyncClient(base_url=base, timeout=300)
        await register(c, f"chal{time.time_ns()}{i}")
        clients.append(c)
    lat, errors = [], 0

    async def attempt(c: httpx.AsyncClient, n: int):
        nonlocal errors
        t = time.perf_counter()
        body = {"strokes": strokes[n % len(strokes)], "duration_ms": 3000}
        try:
            r = await c.post("/api/v1/challenge/attempts", json=body)
        except httpx.ReadError:                                                                    # the server closed an idle keep-alive connection (5 s): a browser retries too
            r = await c.post("/api/v1/challenge/attempts", json=body)
        (lat.append(time.perf_counter() - t) if r.status_code == 200 else None)
        errors += r.status_code != 200

    t0 = time.perf_counter()
    await asyncio.gather(*[attempt(c, i) for i, c in enumerate(clients)])
    out = summary(f"daily challenge: {users} simultaneous attempts", lat, errors, time.perf_counter() - t0)
    await asyncio.gather(*[c.aclose() for c in clients])
    return out


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--seconds", type=float, default=20)
    ap.add_argument("--students", type=int, default=60)
    ap.add_argument("--users", type=int, default=50)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    live = json.loads((ROOT / "models" / "registry.json").read_text())["active"]
    sketches = [s["strokes"] for s in json.loads((ROOT / "models" / live / "samples.json").read_text())]
    print(f"server {a.base}, live model {live}, {len(sketches)} real sketches as input\n", flush=True)
    results: list[dict] = []
    for name, scenario in (("predict", lambda: predict_scenario(a.base, sketches, a.workers, a.seconds)),
                           ("classroom", lambda: classroom_scenario(a.base, sketches, a.students)),
                           ("challenge", lambda: challenge_scenario(a.base, sketches, a.users))):
        try:
            out = await scenario()
            results += out if isinstance(out, list) else [out]
        except Exception as e:  # noqa: BLE001  (a failed scenario is a result: report it and carry on)
            print(f"{name}: FAILED with {type(e).__name__}: {e}", flush=True)
            results.append({"scenario": name, "error": f"{type(e).__name__}: {e}"})
    if a.out:
        a.out.write_text(json.dumps({"model": live, "results": results}, indent=2), encoding="utf-8")
        print("\nwrote", a.out)


if __name__ == "__main__":
    asyncio.run(main())
