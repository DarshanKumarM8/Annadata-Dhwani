# Annadata Dhwani (अन्नदाता ध्वनि)

A missed-call, keypad and voice marketplace that lets farmers with ₹1,000 button phones pool small harvests
into truckload clusters and sell them to wholesale buyers. Built in 24 hours for the Seva First Innovation
Challenge 2026 (theme: Samriddh Annadata, Samriddh Bharat).

- **What we are building and why:** [FINAL_IMPLEMENTATION_PLAN.md](FINAL_IMPLEMENTATION_PLAN.md)
- **Who builds what, the contracts, the schedule and the Gemini prompts:** [TASK_DIVISION.md](TASK_DIVISION.md)
- **Machine-readable contracts and fixtures:** [contracts/](contracts/)

## Run the mock server and the frontend (everyone, from H2)

You need Python 3.12+ and Node 20+.

```bash
python -m venv .venv
```

Windows (Git Bash): `source .venv/Scripts/activate` · macOS/Linux: `source .venv/bin/activate`

```bash
pip install -r mock/requirements.txt
```

```bash
python mock/mock_server.py
```

The mock runs on http://localhost:8001 (API docs at http://localhost:8001/docs). In a second terminal:

```bash
cd frontend && cp .env.example .env.local && npm install && npm run dev
```

Open http://localhost:5173. Routes: `/buyer` (Nahyan), `/sim` (Hitesh), `/agent` and `/ops` (Anirudh), `/login`.
The mock accepts any non-empty password; log in as `admin@demo.test` for admin endpoints.

Check that the mock behaves (optional): `pip install websockets` then `python mock/smoke_test.py`.

## Run the real stack (Darshan, from CP1)

```bash
cp .env.example .env
```

```bash
docker compose up -d
```

This starts PostGIS on 5432 (schema from `db/001_schema.sql` loads automatically on the first start)
and Valkey on 6379. To reload the schema from scratch: `docker compose down -v && docker compose up -d`.

### Backend (from D2)

With the containers up (and `.env` from `.env.example`; set `DB_PORT`/`DATABASE_URL` if 5432 is taken):

```bash
pip install -r backend/requirements.txt
```

```bash
python backend/scripts/dev_min_seed.py --floor 3565
```

`dev_min_seed.py` loads minimal reference data and a test farmer (+919800000001) until Anirudh's `db/002_reference.sql`
lands; `--floor` caches a ragi price floor (afpp 3430) so the price guardrail can be tried; `--reset` clears the test farmer.

```bash
cd backend && python -m uvicorn app.main:app --port 8000
```

In a second terminal, walk a full listing as the simulated phone (`--help` lists the options):

```bash
python backend/scripts/sim_client.py --price 3000 --bounce
```

Reliability (D3): every transition is checkpointed to Postgres `call_sessions`, so after `POST /api/ops/chaos/flush-redis`
(DEMO_MODE only) a live call carries on from where it was. Missed calls are deduplicated (20 s) and limited to 3 per
10 minutes and 6 per day per number; for rehearsals raise them with `RL_CB_10M` / `RL_CB_DAY` in `.env`.

Tests: `cd backend && python -m pytest`. The engine tests need nothing; `test_reliability.py` uses the compose stack
(Postgres + Valkey) and skips itself when it is not running. Set `SIM_RING_MIN=0.2 SIM_RING_MAX=0.3 SIM_HANGUP_DELAY=0.3` for quicker test calls.

## Folder ownership (only the owner edits a folder)

| Path | Owner |
|---|---|
| `docker-compose.yml`, `.env.example`, `contracts/`, `mock/`, `db/001_schema.sql`, `backend/app/` (except below), `frontend/src/lib/api.ts`, `frontend/src/App.tsx`, `frontend/src/main.tsx` | Darshan |
| `frontend/src/routes/Buyer.tsx`, `frontend/src/components/buyer/`, `frontend/src/lib/ws.ts`, `docs/exotel_setup.md`, `docs/backup_laptop.md` | Nahyan |
| `frontend/src/routes/Sim.tsx`, `frontend/src/components/sim/`, `backend/app/services/audio.py`, `backend/scripts/prewarm_audio.py`, `backend/prompts.yaml`, `audio/`, `docs/audio_tests.md` | Hitesh |
| `frontend/src/routes/Agent.tsx`, `frontend/src/routes/Ops.tsx`, `frontend/src/components/agent/`, `frontend/src/components/ops/`, `db/002_reference.sql`, `backend/app/services/pricing.py`, `backend/scripts/ingest_prices.py`, `backend/scripts/seed_demo.py`, `docs/` (deck, demo script) | Anirudh |

## Git workflow

- Branch per task: `feat/<name>-<task id>-<slug>`, for example `feat/nahyan-N3-ws-hook`.
- Open a small pull request into `main` as soon as it works against the mock. Darshan reviews and merges every PR.
- Never commit `.env`, API keys or tokens. Send keys to Darshan privately.
- Stuck for 20 minutes? Post `BLOCKED <task id>: <what you tried> / <what you need>` in the group and switch to your next task.
- Code freeze at H19 (tag `v-demo`). After that only Darshan merges, and only fixes.
