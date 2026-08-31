import json
import sys
from pathlib import Path

import pytest

# The service is imported as the `app` package, so `solver/` must be on the path
# whichever directory pytest was started from.
SOLVER_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SOLVER_DIR.parent
sys.path.insert(0, str(SOLVER_DIR))

SMALL_SEED_PATH = REPO_ROOT / "shared" / "seed-small.json"
FULL_SEED_PATH = REPO_ROOT / "shared" / "seed-full.json"


def build_slots(days, periods, blocked=()):
    """Same slot generation the frontend does: id is '<lowercased day>-<period>'."""
    slots = []
    for day in days:
        for period in range(1, periods + 1):
            slot_id = f"{day.lower()}-{period}"
            if slot_id in blocked:
                continue
            slots.append({"id": slot_id, "day": day, "period": period})
    return slots


def _request(data, groups, subjects, seconds):
    cfg = data["slotConfig"]
    return {
        "slots": build_slots(cfg["days"], cfg["periods"], set(cfg["blockedSlots"])),
        "teachers": data["teachers"],
        "rooms": data["rooms"],
        "groups": groups,
        "subjects": subjects,
        "maxTimeInSeconds": seconds,
    }


@pytest.fixture
def full_seed():
    """The UI's "Full example": all four years of Факултет "Полиция". Realistic,
    and slow enough that only the demo-budget test should use it."""
    data = json.loads(FULL_SEED_PATH.read_text())
    return _request(data, data["groups"], data["subjects"], 30.0)


@pytest.fixture
def seed():
    """The UI's "Small example", and the default fixture for everything here.

    It carries every shape the tests select on -- a поток lecture spanning
    several groups, per-group упражнения, all five room types (including
    firing_range, which the capacity test needs) and multi-candidate teacher
    pools -- at a size that solves in a fraction of a second, which is what keeps
    this suite quick.
    """
    data = json.loads(SMALL_SEED_PATH.read_text())
    return _request(data, data["groups"], data["subjects"], 10.0)
