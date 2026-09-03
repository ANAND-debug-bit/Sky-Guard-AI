"""FastAPI backend: live stream + normal REST API.

Two halves:
  - stream : a background ingestor consumes the sensor simulator's NDJSON
             stream (`/v1/sensor/injected`) and fans rows out to SSE clients
             via `/stream`, while keeping a rolling in-memory buffer.
  - normal : classic REST endpoints over that buffer (`/readings`,
             `/readings/latest`, `/anomalies`, `/stations`, `/health`).

Run (after starting the simulator on :8000), from `microservices/app/`:
    uvicorn backend:app --port 3000

Prototype scope: in-memory buffer, no database. Rows are plain dicts that
match the simulator's injected schema (is_anomaly / anomaly_type /
affected_sensor included).
"""

import asyncio
import json
import threading
from collections import deque
from pathlib import Path

import requests
from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse

# --- config -------------------------------------------------------------
SIMULATOR_URL = "http://127.0.0.1:8000"
INGEST_STREAM = f"{SIMULATOR_URL}/v1/sensor/injected"
BUFFER_SIZE = 10000          # rolling rows kept for the normal endpoints
CONNECT_RETRY_S = 5          # backoff before retrying the simulator
FRONTEND_INDEX = (
    Path(__file__).resolve().parent.parent / "frontend" / "index.html"
)

app = FastAPI(title="SkyGuard backend", version="0.1.0")


class Ingestor:
    """Consumes the simulator stream in a daemon thread.

    One consumer, many subscribers: every parsed row goes into the rolling
    buffer AND is pushed to every live SSE client. If the simulator is not
    running, the thread retries forever so the REST API still works.
    """

    def __init__(self) -> None:
        self._buffer: deque = deque(maxlen=BUFFER_SIZE)
        self._latest: dict[str, dict] = {}        # station_id -> last row
        self._subscribers: dict[int, asyncio.Queue] = {}  # id -> client queue
        self._lock = threading.Lock()
        self._next_id = 0
        self.started = False

    # ---- internal helpers (called from the worker thread) ---------------
    def _loop(self, loop) -> None:
        import asyncio

        while True:
            try:
                with requests.get(INGEST_STREAM, stream=True) as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if not line:
                            continue
                        try:
                            row = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        asyncio.run_coroutine_threadsafe(
                            self._async_record(row), loop
                        )
            except Exception as exc:  # simulator down, transient read errors
                print(f"[ingestor] reconnect in {CONNECT_RETRY_S}s: {exc}")
                import time

                time.sleep(CONNECT_RETRY_S)

    async def _async_record(self, row: dict) -> None:
        with self._lock:
            self._buffer.append(row)
            self._latest[row["id"]] = row
            subscribers = list(self._subscribers.values())
        for queue in subscribers:
            queue.put_nowait(row)

    # ---- public API (called from the event loop) ------------------------
    def start(self) -> None:
        if self.started:
            return
        self.started = True
        import asyncio

        loop = asyncio.get_running_loop()
        threading.Thread(
            target=self._loop, args=(loop,), daemon=True, name="ingestor"
        ).start()

    def subscribe(self, queue) -> int:
        with self._lock:
            self._next_id += 1
            self._subscribers[self._next_id] = queue
            return self._next_id

    def unsubscribe(self, sub_id: int) -> None:
        with self._lock:
            self._subscribers.pop(sub_id, None)

    def readings(self, limit: int, station: str | None = None) -> list[dict]:
        with self._lock:
            rows = list(self._buffer)
        if station:
            rows = [r for r in rows if r["id"] == station]
        return rows[-limit:]

    def latest(self) -> list[dict]:
        with self._lock:
            return list(self._latest.values())

    def anomalies(self, limit: int, station: str | None = None) -> list[dict]:
        with self._lock:
            rows = [r for r in self._buffer if r.get("is_anomaly")]
        if station:
            rows = [r for r in rows if r["id"] == station]
        return rows[-limit:]


ingestor = Ingestor()


# --- startup / shutdown --------------------------------------------------
@app.on_event("startup")
async def startup() -> None:
    ingestor.start()


# --- stream side ---------------------------------------------------------
@app.get("/")
async def index():
    """Serve the dashboard page (see microservices/frontend/)."""
    return FileResponse(FRONTEND_INDEX)


@app.get("/stream")
async def stream():
    """Server-Sent Events: one JSON row per event, live from the simulator."""
    import asyncio

    queue: asyncio.Queue = asyncio.Queue()
    sub_id = ingestor.subscribe(queue)

    async def event_gen():
        try:
            while True:
                row = await queue.get()
                yield f"data: {json.dumps(row)}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            ingestor.unsubscribe(sub_id)

    return StreamingResponse(
        event_gen(), media_type="text/event-stream"
    )


# --- normal side ---------------------------------------------------------
@app.get("/health")
async def health():
    with ingestor._lock:
        buffered = len(ingestor._buffer)
    return {
        "status": "running",
        "buffered_rows": buffered,
        "stations": sorted({r["id"] for r in ingestor.latest()}),
    }


@app.get("/readings")
async def readings(station: str | None = None, limit: int = 100):
    limit = max(1, min(limit, BUFFER_SIZE))
    return {"count": len(ingestor.readings(limit, station)),
            "rows": ingestor.readings(limit, station)}


@app.get("/readings/latest")
async def readings_latest():
    return {"rows": ingestor.latest()}


@app.get("/anomalies")
async def anomalies(station: str | None = None, limit: int = 100):
    limit = max(1, min(limit, BUFFER_SIZE))
    return {"count": len(ingestor.anomalies(limit, station)),
            "rows": ingestor.anomalies(limit, station)}


@app.get("/stations")
async def stations():
    return {"stations": sorted({r["id"] for r in ingestor.latest()})}