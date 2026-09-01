# solver-demo

Timetable generator: a React + Vite frontend (`frontend/`) posting a whole problem to a FastAPI +
OR-Tools CP-SAT service (`solver/`). No database, no server-side session — `frontend/src/types.ts`
and `solver/app/models.py` mirror each other and together are the entire wire format. Shared example
datasets live in `shared/`.

## UI work

**Before changing anything under `frontend/`, read [`frontend/DESIGN.md`](frontend/DESIGN.md).**

The look is derived from a Claude Design project, not invented here, and it must not drift. That file
carries the provenance, the token rules, the non-negotiables (one accent, no shadows on chrome, no
gradients, weight 500 never used) and the literal specs for every control. Design tokens in
`frontend/src/styles/ds/` are a verbatim copy of the design project — never hand-edit them.

## Running it

```bash
# solver on :8000
cd solver && .venv/bin/uvicorn app.main:app --reload --port 8000
# frontend on :5173
cd frontend && npm install && npm run dev
```

## Checks

```bash
cd frontend && npx tsc --noEmit
cd solver && .venv/bin/pytest
```

The solver suite takes ~10 minutes and several tests assert `OPTIMAL` inside a fixed time budget, so
run it on an otherwise idle machine — a busy CPU makes those tests flaky.
