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

D4 (clusters, events, live feed): `POST /api/auth/buyer/login` (seeded `buyer1@demo.test`, `buyer2@demo.test`,
`admin@demo.test`, password = `SEED_PASSWORD` in `.env`), `GET /api/clusters?status=OPEN,READY&crop=`, `GET /api/clusters/{id}`
(all need `Authorization: Bearer <token>`), and the dashboard feed `ws://localhost:8000/ws?token=<jwt>&since=<seq>`.
A cluster turns READY at 20 quintals and announces one VERIFY task to agents. Events are stored in the `events` table in the
same transaction as the change, so a reconnecting client with `since` gets what it missed; if it is too far behind, or ahead
after a database reset, it receives `{"type":"resync"}` and should refetch the REST lists. Bids, deals and the agent/admin
routes are D5.

D5 (the trade, end to end): agent login `POST /api/auth/agent/login` (seeded `+919800000099`, PIN `1234`), `GET /api/agent/tasks`,
`POST /api/agent/clusters/{id}/verification` (multipart; within 500 m, capture under 10 min old; READY becomes BIDDING and starts the
3-minute demo auction), `POST /api/clusters/{id}/bids` (needs `Idempotency-Key`; each bid beats the best by Rs 10), `GET /api/bids/mine`,
`GET /api/deals/mine`, `POST /api/deals/{id}/payment-reported`, `POST /api/agent/deals/{id}/payment-confirmed`, triage `claim`/`bridge`.
Admin (login `admin@demo.test`): `POST /api/admin/clusters/{id}/close-auction`, `GET /api/ops/calls`, `GET /api/ops/dtmf`, the Redis flush.
The farmers' accept/reject round is not wired to phone calls yet: in the demo use
`POST /api/admin/clusters/{id}/simulate-farmers` with `{"accept": true}` (or `{"accepted_lots": 3}`); if nobody answers, the round
settles at the deadline (90 s in demo mode). Deal created when accepted quantity reaches the bid's minimum; otherwise the bid fails,
the cluster returns to BIDDING once, then NO_BID.

D6 (farmers' confirmation calls): closing an auction queues one `BID_OFFER` call per lot in `call_jobs`. The worker (1 s tick) rings the
farmer's phone, at most 5 calls at once, skips anyone already on a call, honours `DAILY_CALL_BUDGET`, and retries an unanswered
call after 20/40/60 s in demo mode (2/10/30 min otherwise). On `/sim` the phone rings like a callback; answering reads the offer:
1 then 1 accepts, 2 rejects, 9 repeats. When every lot has answered (or the 90 s deadline passes) the round settles into a deal or a
failed bid. `simulate-farmers` still exists as a backup that skips the phone calls. `telephony/base.py` is the provider interface
that the Exotel adapter (D7) plugs into.

Tests should not share your dev database (a running server's job worker would claim the test jobs). One-time setup, then run
the suite against the separate database:
```bash
docker exec annadata-db-1 psql -U postgres -c "CREATE DATABASE annadata_test"
docker exec -i annadata-db-1 psql -U postgres -d annadata_test < db/001_schema.sql
```
```bash
cd backend && DATABASE_URL=postgresql://postgres:postgres@localhost:5433/annadata_test python -m pytest
```
(use your own port/credentials from `.env`; the tests create the reference rows they need).

D7 (real phones through Exotel): `backend/app/telephony/exotel.py` serves `/tel/exotel/{WEBHOOK_SECRET}/missed|gather|digits|status`
and places calls with the Exotel connect API. A missed call queues a `CALLBACK` job in the same queue as the offer calls; the
worker rings the farmer, Exotel runs the `annadata-ivr` flow, and every Gather/Passthru pair is one engine event. Real numbers go
through Exotel and `/sim` farmers still ring in the browser at the same time. Events are accepted only for call ids we started.
`python backend/scripts/exotel_check.py --ping` lists missing settings and the exact URLs to paste into the Exotel flow. To go live:
(1) Nahyan builds the flow and sends the App ID -> `EXOTEL_APP_ID`, (2) set `TELEPHONY_PROVIDER=exotel`, restart,
(3) missed-call a whitelisted phone. The applet behaviour (quoted digits, Passthru 404 = hang up) is unverified until that spike.

Live board for demos: open `http://localhost:8000/demo`, enter `SEED_PASSWORD`, and watch clusters, bids and deals update live.
The buttons stand in for the agent PWA, buyer screens and farmers' accept calls (a stopgap until those UIs merge).
Serve the backend to other laptops on the same Wi-Fi with `--host 0.0.0.0` and point their `VITE_API_BASE` / `VITE_WS_BASE` at your IP.

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
