"""Benchmark the solver against the payloads the UI actually sends.

Not a test. The pytest fixtures shorten the semester (``conftest.compress``) so
the suite stays quick; that hides the cost that matters, because the real request
carries the whole 18-week term. This builds the same payload ``frontend/src/api.ts``
posts -- every dated slot of the semester -- and reports where the time goes.

    .venv/bin/python bench.py                 # both seeds, default budget
    .venv/bin/python bench.py --budget 900    # long enough for the whole ladder
    .venv/bin/python bench.py --seed small
    .venv/bin/python bench.py --semester 2   # the seeds carry both semesters
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / "tests"))

from conftest import (  # noqa: E402
    FULL_SEED_PATH,
    SEED_SEMESTER,
    SEED_SEMESTER_2,
    SMALL_SEED_PATH,
    _request,
)

SEMESTERS = {1: SEED_SEMESTER, 2: SEED_SEMESTER_2}

from app.models import SolveRequest  # noqa: E402
from app.sessions import build_series  # noqa: E402
from app import timetable_solver as ts  # noqa: E402


def request_for(path: Path, budget: float, semester: int = 1) -> SolveRequest:
    """The payload the UI would send for one semester of this seed.

    Uncompressed on purpose: the fixtures shorten the term to keep the suite
    quick, and the cost this script exists to measure is the one that only shows
    up over a real term. Both seeds carry two semesters and a solve covers one,
    so the semester is a parameter here exactly as it is in the UI.
    """
    data = json.loads(path.read_text())
    payload = _request(data, data["courseInstances"], data["offerings"], budget,
                       semester=SEMESTERS[semester])
    payload["roles"] = data["roles"]
    return SolveRequest(**payload)


def run(label: str, path: Path, budget: float, semester: int) -> None:
    req = request_for(path, budget, semester)
    series = build_series(req, req.semester)
    sessions = sum(s.count for s in series)
    print(
        f"{label}: {len(req.slots)} periods, "
        f"{len(req.offerings)} offerings, {len(series)} series, {sessions} sessions, "
        f"{len(req.rooms)} rooms, {len(req.teachers)} teachers, "
        f"{len(req.groups)} groups + {len(req.subgroups)} подгрупи, budget {budget:g}s"
    )

    start = time.perf_counter()
    result = ts.solve_timetable(req)
    wall = time.perf_counter() - start

    stats = result.stats
    # Build time is what is left once the solver's own seconds are taken out --
    # the number the ladder never gets to spend on searching.
    solve_seconds = stats.solveTimeSeconds if stats else 0.0
    print(
        f"  wall {wall:7.1f}s   solve {solve_seconds:7.1f}s   "
        f"build+readback {wall - solve_seconds:7.1f}s"
    )
    print(
        f"  status {result.status}   objective {stats.objectiveValue if stats else None}   "
        f"placed {stats.numPlaced if stats else 0}/{stats.numSessions if stats else 0}   "
        f"booleans {stats.numBooleanVariables if stats else 0}"
    )
    if stats:
        for tier in stats.tiers:
            roles = ", ".join(tier.roles) or "unranked"
            print(
                f"    tier w={tier.weight} {tier.status:<11} "
                f"{tier.solveTimeSeconds:6.1f}s  penalty {tier.penalty:6d}  ({roles})"
            )
    if result.validation is not None and not result.validation.ok:
        print(f"  VALIDATION FAILED: {result.validation.errors[:3]}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--budget", type=float, default=30.0)
    parser.add_argument("--seed", choices=("small", "full", "both"), default="both")
    parser.add_argument("--semester", choices=("1", "2", "both"), default="1")
    args = parser.parse_args()

    seeds = {"small": SMALL_SEED_PATH, "full": FULL_SEED_PATH}
    wanted = (1, 2) if args.semester == "both" else (int(args.semester),)
    for name in ("small", "full"):
        if args.seed in (name, "both"):
            for semester in wanted:
                run(f"{name.upper()} S{semester}", seeds[name], args.budget, semester)


if __name__ == "__main__":
    main()
