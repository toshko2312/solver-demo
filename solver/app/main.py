"""HTTP wrapper around the CP-SAT model. All the interesting code is in
`timetable_solver.py`."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

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
