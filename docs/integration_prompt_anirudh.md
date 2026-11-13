# Anirudh: integration fixes (self-contained brief)

You are fixing your part of **Annadata Dhwani** so it works with the real backend. Everything you need is in this file. Do the tasks in order. Report back using the template at the end.

## 0. Context

- Repo: https://github.com/DarshanKumarM8/Annadata-Dhwani, branch `main`. Pull first: `git pull origin main`. Work on a new branch: `git checkout -b feat/anirudh-integration`, open a pull request into `main` when done.
- The product: farmers with button phones give a missed call, get a call back, list a crop by keypad; listings pool into clusters; an FPO agent verifies a sample with a photo; buyers bid; farmers accept by phone; a deal is created.
- **The backend that works is `backend/app/` (FastAPI, Postgres+PostGIS, Valkey).** It already has: call engine, listings, clusters, live WebSocket feed, bidding, farmer offer calls, Exotel adapter, agent and ops endpoints. 106 tests pass. Run it: `cd backend && python -m uvicorn app.main:app --port 8000` (Postgres and Valkey from `docker compose up -d`). API docs: http://localhost:8000/docs.
- All backend code lives under `backend/` and imports as `app.` (for example `from app.services import pricing`). **Never import `backend.app...`**; that only works from the repo root and breaks when the server runs from `backend/`.
- Tests: `cd backend && python -m pytest`. Tests must use a **separate test database**, one-time setup:
  `docker compose exec db psql -U postgres -c "CREATE DATABASE annadata_test"` then
  `docker compose exec -T db psql -U postgres -d annadata_test < db/001_schema.sql`
  and run with `DATABASE_URL=postgresql://postgres:postgres@localhost:<DB_PORT>/annadata_test python -m pytest` (take the port from your `.env`).
- Frontend: `cd frontend && npm ci && npx tsc --noEmit && npx vite build` must pass.

## 1. Ground rules

1. Edit only your files: `frontend/src/routes/Agent.tsx`, `AgentApp.tsx`, `AgentVerify.tsx`, `Ops.tsx`, `frontend/src/components/agent/`, `components/ops/`, `db/002_reference.sql`, `backend/app/services/pricing.py`, `backend/scripts/ingest_prices.py`, `backend/scripts/seed_demo.py`, `docs/`, and your tests. **Do not edit**: `backend/app/main.py`, `backend/app/api/*`, `backend/app/engine/*`, `backend/app/telephony/*`, `backend/app/services/{bidding,clustering,jobs,events,views}.py`, `frontend/src/App.tsx`, `frontend/src/lib/api.ts`, `frontend/vite.config.ts`, `frontend/src/index.css`, `package.json`. If you need a change there, message Darshan with the exact request.
2. **Tailwind is pinned to v4** (`@tailwindcss/vite`, `@import "tailwindcss"` in `index.css`). Do not add `postcss.config.js`, `tailwind.config.js`, `autoprefixer` or `@tailwind` directives. Your last push broke the build for everyone for that reason; Darshan reverted it. If `vite build` fails on your laptop, run `npm ci` again and send Darshan the error text instead of changing config.
3. No secrets in git: no API keys, tokens, passwords, `.env`, `.env.local`. Do not commit `audio/mix/`.

## 2. Tasks

### T1. Security: remove the hard-coded key (do this first, 10 minutes)
`fetch_samples.py` (repo root) line 19 has a hard-coded data.gov.in API key. Fix: read it from the environment variable `DATA_GOV_KEY` (the name used in `.env`), delete the literal, and move the file to `backend/scripts/fetch_samples.py`. The old key is in git history, so treat it as exposed: if it is your personal key, generate a new one on data.gov.in and put it only in your local `.env`. Check `git grep -n -i "api_key *= *[\"']"` finds no literal key anywhere in the tree (never paste the key in chat or in a doc).

### T2. `db/002_reference.sql` must load cleanly, twice, with one command
Today it fails: it leaves `<HASH_PW>` / `<HASH_PIN>` placeholders, inserts buyers without the required `phone` column, and needs hand-substituted values. Rewrite it so this works against a database that only has `db/001_schema.sql` applied, and works again on a second run with no error:

```
docker compose exec -T db psql -U postgres -d annadata -v ON_ERROR_STOP=1 \
  -v venue_lat=12.9716 -v venue_lon=77.5946 -v seed_pw=<SEED_PASSWORD> -v agent_pin=1234 < db/002_reference.sql
```

