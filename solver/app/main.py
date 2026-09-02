"""HTTP wrapper around the CP-SAT model. All the interesting code is in
`timetable_solver.py`."""

import asyncio
import json

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .models import SolveRequest, SolveResponse
from .timetable_solver import solve_timetable

app = FastAPI(
    title="Timetable Solver",
    description="OR-Tools CP-SAT university timetable scheduler (proof of concept).",
    version="0.1.0",
)

# Wide open on purpose: this is a local proof of concept with no data to protect,
# and it keeps `curl` and a separately-served frontend both working.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


# Declared `def`, not `async def`: solving is CPU-bound and blocking, so FastAPI
# runs it in a worker thread instead of stalling the event loop.
@app.post("/solve", response_model=SolveResponse)
def solve(request: SolveRequest) -> SolveResponse:
    return solve_timetable(request)


@app.post("/solve/stream")
async def solve_stream(request: SolveRequest) -> StreamingResponse:
    """The same solve, reporting its own progress as server-sent events.

    A solve is one long request -- on a faculty-sized problem, minutes of it --
    and `/solve` says nothing until it is over. This runs the identical solve and
    forwards the milestones it already passes: the model being built, then each
    rung of the priority ladder starting, improving and settling. The last event
    carries exactly the SolveResponse `/solve` would have returned.

    `/solve` is untouched and still the simpler thing to `curl`.
    """
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def emit(event: dict) -> None:
        # Called from the solver's worker thread, so it has to hop back onto the
        # loop rather than touch the queue directly.
        loop.call_soon_threadsafe(queue.put_nowait, event)

    async def run() -> None:
        try:
            result = await asyncio.to_thread(solve_timetable, request, emit)
            emit({"type": "done", "result": result.model_dump(mode="json")})
        except Exception as exc:  # noqa: BLE001 -- the client needs the reason, whatever it is
            emit({"type": "error", "message": f"{type(exc).__name__}: {exc}"})
        finally:
            emit(None)

    async def events():
        task = asyncio.create_task(run())
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield f"data: {json.dumps(event)}\n\n"
        finally:
            # A client that disconnects mid-solve leaves the thread running to
            # completion -- CP-SAT has no cancellation here -- but the task must
            # still be awaited so its exception is never swallowed.
            await task

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        # Proxies that buffer would defeat the whole point of streaming.
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
