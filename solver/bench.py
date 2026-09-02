"""Benchmark the solver against the payloads the UI actually sends.

Not a test. The pytest fixtures shorten the semester (``conftest.compress``) so
the suite stays quick; that hides the cost that matters, because the real request
carries the whole 18-week term. This builds the same payload ``frontend/src/api.ts``
posts -- every dated slot of the semester -- and reports where the time goes.

    .venv/bin/python bench.py                 # both seeds, default budget
    .venv/bin/python bench.py --budget 900    # long enough for the whole ladder
    .venv/bin/python bench.py --seed small
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
    SMALL_SEED_PATH,
    build_slots,
    semester_span,
)

from app.models import SolveRequest  # noqa: E402
from app import timetable_solver as ts  # noqa: E402


def request_for(path: Path, budget: float) -> SolveRequest:
    """The payload the UI would send for this seed's first semester."""
    data = json.loads(path.read_text())
    cfg = data["slotConfig"]
    start, end = semester_span(data["groups"], SEED_SEMESTER)
    slots = build_slots(
        cfg["days"], cfg["periods"], set(cfg["blockedSlots"]), start, end
    )
    return SolveRequest(
        semester=SEED_SEMESTER,
        slots=slots,
        roles=data["roles"],
        teachers=data["teachers"],
        rooms=data["rooms"],
        groups=data["groups"],
        subjects=data["subjects"],
        maxTimeInSeconds=budget,
    )


def run(label: str, path: Path, budget: float) -> None:
    req = request_for(path, budget)
    sessions = sum(
        x.totalSessions
        for s in req.subjects
        for x in s.semesters
        if x.academicYear == SEED_SEMESTER["academicYear"]
        and x.index == SEED_SEMESTER["index"]
    )
    print(
        f"{label}: {len(req.slots)} slots, {len(req.subjects)} subjects, "
        f"{sessions} sessions, {len(req.rooms)} rooms, {len(req.teachers)} teachers, "
        f"{len(req.groups)} groups, budget {budget:g}s"
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
    args = parser.parse_args()

    seeds = {"small": SMALL_SEED_PATH, "full": FULL_SEED_PATH}
    for name in ("small", "full"):
        if args.seed in (name, "both"):
            run(name.upper(), seeds[name], args.budget)


if __name__ == "__main__":
    main()