Requirements:
- Start with `CREATE EXTENSION IF NOT EXISTS pgcrypto;`. Make hashes inside SQL: `crypt(:'seed_pw', gen_salt('bf', 10))` for buyers and `crypt(:'agent_pin', gen_salt('bf', 10))` for the agent. (Verified: these `$2a$10$` hashes pass the backend's Python `bcrypt.checkpw`.)
- Everything idempotent. Reference rows: `ON CONFLICT DO NOTHING`. Buyers: `ON CONFLICT (email) DO UPDATE SET password_hash = EXCLUDED.password_hash`. Agent: `ON CONFLICT (phone) DO UPDATE SET pin_hash = EXCLUDED.pin_hash`. So changing the password and rerunning updates logins.
- Keep: districts KA-MANDYA and KA-MYSURU; crops `ragi`, `paddy_common`, `maize` with your current msp/min/max; crop_calendar months 10, 11, 12 (ragi rank 1, paddy_common 2, maize 3) for both districts; deduction_rules per district; one FPO (payee_details `UPI keregodu-fpo@bank (demo)`); three collection points (Keregodu FPO yard, Hosahalli point, Venue demo point using `:venue_lat`/`:venue_lon`; build the point with `ST_SetSRID(ST_MakePoint(:venue_lon, :venue_lat), 4326)::geography`).
- Buyers (all `APPROVED`, each with a non-null `phone`, for example `+910000000001`..`3`): `buyer1@demo.test`, `buyer2@demo.test`, `admin@demo.test` (admin is just the buyer row with that email).
- Agent: phone **`+919800000099`**, name Kavya, PIN from `:agent_pin`, `fpo_id` = the FPO that owns the collection points. (Your second agent is fine to keep with another phone.)
- **Add the eight simulator farmers** (the phone simulator page shows these; without them the simulator hits "not registered"). All eight go to the **same collection point, "Keregodu FPO yard"**, same FPO, district KA-MANDYA, `lang` and `consent_at` NULL, `geog` near Keregodu (about lon 76.91, lat 12.53). The village text can differ:

  | phone | name | village |
  |---|---|---|
  | +919800000001 | Ramesh | Keregodu |
  | +919800000002 | Lakshmi | Keregodu |
  | +919800000003 | Manju | Hosahalli |
  | +919800000004 | Savitha | Hosahalli |
  | +919800000005 | Krishnappa | Keregodu |
  | +919800000006 | Meena | Hosahalli |
  | +919800000007 | Rajesh | Keregodu |
  | +919800000008 | Geetha | Hosahalli |

  Use `ON CONFLICT (phone) DO NOTHING` for farmers.
- Do **not** also run `backend/scripts/dev_min_seed.py` against the same database; it uses different ids. After your seed is validated, Darshan retires that script from the demo path.

Acceptance: on an empty database (schema only) run your command twice with zero errors; then `python backend/scripts/dev_demo_clusters.py` (Darshan's script, builds demo clusters from the eight farmers) runs successfully and prints three clusters; then the logins below work through the API:
`POST /api/auth/buyer/login {"email":"buyer1@demo.test","password":"<SEED_PASSWORD>"}` returns a token, and `POST /api/auth/agent/login {"phone":"+919800000099","pin":"1234"}` returns a token.

### T3. Agent screen (`AgentApp.tsx`) must call the real API
Your screen currently calls paths your own `routers/agent.py` defined. The real backend follows the contract below. Change the screen to this (all calls go through `frontend/src/lib/api.ts`: `api.get`, `api.post`, `api.postForm`; after login call `setToken(token)` from that file so later calls carry `Authorization: Bearer`). Errors arrive as HTTP status plus body `{"error":"CODE", ...}`; `ApiError.body.error` has the code.

| What | Call | Response |
|---|---|---|
| Login | `POST /api/auth/agent/login` body `{phone, pin}` | `{token, agent:{id, name, fpo_id}}`; 401 `BAD_CREDENTIALS`; 429 `LOCKED` after 5 wrong tries |
| Work list | `GET /api/agent/tasks` | `{verify:[cluster...], tickets:[{id, village, first_name, reason, status, created_at}], deals:[{id, cluster_code, status, qty_qtl, gross_value}]}` |
| Verify a cluster | `POST /api/agent/clusters/{id}/verification` multipart | `201 {cluster_id, status:"BIDDING"|"OPEN", bidding_ends_at}` |
| Claim ticket | `POST /api/agent/triage/{id}/claim` | `{status:"ASSIGNED"}`; 409 `ALREADY_CLAIMED` |
| Bridge call | `POST /api/agent/triage/{id}/bridge` | `{verbal_code, mode:"simulated"}` (shown once); 409 `CODE_USED` / `NOT_CLAIMED` |
| Confirm payment | `POST /api/agent/deals/{id}/payment-confirmed` | `{status:"PAID"}`; 409 `PAYMENT_NOT_REPORTED` |

A `cluster` object: `{id, code, crop_code, crop_name, district, collection_point:{name, lat, lon}, status, total_qtl, listing_count, min_ask, wavg_ask, grade, photo_url, bidding_ends_at, best_bid, version}`.

Verification multipart fields (all required except `moisture_pct`): `photo` (an image file, **max 2 MB**; compress to JPEG about 1280 px wide, quality 0.7, in the browser before upload), `grade` (`A`, `B`, `C` or `REJECT`), `lat`, `lon`, `accuracy_m` (use `position.coords.accuracy`), `captured_at` (ISO timestamp taken when the photo was captured), optional `moisture_pct`. Your current form is missing `accuracy_m` and `captured_at`, and silently skips lat/lon when GPS fails: **block the submit with a clear message when there is no GPS fix.** Drop the `notes` field (the backend ignores it).
Verification errors: 422 `TOO_FAR` (with `distance_m`; the agent must be within 500 m of the pickup point), 422 `STALE_CAPTURE` (photo older than 10 minutes), 422 `LOW_ACCURACY` (accuracy worse than 200 m), 422 `BAD_GRADE`, 409 `ALREADY_VERIFIED`, 409 `NOT_READY`, 403 `FORBIDDEN` (cluster belongs to another FPO), 413 `PHOTO_TOO_LARGE`. Show a readable message for each.
Offline queue: keep it, but a queued photo older than 10 minutes will be refused with `STALE_CAPTURE`: tell the agent to retake it, do not retry forever. Treat 409 `ALREADY_VERIFIED` as success and remove the item.

Things your screen shows that the backend does **not** provide: farmer names and phone numbers (never returned, by design: privacy), `GET /api/agent/collection-points`, `GET /api/agent/verifications` history, `GET /api/agent/clusters/{id}` detail. Remove farmer name/phone from the UI and types. Build the cluster list from `tasks.verify` (it already has the pickup point name and coordinates); keep a local history in `localStorage` if you want one. If you truly need one of the missing endpoints, message Darshan with the exact JSON shape you want and he will add it.

Wire the route: `frontend/src/routes/Agent.tsx` must export the screen as default (currently it is a placeholder; make it `export { default } from "./AgentApp";`). `App.tsx` already routes `/agent` to `Agent`.
Nice to have: connect to `ws://<host>:8000/ws?token=<agent token>&since=<last seq>`; messages are `{seq, type, payload}`; refresh the task list on `task.created` and `cluster.updated`; on `{"type":"resync"}` refetch.
Acceptance: log in as the agent, see the READY ragi cluster from `dev_demo_clusters.py`, verify it (with a real photo near its coordinates, or temporarily set `VERIFY_RADIUS_M=5000` in `.env` for rehearsal), and watch it become BIDDING; the buyer view (and Darshan's `http://localhost:8000/demo` page) updates by itself.

### T4. Ops page (`Ops.tsx`) is still a placeholder; build it
All `/api/ops/*` and the flush need an **admin** token: log in with `POST /api/auth/buyer/login` as `admin@demo.test` and call `setToken`. Build one page that:
- polls `GET /api/ops/calls` every 1 s. Response: `{sessions:[{phone_masked, kind, state, provider, version, updated_at}], jobs:[{id, kind, status, attempts, run_at}], breaker:{calls_today, budget}}`. Show state badges, flash a row when its `version` increases.
- polls `GET /api/ops/dtmf?limit=50` every 1 s. Response: `{events:[{session_id, state_before, digits, state_after, dropped_reason, at}]}`. Rows with `dropped_reason == "BOUNCE"` in red.
- polls `GET /health` (no token) every 5 s: `{db, redis, provider, tts_clips, price_age_days}`; show green/red lights.
- has a "Flush Redis" button with a confirm dialog calling `POST /api/ops/chaos/flush-redis` (returns `{ok:true}`). Live calls must carry on afterwards: that is the demo.
Acceptance: run a listing from the phone simulator page (`/sim`) while this page is open; the live session and the keypresses appear within 2 seconds; press Flush Redis mid-call and the call still completes.

### T5. Your `backend/app/routers/` duplicates working endpoints: retire it
`routers/agent.py`, `buyer.py`, `ivr.py`, `ops.py`, `prices.py` are not mounted by `main.py` and duplicate (with other paths and shapes) what `backend/app/api/` already does. `ivr.py` is a second IVR; the real one is `backend/app/engine/`. Do this:
1. Delete `routers/agent.py`, `routers/buyer.py`, `routers/ivr.py`, `routers/ops.py` once your UI no longer depends on them (after T3, T4).
2. If `routers/prices.py` has an endpoint worth keeping (for example a prices read endpoint), port it to `backend/app/api/prices.py` using the same conventions as `backend/app/api/clusters.py`: `APIRouter(prefix="/api")`, `from .. import db, cache`, auth with `Depends(require("buyer"))` or `require("admin")` from `.auth`, errors by `raise ApiError(status, "CODE")`, JSON errors shaped `{"error": CODE}`. Then ask Darshan to add one line to `main.py` to mount it. Delete `routers/` entirely afterwards.
3. Tests: your four router tests (`test_agent_api.py`, `test_ops_api.py`, `test_price_ingestion.py`, `test_e2e_acceptance_and_chaos.py`) are currently skipped by `backend/pytest.ini` (`addopts = --ignore=...`). Make each one pass against the real app or delete it. Real-app pattern: `from app.main import app`, `httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")`, real Postgres/Valkey on the test database, see `backend/tests/test_d5.py` and `backend/tests/test_exotel.py` for working examples (they set `app.state.deps = PgDeps(pool)` and call `db.connect()` / `cache.connect()` themselves). Change `from backend.app...` imports to `from app...`. Remove each file's `--ignore` entry from `backend/pytest.ini` once it passes. `test_pricing.py` already passes; keep it green.

### T6. Pricing and ingestion must feed the live system
- `pricing.refresh(pool, redis)` is called by `POST /api/admin/prices/refresh`. It imports `backend.scripts.ingest_prices`, which fails when the server runs from `backend/`. Import `scripts.ingest_prices` instead (the server's working directory is `backend/`), and inside `ingest_prices.py` also remove `backend.` imports. Test by calling that endpoint as admin: it must return `{"floors_written": N}` with N greater than 0 using the fixtures in `contracts/fixtures/agmark_*.json` (offline mode).
- Ingestion must write: `mandi_prices` rows (the `/health` field `price_age_days` is computed from the newest `price_date`), `price_floors` rows, **and the Redis key `floor:{district_code}:{crop_code}`** (JSON `{"modal_price":..., "afpp":..., "basis":..., "price_date":"YYYY-MM-DD"}`, expiry 93600 s). The cluster detail endpoint reads that Redis key directly; if only the database has the floor, buyers see no price reference. Commodity names must match the `crops.agmark_name` values: `Ragi (Finger Millet)`, `Paddy(Dhan)(Common)`, `Maize`.
- `afpp` formula stays: `floor(modal * (1 - pct_deduction) - transport - handling` to the nearest 10 below`)`. The IVR fires its guardrail when the farmer's price is below `afpp * 0.97`.
Acceptance: after refresh, `docker compose exec cache valkey-cli get floor:KA-MANDYA:ragi` returns JSON; `GET /health` shows a numeric `price_age_days`; a phone-simulator listing speaks the mandi and fair price (the dtmf log shows the PRICE state).

### T7. Audio and prompt text: report status, no new files in git
You committed the generated clips under `audio/kn` and `audio/hi` (fine). Do not commit `audio/mix/` (generated cache; confirm `.gitignore` covers it). Tell Darshan whether the Kannada and Hindi text in `backend/prompts.yaml` is real, native-reviewed text or the English placeholder, and mark `reviewed: true` only for lines a native speaker actually checked.

## 3. Definition of done (run all, paste results in your report)
```
cd backend && DATABASE_URL=<test db> python -m pytest        # all green, no router test files ignored
cd frontend && npm ci && npx tsc --noEmit && npx vite build   # passes, no config changes
git grep -n "backend\.app\|backend\.scripts"                 # nothing left
```
plus the acceptance line of T2, T3, T4 and T6, each with what you saw.

## 4. Report back (reply to Darshan in the group, one line each)
`pushed feat/anirudh-integration` and: T1 key rotated yes/no; T2 loads twice yes/no and the exact command you used; T3 agent verify works end to end yes/no; T4 ops page works yes/no; T5 which routers removed, which tests passing; T6 floors_written number; T7 kn/hi text status. Anything blocked for more than 20 minutes: `BLOCKED <task>: <what you tried> / <what you need>`.
