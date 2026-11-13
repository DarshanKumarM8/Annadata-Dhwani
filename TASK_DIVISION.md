# Annadata Dhwani: 24-Hour Task Division

**Source of truth:** `FINAL_IMPLEMENTATION_PLAN.md` (the "plan"). Section numbers like "plan §5.1" point into it.
**Clock:** H0 = the moment the hackathon started. All times below are hours from H0. **Code freeze: H19. Demo-ready: H24.**
**Tags:** `[CLAUDE-CODE]` Darshan, agentic build · `[MANUAL-GUI]` accounts, dashboards, phones, people · `[GEMINI-OK]` bounded code, content or docs for Gemini (AI Chat or Antigravity) · `[Assumed]` my guess, not a fact.

> **Read this first: the plan was written for 14 days; you have 24 hours.** The plan's own cut line (plan §12) is applied hard. What survives is the plan's "never cut" core plus the jury-visible failure demos. Everything removed is listed in §2 and §10. Do not build anything from the plan that is not in a task below.

---

## 1. Summary

Hours assume **about 20 productive hours per person** out of 24, with one staggered 90-minute rest each and meal breaks [Assumed].

| Person | Role / vertical | Tasks | Total hours | % of effort | Main deliverables |
|---|---|---|---|---|---|
| **Darshan** | Backend core and integration: call engine, reliability, clustering, bidding, call queue, WebSocket, Exotel adapter | 10 | 20.5 | 26 % | Running FastAPI backend, Redis/Postgres state, everyone's work merged, live failure injection |
| **Nahyan** | Buyer marketplace and real phone line: buyer dashboard, Exotel account and flow, real-phone tests, backup laptop | 9 | 19.0 | 24 % | Live bidding dashboard; a real button phone ringing through Exotel; a second laptop that runs the demo |
| **Hitesh** | Voice and network physics: prompts in Kannada and Hindi, TTS → 8 kHz pipeline, audio mixer, browser phone simulator, handset tests, demo video | 9 | 19.5 | 25 % | Every spoken prompt as 8 kHz audio; the simulator phone with bounce and drop switches; the backup video |
| **Anirudh** | Markets, field and story: mandi price ingestion and AFPP floor, seed data, FPO agent PWA, ops monitor, pitch deck, acceptance testing | 9 | 20.0 | 25 % | Live price floor in the call; FPO verification on a phone; ops screen; pitch deck |
| **Total** | | 37 | 79.0 | 100 % | |

**About the 50–55 % cap.** Measured in hours, Darshan is at 26 %, far under the cap, because nobody can work more than 24 hours. The cap is the wrong risk for a 24-hour event. The real risk is that **every integration checkpoint passes through Darshan**, and his tasks have almost no slack. The division handles that by (a) giving the other three complete verticals built against mocks, so they never wait for him, (b) cutting scope until his build fits in 18 hours, and (c) naming a backup for every module he owns (§8).

---

## 2. Division principles applied

1. Darshan owns everything stateful or concurrent (engine, Lua, idempotency, clustering transaction, bidding, call queue, WebSocket, Exotel adapter) and merges every pull request; the others own complete verticals with a visible jury moment each, built against the mock server from H2.
2. Each Gemini task is one file or one folder, with the exact contract pasted into its prompt, so it can be built and tested without Darshan's running code.
3. Accounts are created by the person whose vertical uses them (Exotel: Nahyan; Bhashini: Hitesh; data.gov.in: Anirudh). ngrok runs on Darshan's demo laptop, so only Darshan can do that one.
4. **Cut for 24 hours:** Asterisk path, Marathi, cloud mirror, ledger and pickup weights, proxy listing and its confirmation call, real masked bridge (simulated), buyer self-registration, listing withdrawal, "9 for more crops", dynamic TTS (numbers are spoken digit by digit from fixed clips), historical backfill, Locust load test (replaced by a short asyncio script).
5. **Simplified, not cut:** triage keeps the 3-failure ticket and the spoken two-digit code; the deal ends at "payment reported / payment confirmed" buttons with no money; the auction window is 3 minutes and the confirmation round 90 seconds.

---

## 3. Contracts

Contracts v0 are written **in this section**, so everyone can start at H0 from this file. Darshan copies them into the repository as code (`contracts/`, fixtures, mock server) and **freezes them at H2**. After H2, a contract changes only if Darshan announces it in the group with the exact diff.

| ID | Contract | Owner | Freeze |
|---|---|---|---|
| C1 | Repository layout and folder ownership | Darshan | H1 |
| C2 | Environment variables | Darshan | H1 |
| C3 | Database schema | Darshan (seed values: Anirudh) | H2 |
| C4 | REST endpoints | Darshan | H2 |
| C5 | Dashboard WebSocket events | Darshan | H2 |
| C6 | Simulator phone WebSocket protocol | Darshan (Hitesh reviews) | H2 |
| C7 | Exotel webhooks and App Bazaar flow | Darshan (Nahyan reviews) | H2 |
| C8 | IVR state names and audio clip ids | Darshan (states), Hitesh (clip list and text) | H2 |
| C9 | Python module interfaces (pricing, audio) | Darshan | H2 |
| C10 | Redis keys | Darshan | H2 |
| C11 | Mock server and fixtures | Darshan | H2 |

### C1. Repository layout and folder ownership

One GitHub repository (free, private), `annadata-dhwani`. **Only the owner edits a folder.** Changes to someone else's folder go through that owner.

```
annadata-dhwani/
  docker-compose.yml              Darshan     postgis/postgis:16-3.4 on 5432, valkey/valkey:8 on 6379
  .env.example                    Darshan
  contracts/                      Darshan     fixtures/*.json, clip_ids.txt, states.md
  mock/mock_server.py             Darshan     fake backend on :8001
  db/001_schema.sql               Darshan
  db/002_reference.sql            Anirudh     districts, crops, deduction_rules, crop_calendar, fpo, points, agents, buyers
  backend/app/                    Darshan     main, engine/, telephony/, services/ (except two files below), api/
  backend/app/services/pricing.py Anirudh
  backend/app/services/audio.py   Hitesh
  backend/app/lua/                Darshan
  backend/scripts/ingest_prices.py Anirudh
  backend/scripts/seed_demo.py    Anirudh
  backend/scripts/prewarm_audio.py Hitesh
  backend/prompts.yaml            Hitesh
  backend/tests/                  Darshan (+ test files named after each owner's module)
  audio/kn/*.wav audio/hi/*.wav   Hitesh      generated, committed (small)
  frontend/                       shell by Darshan; then:
    src/routes/Buyer.tsx + src/components/buyer/*   Nahyan
    src/lib/ws.ts                                   Nahyan
    src/routes/Sim.tsx + src/components/sim/*       Hitesh
    src/routes/Agent.tsx + src/components/agent/*   Anirudh
    src/routes/Ops.tsx                              Anirudh
    src/lib/api.ts, src/main.tsx, src/App.tsx       Darshan
  docs/                           Anirudh     deck, demo script; Nahyan: exotel_setup.md, backup_laptop.md; Hitesh: audio_tests.md
```

### C2. Environment variables

Backend (`.env`, never committed):

```
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/annadata
REDIS_URL=redis://localhost:6379/0
JWT_SECRET=<random 32 chars>
PUBLIC_BASE_URL=http://localhost:8000          # becomes https://<static>.ngrok-free.app for Exotel and phones
TELEPHONY_PROVIDER=sim                          # sim | exotel
WEBHOOK_SECRET=<random 32 chars>
EXOTEL_SID= EXOTEL_API_KEY= EXOTEL_API_TOKEN= EXOPHONE= EXOTEL_APP_ID=
DATA_GOV_KEY=
BHASHINI_USER_ID= BHASHINI_API_KEY= BHASHINI_PIPELINE_ID=
SEED_PASSWORD=<demo password for seeded buyers, agents and admin>
DEMO_MODE=1                                     # auction 180 s, confirm round 90 s, no calling-hours limit
DAILY_CALL_BUDGET=200
```

Frontend (`frontend/.env.local`):

```
VITE_API_BASE=http://localhost:8001     # mock server until CP2, then http://localhost:8000
VITE_WS_BASE=ws://localhost:8001        # then ws://localhost:8000
```

### C3. Database schema

The full DDL is plan §5.1 and Darshan puts it in `db/001_schema.sql` unchanged, except: the `ledger` table is not used. Tables and the columns other people touch:

| Table | Columns used outside the backend core |
|---|---|
| `districts` | `code` ('KA-MANDYA'), `name`, `state`, `agmark_state`, `agmark_district`, `default_lang` ('kn'/'hi'/'mr') |
| `crops` | `code` ('ragi'), `name_en`, `agmark_name`, `msp`, `max_listing_qtl`, `min_price`, `max_price` |
| `crop_calendar` | `district_code`, `month` (1–12), `crop_code`, `rank` (1 = first) |
| `deduction_rules` | `district_code`, `transport_per_qtl`, `handling_per_qtl`, `pct_deduction` (0.0200 = 2 %), `source_note` |
| `fpos` | `id`, `name`, `district_code`, `payee_details` |
| `collection_points` | `id`, `fpo_id`, `name`, `district_code`, `geog geography(Point,4326)` |
| `farmers` | `id`, `phone` (E.164 '+9198…'), `name`, `fpo_id`, `village`, `district_code`, `geog`, `collection_point_id`, `lang`, `consent_version`, `consent_at`, `status` |
| `agents` | `id`, `fpo_id`, `name`, `phone`, `pin_hash` (bcrypt) |
| `buyers` | `id`, `org_name`, `email`, `password_hash` (bcrypt), `phone`, `status` ('APPROVED' for seeds) |
| `mandi_prices` | `district_code`, `crop_code`, `market`, `price_date`, `min_price`, `max_price`, `modal_price`, `source` ('data.gov.in'/'seed'); unique `(district_code, crop_code, market, price_date)` |
| `price_floors` | `district_code`, `crop_code`, `as_of`, `price_date`, `modal_price`, `afpp`, `basis` ('DISTRICT_FRESH'/'DISTRICT_7D'/'STATE_7D'); primary key `(district_code, crop_code, as_of)` |
| `clusters` | `id`, `code`, `collection_point_id`, `crop_code`, `status` (OPEN, READY, BIDDING, CONFIRMING, DEAL, CLOSED, NO_BID, FAILED), `total_qtl`, `listing_count`, `min_ask`, `wavg_ask`, `grade`, `bidding_ends_at`, `best_bid_id`, `version` |
| `listings` | `id`, `code`, `farmer_id`, `cluster_id`, `crop_code`, `qty_qtl`, `ask_price`, `afpp_at_listing`, `guardrail`, `source`, `session_id`, `status` |
| `verifications`, `bids`, `bid_responses`, `deals`, `call_jobs`, `call_sessions`, `triage_tickets`, `consent_log`, `dtmf_events`, `events` | Backend core only (Darshan). Read-only for Anirudh's seed and ops work. |

Reference values Anirudh must seed (`db/002_reference.sql`), with `ON CONFLICT DO NOTHING` so it can be re-run:
- Districts: `KA-MANDYA` (Mandya, Karnataka, kn) and `KA-MYSURU` (Mysuru, Karnataka, kn). Hindi is offered on the language menu for everyone.
- Crops: `ragi` (agmark "Ragi (Finger Millet)", MSP 5205), `paddy_common` (agmark "Paddy(Dhan)(Common)", MSP 2441), `maize` (agmark "Maize", MSP 2410). `max_listing_qtl` 50; price bounds ragi 1500–9000, paddy 1000–5000, maize 1000–5000 [Assumed]. The agmark spellings must be copied from a real API response (task A1), not from this line.
- Deduction rules for both districts: transport 50, handling 10, pct 0.02, note "assumed, to confirm with FPO".
- Crop calendar for both districts, month 11: ragi 1, paddy_common 2, maize 3; and the same for months 10 and 12.
- One FPO, three collection points (one placed at the venue's coordinates for the demo), two agents, two buyers with status `APPROVED`, one admin row (admin is a buyer row with email `admin@demo.test`; Darshan's auth treats that email as admin) [Assumed design to save time].

### C4. REST endpoints

All JSON, `Authorization: Bearer <jwt>` except login. Money in rupees per quintal. Times in ISO-8601 UTC. Errors are `{"error": "CODE", ...}`. Full detail: plan §6.

**Auth**

```
POST /api/auth/buyer/login   {"email":"buyer1@demo.test","password":"…"}
  200 {"token":"eyJ…","buyer":{"id":"…","org_name":"Mysuru Grain Traders","status":"APPROVED"}}
  401 {"error":"BAD_CREDENTIALS"}     429 {"error":"LOCKED"}   (5 failures → 15 min)
POST /api/auth/agent/login   {"phone":"+919800000101","pin":"1234"}
  200 {"token":"eyJ…","agent":{"id":"…","name":"Kavya","fpo_id":"…"}}
```

**Buyer**

```
GET  /api/clusters?status=OPEN,READY,BIDDING,CONFIRMING,DEAL
  200 {"clusters":[ <Cluster>, … ]}
GET  /api/clusters/{id}
  200 { <Cluster>, "lots":[{"lot_no":1,"qty_qtl":3,"ask_price":3600}, …],
        "price_ref":{"modal_price":3565,"afpp":3430,"basis":"DISTRICT_FRESH","price_date":"2026-11-12"},
        "msp":5205 }
POST /api/clusters/{id}/bids          header Idempotency-Key: <uuid>
  {"price_per_qtl":3850,"min_qty_qtl":15}
  201 {"id":"…","status":"LEADING","price_per_qtl":3850,"min_qty_qtl":15}
  200 same body when the same Idempotency-Key is replayed
  409 {"error":"BID_TOO_LOW","min_next":3810}  409 {"error":"CLUSTER_NOT_BIDDING"}  422 {"error":"MIN_QTY_TOO_HIGH"}
GET  /api/bids/mine
  200 {"bids":[{"id":"…","cluster_id":"…","price_per_qtl":3850,"min_qty_qtl":15,"status":"CONFIRMING",
               "progress":{"accepted_qtl":9,"rejected_qtl":3,"pending_qtl":12}}]}
GET  /api/deals/mine
  200 {"deals":[{"id":"…","cluster_id":"…","qty_qtl":17,"price_per_qtl":3850,"gross_value":65450,
                "platform_fee":981.75,"status":"CONFIRMED","pickup_by":"2026-11-16",
                "fpo":{"name":"Keregodu FPO","payee_details":"UPI keregodu-fpo@bank"}}]}
POST /api/deals/{id}/payment-reported   {"payment_ref":"UTR123456"}   200 {"status":"PAYMENT_REPORTED"}
```

`<Cluster>` (identical in REST and WebSocket):

```json
{"id":"7f0c…","code":104,"crop_code":"ragi","crop_name":"Ragi","district":"Mandya",
 "collection_point":{"name":"Keregodu FPO yard","lat":12.63,"lon":76.92},
 "status":"BIDDING","total_qtl":24.0,"listing_count":8,"min_ask":3600,"wavg_ask":3742,
 "grade":"A","photo_url":"/media/v/7f0c.jpg","bidding_ends_at":"2026-11-13T12:30:00Z",
 "best_bid":{"price_per_qtl":3800,"mine":false},"version":12}
```

`best_bid` is `null` when there is no bid; `grade` and `photo_url` are `null` before verification.

**Agent**

```
GET  /api/agent/tasks
  200 {"verify":[ <Cluster>… status READY ],
       "tickets":[{"id":"…","village":"Keregodu","first_name":"Ramesh","reason":"IVR_FAIL_3",
                   "status":"OPEN","created_at":"…"}],
       "deals":[{"id":"…","cluster_code":104,"status":"PAYMENT_REPORTED","qty_qtl":17,"gross_value":65450}]}
POST /api/agent/clusters/{id}/verification     multipart/form-data
  fields: photo (image/jpeg ≤ 2 MB), grade (A|B|C|REJECT), moisture_pct (optional), lat, lon, accuracy_m, captured_at
  201 {"cluster_id":"…","status":"BIDDING","bidding_ends_at":"…"}
  422 {"error":"TOO_FAR","distance_m":1840}  422 {"error":"STALE_CAPTURE"}  422 {"error":"LOW_ACCURACY"}  409 {"error":"ALREADY_VERIFIED"}
POST /api/agent/triage/{id}/claim              200 {"status":"ASSIGNED"}
POST /api/agent/triage/{id}/bridge             200 {"verbal_code":"55","mode":"simulated"}   409 {"error":"CODE_USED"}
POST /api/agent/deals/{id}/payment-confirmed   200 {"status":"PAID"}
```

**Admin and ops** (admin token)

```
POST /api/admin/clusters/{id}/close-auction    200 {"status":"CONFIRMING"}
POST /api/admin/prices/refresh                 200 {"floors_written":6}
GET  /api/ops/calls
  200 {"sessions":[{"phone_masked":"+91•••••2345","kind":"LISTING","state":"PRICE","provider":"sim",
                    "version":7,"updated_at":"…"}],
       "jobs":[{"id":"…","kind":"BID_OFFER","status":"QUEUED","attempts":1,"run_at":"…"}],
       "breaker":{"calls_today":14,"budget":200}}
GET  /api/ops/dtmf?limit=50
  200 {"events":[{"session_id":"…","state_before":"QTY","digits":"3","state_after":"QTY_CONFIRM",
                  "dropped_reason":null,"at":"…"}]}
POST /api/ops/chaos/flush-redis                200 {"ok":true}      (DEMO_MODE only)
GET  /health
  200 {"db":"ok","redis":"ok","tts_clips":220,"price_age_days":0,"provider":"sim","public_base_url_ok":true}
```

### C5. Dashboard WebSocket events

`GET {VITE_WS_BASE}/ws?token=<jwt>&since=<seq>`. Server sends only. Each message: `{"seq":1042,"type":"…","payload":{…}}`. On connect the server replays rows with `seq > since` (max 500, else it sends `{"type":"resync"}` and the client reloads with REST). Delivery is at-least-once: clients drop any `seq` they have seen, and keep a cluster only if the incoming `version` is higher.

| type | audience | payload |
|---|---|---|
| `cluster.updated` | all | `<Cluster>` |
| `listing.created` | all | `{"cluster_id","crop_code","qty_qtl","ask_price","source"}` |
| `bid.placed` | buyer | `{"cluster_id","bid_id","price_per_qtl","buyer_is_you"}` |
| `bid.confirming` | buyer | `{"cluster_id","bid_id","accepted_qtl","rejected_qtl","pending_qtl"}` |
| `bid.failed` | buyer | `{"cluster_id","bid_id","accepted_qtl","min_qty_qtl"}` |
| `deal.created` | buyer, agent | `{"deal_id","cluster_id","qty_qtl","price_per_qtl","gross_value","platform_fee","pickup_by"}` |
| `deal.updated` | buyer, agent | `{"deal_id","status"}` |
| `task.created` | agent | `{"kind":"VERIFY"|"TRIAGE","ref_id"}` |
| `call.state` | admin | `{"phone_masked","kind","state","provider"}` |

### C6. Simulator phone WebSocket protocol

`{VITE_WS_BASE}/tel/sim/ws?phone=%2B919845012345` (one socket per simulated phone; no token: DEMO_MODE only).

| Direction | JSON |
|---|---|
| client → server | `{"t":"missed_call"}` |
| server → client | `{"t":"ring","call_id":"sim-17"}` (after 1–3 s) |
| client → server | `{"t":"answer","call_id":"sim-17"}` |
| server → client | `{"t":"play","call_id":"sim-17","audio_url":"/audio/mix/ab12….wav","max_digits":1,"finish_on_key":"","timeout_s":6,"state":"CROP"}` |
| client → server | `{"t":"digit","call_id":"sim-17","d":"1","ts_ms":1731480000123,"seq":4}` (one per keypress) |
| client → server | `{"t":"timeout","call_id":"sim-17","seq":5}` (client sends this `timeout_s` seconds after the audio ends with no complete input) |
| server → client | `{"t":"hangup","call_id":"sim-17"}` |
| client → server | `{"t":"hangup","call_id":"sim-17"}` (user pressed red key) |

Rules: `audio_url` is relative to `VITE_API_BASE`. Every `play` replaces the previous one (stop old audio). The server collects digits until `max_digits` or `finish_on_key`; the client just sends every key. "Inject bounce" switch: the client sends each digit twice, the second 30–60 ms later with a new `seq`. "Drop call" switch: the client closes the socket without sending `hangup` and reconnects 2 s later (the phone is then idle).

### C7. Exotel webhooks and App Bazaar flow

All under `{PUBLIC_BASE_URL}/tel/exotel/{WEBHOOK_SECRET}/` (secret in the path, because Exotel documents no webhook signature).

| Exotel feature | Our URL | Method | We return |
|---|---|---|---|
| ExoPhone missed-call webhook | `/missed` | POST form: `CallSid, From, To, Status` | `200 {"ok":true}` always |
| Gather applet *k* (dynamic URL) | `/gather?step=k` | GET, query includes `CallSid`, `CallFrom` | `200 {"gather_prompt":{"audio_url":"https://…/audio/mix/x.wav"},"max_input_digits":1,"finish_on_key":"#","input_timeout":6}` |
| Passthru applet *k* | `/digits?step=k` | GET, query includes `CallSid`, `digits` (wrapped in literal `"`) | `200` continue to Gather *k+1*; `404` end call |
| Outbound call StatusCallback | `/status` | POST form | `200` |

Flow in App Bazaar, named `annadata-ivr`: `Gather(step=1) → Passthru(step=1) → Gather(step=2) → Passthru(step=2) → … → Gather(step=12) → Passthru(step=12) → Hangup`. Each Passthru's failure branch → Hangup. Its App ID becomes `EXOTEL_APP_ID`. The outbound call is `POST https://api.exotel.com/v1/Accounts/{sid}/Calls/connect.json` with `From=<farmer>&CallerId=<exophone>&Url=http://my.exotel.com/{sid}/exoml/start_voice/{app_id}&CallType=trans&TimeLimit=240&TimeOut=30&StatusCallback=<status url>`. **The exact applet behaviour is unconfirmed** because Exotel's two Passthru documents disagree (plan §16, risk 1); task N6 + D7 resolve it.

### C8. IVR state names and audio clip ids

States (plan §5.4, trimmed): `LANG`, `CONSENT`, `MAIN`, `CROP`, `QTY`, `QTY_CONFIRM`, `PRICE`, `GUARD`, `FINAL`, `DONE`, `HELP`, `BYE`, `NOT_REGISTERED`, `OFFER`, `OFFER_CONFIRM`, `DONE_OFFER`. Terminal: `DONE`, `DONE_OFFER`, `HELP`, `BYE`, `NOT_REGISTERED`.

Clip ids (each exists as `audio/kn/<id>.wav` and `audio/hi/<id>.wav`, 8000 Hz, mono, 16-bit PCM). A clip id may be written `hi:<id>` to force the Hindi file inside a Kannada prompt (used only by the language menu). English meaning, which Hitesh translates:

| Clip id | English meaning |
|---|---|
| `welcome` | "Welcome to Annadata Dhwani." |
| `lang_option` | kn file: "For Kannada, press 1." hi file: "Hindi ke liye 2 dabaiye." |
| `consent` | "We will save your name, phone number, village and the crops you list, to find buyers for you. We do not record this call. Press 1 to agree, or 2 to exit." |
| `main_menu` | "You already have a crop listed. Press 1 to list a new crop. Press 0 for a helper." |
| `crop_menu_intro` | "Which crop do you want to sell?" |
| `cropkey_ragi_1`, `cropkey_ragi_2`, `cropkey_ragi_3` | "For ragi, press 1." / "…press 2." / "…press 3." |
| `cropkey_paddy_common_1..3`, `cropkey_maize_1..3` | Same for paddy and maize |
| `helper_key_0` | "For a helper, press 0." |
| `crop_ragi`, `crop_paddy_common`, `crop_maize` | "Ragi." / "Paddy." / "Maize." |
| `ask_qty` | "How many quintals? One quintal is one hundred kilos. Type the number, then press hash." |
| `you_entered` | "You entered" |
| `qty_1` … `qty_50` | "one quintal" … "fifty quintals" (50 clips) |
| `confirm_1_2` | "If correct, press 1. To enter again, press 2." |
| `mandi_price_was` | "The mandi price in your district was" |
| `fair_price_is` | "The fair price at your village is" |
| `rupees_per_qtl` | "rupees per quintal." |
| `no_price_today` | "No mandi price is available today." |
| `ask_price` | "Type your price per quintal in rupees, then press hash." |
| `guard_warn` | "Your price is below the fair price of" |
| `guard_options` | "To raise your price to the fair price, press 1. To keep your price, press 2. To type again, press 3." |
| `final_intro` | "You are listing" |
| `at_price` | "at a price of" |
| `final_confirm` | "To confirm, press 1. To start again, press 2." |
| `listed_ok` | "Your crop is listed." |
| `your_number_is` | "Your listing number is" |
| `will_call` | "We will call you when a buyer makes an offer. Goodbye." |
| `welcome_back` | "Welcome back. Let us continue where you stopped." |
| `bad_input` | "Sorry, that was not valid." |
| `already_listed` | "You already have this crop listed." |
| `bye` | "Thank you. Goodbye." |
| `helper_will_call` | "A helper from your FPO will call you." |
| `helper_code_is` | "Only talk to a helper who tells you this code:" |
| `not_registered` | "This number is not registered with your FPO." |
| `offer_intro` | "Good news. A buyer offers" |
| `for_your` | "for your" |
| `your_ask_was` | "Your asking price was" |
| `offer_options` | "To accept, press 1. To reject, press 2. To hear again, press 9." |
| `offer_confirm` | "You are accepting this offer. To confirm, press 1. To go back, press 2." |
| `offer_done` | "Accepted. Your FPO will tell you the pickup day. Goodbye." |
| `offer_rejected` | "You rejected the offer. Your crop stays listed. Goodbye." |
| `d_0` … `d_9` | "zero" … "nine" (10 clips) |

Numbers other than quantity are spoken digit by digit (`3430` → `d_3 d_4 d_3 d_0`). That removes all dynamic TTS from the 24-hour build.

### C9. Python module interfaces

```python
# backend/app/services/pricing.py   (Anirudh)
async def get_floor(pool, redis, district_code: str, crop_code: str) -> dict | None:
    """Returns {"modal_price": 3565.0, "afpp": 3430, "basis": "DISTRICT_FRESH",
                "price_date": "2026-11-12"} or None. Never raises; never calls the internet."""
def compute_afpp(modal: float, pct_deduction: float, transport: float, handling: float) -> int:
    """floor to 10 of modal*(1-pct) - transport - handling"""

# backend/app/services/audio.py     (Hitesh)
def digit_clips(n: int) -> list[str]            # 3430 -> ["d_3","d_4","d_3","d_0"]
def mix(clips: list[str], lang: str) -> str     # returns sha; writes audio/mix/{sha}.wav if absent
def mix_url(clips: list[str], lang: str, base_url: str) -> str   # f"{base_url}/audio/mix/{sha}.wav"
def missing_clips(clip_ids: list[str], langs: list[str]) -> list[str]
```

`pool` is an `asyncpg.Pool`, `redis` a `redis.asyncio.Redis`. Both are passed in; the modules never create their own connections.

### C10. Redis keys

As plan §5.2, unchanged: `sess:{phone}` (1800 s), `callmap:{provider}:{call_id}` (3600 s), `evt:{call_id}:{event_id}` (3600 s), `lock:call:{phone}` (300 s), `dtmf:last:{call_id}` (5 s), `rl:cb:{phone}:10m` (600 s), `rl:cb:{phone}:day` (86400 s), `budget:calls:{yyyymmdd}` (172800 s), `miss:{phone}` (20 s), `fail:{phone}` (86400 s), `floor:{district}:{crop}` (93600 s; value is the JSON returned by `get_floor`), `rl:login:{id}` (900 s), channel `ad:events`. **Only Anirudh's `pricing.py` writes `floor:*`; everything else is Darshan's.**

### C11. Mock server and fixtures

`mock/mock_server.py` (Darshan, ready by H2), run with `python mock/mock_server.py` on port 8001. It:
- serves every C4 endpoint from `contracts/fixtures/*.json` (any login succeeds; `POST …/bids` returns 201 the first time per `Idempotency-Key` and 200 after, and 409 `BID_TOO_LOW` if the price is not above the fixture's best bid + 10);
- serves the C5 WebSocket with replay by `since`, and emits a scripted story every 5 s: `listing.created` → `cluster.updated` (17 → 20 qtl, READY) → `cluster.updated` (BIDDING) → `bid.placed` → `bid.confirming` ×3 → `deal.created`;
- serves the C6 simulator socket with a scripted call: `ring` → `play` (CROP) → after any digit `play` (QTY) → … → `hangup`, using `contracts/fixtures/sample.wav`;
- accepts the verification multipart and returns 201 (or 422 `TOO_FAR` when `lat` is 0).

Fixtures: `clusters.json` (5 clusters across all statuses), `cluster_detail.json`, `bids_mine.json`, `deals_mine.json`, `agent_tasks.json`, `ops_calls.json`, `ops_dtmf.json`, `events_story.json`, `health.json`, `sample.wav`.

---

## 4. Per-person sections

Columns: ID | Task | Tag | Why this owner | What is included | Inputs | Done when | Hours | Depends on | Backup.

### 4.1 Darshan: backend core and integration

**Vertical and jury moment.** The state machine, its recovery and its concurrency guarantees. The jury sees a dropped call resume, keypad bounce dropped, a Redis flush survived, a double-clicked bid recorded once, and two farmers' keypresses closing a deal.

| ID | Task | Tag | Why this owner | What is included | Inputs | Done when | Hrs | Depends on | Backup |
|---|---|---|---|---|---|---|---|---|---|
| D1 | Repo, contracts as code, mock server, frontend shell | [CLAUDE-CODE] | Every other task depends on it; multi-file | **By H1:** GitHub repo, invite the other 3; C1 folders; `.env.example` (C2); `contracts/fixtures/*.json`, `clip_ids.txt`, `states.md`; Vite + React + TS + Tailwind shell with routes `/login /buyer /sim /agent /ops`, `src/lib/api.ts` (fetch wrapper with token and `VITE_API_BASE`), placeholder pages. **By H2:** `docker-compose.yml`; `db/001_schema.sql` (plan §5.1); `mock/mock_server.py` per C11; README "run in 5 commands"; ngrok account and static domain on the demo laptop (only Darshan can, his laptop) | This document | `docker compose up -d` + schema loads; `npm run dev` shows 5 routes; mock server answers every C4 path and both sockets | 2.0 | — | Anirudh |
| D2 | Call engine + LISTING flow + simulator adapter | [CLAUDE-CODE] | Critical path, state machine | `engine/actions.py`, `engine/engine.py`, `engine/flows.py` with states `LANG…DONE`, `HELP`, `BYE`, `NOT_REGISTERED` per C8 and plan §5.4 (retries max 2, 3rd → BYE, `#` or timeout ends multi-digit, 240 s cap); `telephony/sim.py` implementing C6; `scripts/sim_client.py` (Python test caller that walks a full listing); pricing via a stub until A3 merges | C6, C8 | `sim_client.py` completes a listing; unit table test for every state passes | 4.0 | D1 | Hitesh |
| D3 | Reliability layer | [CLAUDE-CODE] | Concurrency and failure semantics | `lua/session_cas.lua`, `allow_callback.lua`, `release_lock.lua` (plan §5.3); Redis → `call_sessions` checkpoint and rehydrate; `evt:` idempotency; `engine/debounce.py` (120 ms same digit, 40 ms any); `miss:` dedupe; rate limits 3/10 min, 6/day; `fail:` counter → `triage_tickets` row with random 2-digit code and `HELP` prompt that speaks it; `consent_log` and `dtmf_events` writes; `/api/ops/chaos/flush-redis` | D2 | Tests: duplicate event applied once; FLUSHALL mid-call then next digit continues; bounce input stores 3 not 33; 3 failed calls → 1 ticket | 2.0 | D2 | Hitesh |
| D4 | Clustering + events outbox + WebSocket hub | [CLAUDE-CODE] | Transactional, race-prone | `services/clustering.py` `commit_listing` with advisory lock and `recompute_cluster` (plan §7.5, 20 qtl → READY + `task.created`); `services/events.py` (insert in transaction, publish `ad:events` after commit); `api/ws.py` with `since` replay, 2 s poll fallback, audience filter; **minimal REST for CP2:** buyer login, `GET /api/clusters`, `GET /api/clusters/{id}`; merge A3 `pricing.py` and H4 `audio.py` into the engine | A3, H4 | 50 concurrent commits → 1 cluster, correct total; a sim listing appears on two dashboard tabs in < 1 s | 2.0 | D3, A3, H4 | Anirudh |
| D5 | Auth + REST API | [CLAUDE-CODE] | Security-sensitive, many files | JWT (HS256, 12 h), bcrypt, login lockout, agent and admin login; every remaining C4 endpoint against real tables, number masking (no phone in any buyer/agent response); verification endpoint with PostGIS distance ≤ 500 m, ≤ 10 min old, accuracy ≤ 200 m, photo saved to `media/v/`; tickets GET/claim/bridge (simulated bridge returns code once); deal payment buttons; ops endpoints; `/health`; serve `audio/` and `media/` and `frontend/dist` | D4 | Auth matrix test (buyer/agent/admin/anon) passes; JSON scan finds no 10-digit number; frontend switched from mock to real at CP2 works | 2.0 | D4 | Nahyan |
| D6 | Bidding + call-job queue + BID_OFFER flow | [CLAUDE-CODE] | Hardest concurrency; double-accept risk | `services/bidding.py`: `place_bid` (row lock, ≥ min_ask, ≥ best+10, Idempotency-Key), auto close at `bidding_ends_at` (180 s demo) and admin close, `record_response` first-write-wins, `resolve_round` (deal if accepted ≥ min_qty, else FAILED → BIDDING once → NO_BID; non-accepting lots re-pooled); `services/jobs.py`: `call_jobs` claim with `SKIP LOCKED`, 5 concurrent, retries 2/10/30 min (demo: 20/40/60 s), `lock:call:{phone}`, daily budget; flows `OFFER`, `OFFER_CONFIRM`, `DONE_OFFER`; sim adapter "incoming call" for bid offers | D5 | 20 parallel bids → 1 LEADING; replayed key → 1 bid; 8 lots, 5 accept → deal of their quantity; same lot accepted twice → 1 row | 3.0 | D5 | Nahyan |
| D7 | Exotel adapter + live spike | [CLAUDE-CODE] | Needs engine internals | `telephony/exotel.py` (C7): secret check, `callmap` check, quote-stripping of `digits`, 404 on terminal; `place_call` via connect API; status callback → job done/retry; switch with `TELEPHONY_PROVIDER`; run the spike with Nahyan: confirm the 4 unknowns in plan §7.1 step 3 and adapt in place | N1, N6, D6 | A whitelisted button phone gives a missed call and completes a listing and a bid acceptance | 1.5 | D6, N6 | Nahyan |
| D8 | Integration, reviews, merges | [CLAUDE-CODE] | Owner of shared interfaces | Review and merge every PR that touches C1–C11; run the full test suite after each merge; lead CP1, CP2, CP3 (15 min each) | PRs | `main` is green at each checkpoint | 1.5 | — (spread) | Anirudh |
| D9 | Freeze build | [CLAUDE-CODE] | | `scripts/demo_reset.py` (wipes and reseeds in 10 s), final E2E on sim and Exotel, tag `v-demo` at H19 | All | Acceptance list in §9 runs green twice | 0.5 | CP3 | Nahyan |
| D10 | Rehearsals and blocker fixes | [CLAUDE-CODE] | | 2 full rehearsals with failure injection; fix only blockers found; hand the backup laptop its final `git pull` | D9 | Two clean runs | 2.0 | D9 | — |

**Tools and free services:** Claude Code (with subagents for tests), Docker Desktop, Postgres/PostGIS, Valkey, Python 3.12, ngrok free (static domain), GitHub.
**Risks and if blocked:** engine overrun (> H7) → drop CONSENT and MAIN states (first-call language only) and keep going; Exotel behaviour unlike the docs → stop at 45 minutes and declare the phone leg simulated (the simulator is the demo); laptop failure → backup laptop (N8) has the repository.

### 4.2 Nahyan: buyer marketplace and real phone line

**Vertical and jury moment.** The buyer side and the real phone. The jury watches clusters fill live, two buyers outbid each other, the confirmation bar fill as farmers press keys, and a real ₹1,000 phone ring back after a missed call.

| ID | Task | Tag | Why this owner | What is included | Inputs | Done when | Hrs | Depends on | Backup |
|---|---|---|---|---|---|---|---|---|---|
| N1 | Exotel trial account | [MANUAL-GUI] | Needs a person, ID and phone; part of his phone vertical | Sign up at exotel.com (trial: 7 days, ₹500 credit, 10 whitelisted numbers); whitelist the 4 team phones and the demo button phone; note the trial ExoPhone; enable **Missed call** mode on that ExoPhone; copy Account SID, API key, API token; send them to Darshan in a private DM (never in the group or Git); write `docs/exotel_setup.md` with screenshots | Team phone numbers | Darshan has the 5 values; a call to the ExoPhone from a whitelisted phone is cut after 1–2 rings with no answer | 1.0 | — | Hitesh |
| N2 | Buyer dashboard: list and detail | [GEMINI-OK] | Bounded UI against fixed contract | `src/routes/Buyer.tsx`, `src/components/buyer/ClusterList.tsx`, `ClusterDetail.tsx`: status filter chips, crop filter, cards (crop, tonnage, lots, min/avg ask, grade badge, countdown, best bid), detail with lot table, photo, price reference (mandi modal, AFPP, MSP), "demo data" label | C4, fixtures, mock server | Against the mock, all 5 fixture clusters render, filters work, countdown ticks | 3.0 | D1 | Anirudh |
| N3 | Map + live events hook | [GEMINI-OK] | Bounded, contract-defined | `src/components/buyer/ClusterMap.tsx` (react-leaflet, OSM tiles with attribution, marker per collection point sized by tonnage, hides itself on tile error); `src/lib/ws.ts` `useEvents()` per C5 (since/seq in localStorage, drop seen seq, backoff 1→15 s, `resync` → refetch); cluster store merge by `version` | C5, mock WS | Mock story plays on screen; Wi-Fi off 20 s then on → no duplicates, state matches REST | 2.5 | N2 | Anirudh |
| N4 | Bidding, confirmation, deal views | [GEMINI-OK] | Bounded UI | `BidForm.tsx` (price + min qty, `crypto.randomUUID()` per attempt reused on retry, shows 409/422 messages, button disabled while sending), `ConfirmProgress.tsx` (accepted/rejected/pending bar from `bid.confirming`), `DealCard.tsx` (qty, price, gross, 1.5 % fee, FPO payee, payment-reference input → POST) | C4, C5 | Double-click sends one key; BID_TOO_LOW shows `min_next`; mock story ends on a deal card | 3.0 | N3 | Anirudh |
| N5 | Switch to real backend at CP2 | [GEMINI-OK] | His screens | Set `VITE_API_BASE`/`VITE_WS_BASE` to :8000, log in as a seeded buyer, list every mismatch with the contract in the group, fix his side | D5 | Real listing from the simulator appears on his dashboard (bidding screens re-checked against real backend at CP3) | 1.0 | D4, CP2 | Darshan |
| N6 | Exotel App Bazaar flow | [MANUAL-GUI] | Dashboard clicking | Build flow `annadata-ivr` exactly as C7 (12 Gather + 12 Passthru + Hangup) using `{PUBLIC_BASE_URL}` from Darshan; set the missed-call webhook URL; set the flow as the ExoPhone's app; record App ID → Darshan; screenshot every applet into `docs/exotel_setup.md` | C7, ngrok URL, secret | Flow saved; App ID sent; a test call from the dashboard reaches our `/gather?step=1` (seen in Darshan's log) | 2.0 | N1, D1 | Hitesh |
| N7 | Real phone tests with Darshan | [MANUAL-GUI] | Physical phones | During D7: 5 full listings from the button phone, 1 bid acceptance, 1 dropped call (pull the battery after QTY) and resume; prepaid balance check before/after a missed call on 2 operators; log every run (time, result, latency to callback) in `docs/exotel_setup.md` | D7 | ≥ 4 of 5 runs clean, results logged | 2.5 | D7 | Hitesh |
| N8 | Backup laptop | [MANUAL-GUI] | Removes the single laptop risk | On his laptop: install Docker Desktop, Python 3.12, Node 20, FFmpeg; clone; run README; load seed; run the whole demo on `sim` with Wi-Fi off; write `docs/backup_laptop.md` (exact commands, where `.env` lives) | README, D5 | The full demo script runs offline on his laptop | 2.0 | CP2 | Anirudh |
| N9 | Demo rehearsal: buyer operator | [MANUAL-GUI] | Owns the buyer screens | Operate both buyer laptops in 2 rehearsals (bid, outbid, double-click), switch to backup laptop on cue, answer buyer/market questions | Demo script | Two clean runs | 2.0 | D9 | Anirudh |

**Tools:** Gemini 3.1 Pro in AI Chat for single files; Antigravity agent for the `components/buyer/` folder (save the Opus credits for one integration bug at N5). Free: Exotel trial, OpenStreetMap tiles, Leaflet, GitHub.
**Risks:** Exotel signup blocked or OTP not arriving → tell Darshan at once; contingency is "phone leg simulated" (no code change); map tiles blocked at the venue → map hides itself, list still works.

### 4.3 Hitesh: voice and network physics

**Vertical and jury moment.** What the farmer hears. The jury hears 8 kHz band-limited Kannada prompts, sees the simulator phone with "inject key bounce" and "drop call", and Hitesh explains narrowband audio and why digits are read back.

| ID | Task | Tag | Why this owner | What is included | Inputs | Done when | Hrs | Depends on | Backup |
|---|---|---|---|---|---|---|---|---|---|
| H1 | Bhashini account and test call | [MANUAL-GUI] | Account task in his vertical | Register at bhashini.gov.in (ULCA), verify email, generate API key, note user ID; find the TTS pipeline ID in the Bhashini API docs; one test TTS call each for `kn` and `hi` with `curl` or Python; if no working key by **H3**, decide edge-tts and tell the group | — | A Kannada WAV and a Hindi WAV saved from Bhashini, or the edge-tts decision announced | 1.0 | — | Anirudh |
| H2 | `prompts.yaml` in Kannada and Hindi | [GEMINI-OK] + human review | Content | Every C8 clip id with `en`, `kn`, `hi` text; Gemini drafts; a native speaker on the team (or a friend by phone) reviews every Kannada and Hindi line [Assumed someone is available]; keep each line under 12 words; `qty_1…qty_50` and `d_0…d_9` written out | C8 | File has all ids (check with `clip_ids.txt`), reviewed lines marked `reviewed: true` | 3.0 | — | Anirudh |
| H3 | `prewarm_audio.py` and generation | [GEMINI-OK] | One script | Read `prompts.yaml`; for each lang and id: skip if WAV and matching `.sha` exist; synthesise via Bhashini (or edge-tts `kn-IN-SapnaNeural` / `hi-IN-SwaraNeural`); FFmpeg `highpass=f=300,lowpass=f=3400,loudnorm=I=-16:TP=-3:LRA=7`, `-ar 8000 -ac 1 -c:a pcm_s16le`; write `audio/{lang}/{id}.wav`; print a summary; `--engine edge` flag | H1, H2 | About 220 files; `ffprobe` on 10 random files shows 8000 Hz, mono, s16 | 3.0 | H2 | Anirudh |
| H4 | `audio.py` mixer module | [GEMINI-OK] | One module with fixed interface (C9) | `digit_clips`, `mix`, `mix_url`, `missing_clips`; concatenate with Python `wave`, 150 ms silence between clips, `hi:` prefix support, sha256 of `lang|clip ids` as filename, atomic write (temp file + rename); `backend/tests/test_audio.py` | C9 | Tests pass; 6-clip mix in < 50 ms on second call | 1.5 | H3 | Darshan |
| H5 | Simulator phone page | [GEMINI-OK] | One page against C6; he owns audio | `src/routes/Sim.tsx`, `components/sim/Keypad.tsx`, `PhoneScreen.tsx`: phone selector (seeded farmers from a small JSON in the page), green "missed call" button, ringing state with answer button, 3×4 keypad sending C6 `digit` with `ts_ms` and `seq`, WebAudio DTMF tones (two sine waves per key, 100 ms), audio playback of `audio_url` (stop previous), timeout timer, switches "inject bounce" and "drop call", a log panel of messages; two phones side by side | C6, mock server | Against the mock the scripted call runs; with bounce on, every key is sent twice 30–60 ms apart | 4.0 | D1 | Darshan |
| H6 | Handset and noise test | [MANUAL-GUI] | Physical, his vertical | Play 10 mixed prompts (quantity + price readbacks) through a phone call to a teammate's button phone (or the Exotel test call) in a noisy room; the listener writes what they hear; adjust gain/filters and regenerate if < 10/10; record results in `docs/audio_tests.md` | H3, H4 | 10/10 numbers heard correctly | 1.5 | H4 | Anirudh |
| H7 | Backup demo video | [MANUAL-GUI] | Media | Screen + phone recording of the full demo script (plan §10.3) after CP3; 3 minutes; subtitles for Kannada audio; saved on 2 laptops and a USB stick | CP3 | Video plays offline on both laptops | 2.0 | CP3 | Nahyan |
| H8 | Jury Q&A pack: voice and network | [GEMINI-OK] | His topic | One page of answers for plan §14 Q1–Q3, Q7 in his own words; rehearse aloud with Darshan for 15 minutes | Plan §14 | Can answer each in < 45 s without notes | 1.5 | — | Darshan |
| H9 | Demo rehearsal: phone handler | [MANUAL-GUI] | Owns phone + simulator | In 2 rehearsals: handle the button phone on speaker; on cue switch to the simulator tab; trigger bounce and drop switches | Demo script | Two clean runs | 2.0 | D9 | Nahyan |

**Tools:** Gemini AI Chat for `prompts.yaml` drafts and the two Python files; Antigravity for `components/sim/`. Free: Bhashini (proof-of-concept use), edge-tts (fallback), FFmpeg, Python `wave`.
**Risks:** Bhashini key not working by H3 → edge-tts and say so on the slide; no native reviewer → ship Kannada for the prompts that were reviewed and Hindi for the rest, and say so; FFmpeg not installed on Windows → `winget install Gyan.FFmpeg`.

### 4.4 Anirudh: markets, field and story

**Vertical and jury moment.** Price transparency and the trust layer. The jury hears yesterday's real mandi price and the fair floor in the call, watches the FPO agent verify a cluster with a live photo and location on a phone, sees the ops screen, and Anirudh presents the unit economics.

| ID | Task | Tag | Why this owner | What is included | Inputs | Done when | Hrs | Depends on | Backup |
|---|---|---|---|---|---|---|---|---|---|
| A1 | data.gov.in key and real samples | [MANUAL-GUI] | Account task in his vertical | Register on data.gov.in, get a personal API key, send to Darshan privately; call resource `9ef84268-d588-465a-a308-a864a43d0070` for Karnataka / Mandya and Mysuru / ragi, paddy, maize; save raw JSON to `contracts/fixtures/agmark_*.json`; copy the exact commodity spellings into C3 seed | — | Raw responses saved; exact `agmark_name` strings known | 0.5 | — | Hitesh |
| A2 | Reference seed SQL | [GEMINI-OK] | Bounded SQL against C3 | `db/002_reference.sql`: districts, crops, deduction_rules, crop_calendar (months 10–12), 1 FPO with `payee_details`, 3 collection points (one at the venue's lat/lon), 2 agents and 2 buyers and admin with bcrypt hashes of `SEED_PASSWORD` (generate hashes with a 3-line Python script), all `ON CONFLICT DO NOTHING` | C3, A1 | Loads twice on the schema without error | 2.0 | A1, D1 | Hitesh |
| A3 | Price ingestion + AFPP + `pricing.py` | [GEMINI-OK] | Two files, fixed interface | `scripts/ingest_prices.py`: for each district × crop fetch today (3 retries, 10 s timeout), upsert `mandi_prices`, compute floor with the fallback chain (fresh ≤ 2 days → 7-day district median → state median from the same call), drop modals > 40 % from the 7-day median, upsert `price_floors`, set `floor:*` in Redis; `--from-fixtures` mode; `services/pricing.py` per C9; `tests/test_pricing.py` (3565 → 3430) | C3, C9, A1 | Real run writes floors for 6 pairs; tests pass; `get_floor` returns None (not an error) when nothing is stored | 4.0 | A2 | Darshan |
| A4 | Demo seed script | [GEMINI-OK] | Bounded script | `scripts/seed_demo.py`: 40 farmers (team phones as 4 of them, `+91` format) with coordinates 0.5–4 km around the 3 collection points; one ragi cluster at a collection point with 6 listings totalling 17 qtl; one paddy cluster `BIDDING`; 7 days of `mandi_prices` history (`source='seed'`); `--reset` truncates marketplace tables; uses SQL that matches C3 exactly | C3, A2 | Dashboard (mock off) shows the seeded clusters; rerun is safe | 2.0 | A3 | Hitesh |
| A5 | FPO agent PWA | [GEMINI-OK] | Bounded UI against C4 | `src/routes/Agent.tsx`, `components/agent/TaskList.tsx`, `VerifyCapture.tsx`, `TicketList.tsx`, `DealConfirm.tsx`: agent login (phone + PIN); tasks from `/api/agent/tasks`; verify: live camera via `getUserMedia({video:{facingMode:"environment"}})`, capture to canvas, JPEG 0.7, geolocation with `enableHighAccuracy`, grade buttons A/B/C/Reject, optional moisture, multipart POST, show `TOO_FAR` with distance; no file picker; tickets: claim, "call farmer" shows the code big; deals: "payment received" button; `vite-plugin-pwa` manifest; large touch targets | C4, mock | Against the mock: capture, upload and both error messages work on a real Android phone. At CP3 against the real backend: a verification at the venue succeeds and a faked far location gets `TOO_FAR` | 4.0 | D1 | Nahyan |
| A6 | Ops monitor page | [GEMINI-OK] | Bounded UI | `src/routes/Ops.tsx`: polls `/api/ops/calls` and `/api/ops/dtmf` every 1 s, `/health` every 5 s; panels: live sessions (state badge, version), job queue, breaker gauge, DTMF log with `BOUNCE` rows in red, health lights; a "Flush Redis" button (POST chaos endpoint) with confirm | C4 | Against the mock all panels render; against real backend the flush button works | 2.0 | A5 | Nahyan |
| A7 | Acceptance and chaos test run | [MANUAL-GUI] | Fresh eyes, not the builder | Run the §9 checklist and the failure-injection list (plan §13.4, trimmed) on the frozen build; file each failure in the group as `BUG <step> <expected> <saw>` | CP3 | Every item marked pass/fail with notes | 1.5 | CP3 | Hitesh |
| A8 | Pitch deck and economics | [GEMINI-OK] | Story | 6 slides: problem with sourced numbers (plan §11, §14 Q13 wording), how it works (one diagram), live demo cue, engineering proof (failure demos), unit economics (plan §11.2–11.4), "what is real, what is simulated, what costs money" (plan §10.1); `docs/deck.pdf` | Plan §10, §11, §14 | Deck reviewed by Darshan | 2.0 | — | Hitesh |
| A9 | Demo rehearsal: agent and slides | [MANUAL-GUI] | Owns PWA and deck | Operate the agent phone (verification), drive slides, answer price, economics and legal questions | Demo script | Two clean runs | 2.0 | D9 | Nahyan |

**Tools:** Gemini AI Chat for the SQL and the two Python files; Antigravity for `components/agent/`. Free: data.gov.in API, PostGIS, `vite-plugin-pwa`, Google Slides or LibreOffice Impress.
**Risks:** data.gov.in down or empty → `--from-fixtures` with the A1 samples, spoken basis "this week"; camera blocked on HTTP → open the PWA only through the ngrok HTTPS URL; phone GPS weak indoors → accuracy limit is 200 m; demo collection point is placed at the venue.

---

## 5. Dependency graph and critical path

```mermaid
flowchart LR
  D1["D1 repo, contracts, mock<br/>H0–2"]:::crit --> D2["D2 engine + sim adapter<br/>H2–6"]:::crit
  D2 --> D3["D3 reliability<br/>H6–8"]:::crit --> D4["D4 clustering + WS<br/>H8–10"]:::crit
  D4 --> CP2{{"CP2 H10"}}:::crit --> D5["D5 auth + REST<br/>H10–12"]:::crit --> D6["D6 bidding + queue<br/>H12–15"]:::crit
  D6 --> D7["D7 Exotel adapter<br/>H16.5–18"] --> CP3{{"CP3 H18"}}:::crit
  D6 --> CP3
  CP3 --> D9["D9 freeze H19"]:::crit --> D10["D10 rehearsals<br/>H19–24"]:::crit

  A1["A1 key"] --> A2["A2 seed SQL"] --> A3["A3 prices + pricing.py<br/>H2.5–6.5"] --> D4
  A3 --> A4["A4 seed_demo"] --> CP2
  H1["H1 Bhashini"] --> H3
  H2["H2 prompts.yaml"] --> H3["H3 prewarm audio<br/>H4–7"] --> H4["H4 audio.py<br/>H7–8.5"] --> D4
  H4 --> H6["H6 handset test"]
  D1 --> H5["H5 simulator page"] --> CP2
  D1 --> N2["N2 dashboard"] --> N3["N3 map + ws.ts"] --> N4["N4 bids, deal"] --> CP3
  CP2 --> N5["N5 switch to real"]
  N1["N1 Exotel account"] --> N6["N6 App Bazaar flow"] --> D7
  D7 --> N7["N7 real phone tests"]
  CP2 --> N8["N8 backup laptop"]
  D1 --> A5["A5 agent PWA"] --> A6["A6 ops page"]
  CP3 --> A7["A7 acceptance run"]
  CP3 --> H7["H7 video"]
  classDef crit fill:#fde2e1,stroke:#c0392b
```

**Critical path:** D1 → D2 → D3 → D4 (needs A3 and H4) → CP2 → D5 → D6 → CP3 → D9 freeze → D10. **Slack on it: about 1 hour** (Darshan's rest at H15–16.5 is the only movable block; if he is late, the rest shrinks to 45 minutes and D7 starts earlier, not later).

Near-critical feeders: **A3** must merge by H7 and **H4** by H8.5, or D4 runs on stubs (it can: `get_floor` stub returns None, mixer stub plays one clip) and the merge moves to CP3.

---

## 6. Hour-by-hour schedule

The template asked for "Day"; in a 24-hour event the unit is a block of hours.

| Block | Darshan | Nahyan | Hitesh | Anirudh | Integration checkpoint |
|---|---|---|---|---|---|
| **H0–H1** | D1: repo, folders, fixtures, frontend shell, `.env.example` | N1: Exotel trial account, whitelist, missed-call mode | H1: Bhashini account and test call | A1: data.gov.in key and real samples; A2 starts | **H0:15 kickoff (15 min):** read §1–§3 of this file together |
| **H1–H2** | D1: compose, schema, mock server, ngrok domain | N2: dashboard list and detail (mock) | H2: prompts.yaml (Gemini draft) | A2: reference seed SQL | **H2: contracts frozen**; everyone pulls `main` and runs the mock |
| **H2–H4** | D2: engine, LISTING flow | N2 | H2: native review | A3: ingestion + `pricing.py` | |
| **H4–H6** | D2: sim adapter, `sim_client.py` | N3: map + `ws.ts` | H3: prewarm script, generation | A3 | **CP1 H6 (10 min):** `sim_client.py` completes a listing on Darshan's engine; prices in DB |
| **H6–H8** | D3: Lua, checkpoint, idempotency, debounce, triage ticket | N3 → N4 | H3 → H4 audio.py | A4: seed_demo.py | A3 merged by H7 |
| **H8–H10** | D4: clustering, outbox, WS hub, minimal REST; merges A3 + H4 | N4: bid form, progress, deal | H4 → H5 simulator page | A5: agent PWA | H4 merged by H8.5 |
| **H10–H12** | D5: auth + all REST + verification + ops endpoints | N5: switch to real; N6 starts | H5 | A5 | **CP2 H10 (15 min):** Hitesh's simulator page → real backend → listing appears live on Nahyan's dashboard. Plan milestone M1 |
| **H12–H14** | D6: bidding, auction close | N6: App Bazaar flow (H11–13); rest H13–14.5 | H5 ends H12.5; **rest H12.5–14** | A5 ends H12.5; **rest H12.5–14** | |
| **H14–H16** | D6: job queue, BID_OFFER (ends H15); **rest H15–16.5** | N8: backup laptop | H6: handset and noise test; H8 starts | A6: ops page | Status sync H14 |
| **H16–H18** | D7: Exotel adapter + spike with Nahyan | N7: real phone tests (H16.5–19) | H8; H17–18 second phone and listener for N7 | A8: pitch deck | **CP3 H18 (20 min):** full E2E on simulator (missed call → listing → verify → bids → accept calls → deal); real phone at least one listing |
| **H18–H19** | D9: demo reset script, tag | N7 | H7: video (H18–20) | A7: acceptance run (H18–19.5) | **H19: CODE FREEZE** (tag `v-demo`) |
| **H19–H21** | D10: blocker fixes only; rehearsal 1 | N9: rehearsal 1 | H7 → H9 rehearsal 1 | A7 → A9 rehearsal 1 | Rehearsal 1 at H20 with failure injection |
| **H21–H24** | D10: rehearsal 2; backup laptop final pull | N9: rehearsal 2; backup laptop check | H9: rehearsal 2 | A9: rehearsal 2; deck final | Rehearsal 2 at H22; **H23 nothing changes**; H24 demo-ready |

**Idle check during the critical path (H0–H18):** Nahyan, Hitesh and Anirudh always have mock-based work queued; nobody waits on Darshan for more than 30 minutes. If someone finishes early, the next item is in §10's "stretch" list, never new features.

---

## 7. Integration and Git workflow

- **Branches:** `feat/<name>-<task id>-<slug>`, for example `feat/nahyan-N3-ws-hook`. One branch per task. Only Darshan pushes to `main`.
- **Pull requests:** small (one task), opened as soon as it works against the mock. Description: what it does, how to test it in 3 steps, screenshot for UI. **Darshan reviews and merges every PR**, within 30 minutes during build blocks. A PR that changes a C-contract file is rejected unless the change was announced.
- **Folder rule:** only edit your own folders (C1). Merge conflicts are then rare. If Gemini wants to "fix" a file outside your folder, stop and ask Darshan.
- **If Git is giving you trouble:** do not lose 20 minutes on it. Zip your folder and send it to Darshan; he merges it with Claude Code.
- **Secrets:** API keys go only in Darshan's `.env` (and the backup laptop's), sent by private DM. Never in Git, screenshots or the group.
- **Sync (10 minutes, at H2, H6, H10, H14, H18, H20, H22).** Each person answers four lines: done since last sync; next task; blocked on what; any contract change needed. Darshan then states the merge order for the next block.
- **Blocked rule:** after **20 minutes** stuck, post `BLOCKED <task id>: <what you tried> / <what you need>` in the group. Then switch to your next mock-based task; do not wait. Darshan answers at the next PR review pass, or Anirudh (deputy) if Darshan is in deep work.
- **Code freeze at H19:** tag `v-demo`. After it: no new features, no refactors, no dependency upgrades. Only Darshan merges, and only fixes for items that fail the acceptance checklist (§9.1). At H23 even fixes stop.

---

## 8. Bus-factor plan

Each backup reads the handover note at CP2 (5 minutes) and runs the "keep it running" commands once on the backup laptop during N8.

| Darshan module | Backup | Handover note: what the backup must know to keep it running in the demo |
|---|---|---|
| Infrastructure (D1): compose, schema, `.env`, ngrok | **Anirudh** | Start: `docker compose up -d` → `psql -f db/001_schema.sql` → `psql -f db/002_reference.sql` → `python backend/scripts/seed_demo.py --reset` → `uvicorn app.main:app --port 8000` (from `backend/`). ngrok: `ngrok http 8000 --url <static domain>`; if the domain changes, update `PUBLIC_BASE_URL` in `.env` and the Exotel flow URLs. `/health` must show all green. |
| Call engine and simulator adapter (D2, D3) | **Hitesh** | The engine is `engine/engine.py: handle_event()`; prompts per state are in `engine/flows.py: PROMPTS`. A missing clip shows in `/health` as `tts_clips` lower than expected. If a call hangs, `POST /api/ops/chaos/flush-redis` and give a new missed call: sessions resume from Postgres. Never edit Lua files during the demo. |
| Clustering and WebSocket hub (D4) | **Anirudh** | Cluster totals are recomputed only by `recompute_cluster`. If the dashboard stops updating, refresh the browser (it replays by `seq`). If a cluster looks wrong, `python backend/scripts/seed_demo.py --reset` resets everything in about 10 s. |
| Auth and REST (D5) | **Nahyan** | Seeded logins and `SEED_PASSWORD` are in `.env`. Token expiry is 12 h, so log in fresh before the demo. 401 on everything → `JWT_SECRET` changed: log in again. |
| Bidding and call queue (D6) | **Nahyan** | Auction closes 180 s after verification, or `POST /api/admin/clusters/{id}/close-auction` (button on the ops page). Confirmation round lasts 90 s; unanswered lots count as rejected. Stuck job → ops page shows it; it is retried automatically. |
| Exotel adapter (D7) | **Nahyan** | `TELEPHONY_PROVIDER=exotel` vs `sim` in `.env`, restart uvicorn. Exotel URLs depend on `PUBLIC_BASE_URL` and `WEBHOOK_SECRET`. If the phone does not ring in 10 s, switch to `sim` and say so. Trial credit left: Exotel dashboard. |
| Demo reset and freeze (D9) | **Nahyan** | `python backend/scripts/demo_reset.py` before every run. The demo is tag `v-demo`; `git checkout v-demo` on the backup laptop. |

Darshan also reviews every other person's work that touches a shared interface (§7). Anirudh is deputy for blocked-question triage when Darshan is heads-down.

---

## 9. Demo-day roles

| Role | Person | Notes |
|---|---|---|
| Lead presenter and engineering narrator | **Darshan** | Runs the demo laptop, the terminal and the ops screen on the projector; triggers Redis flush and closes the auction |
| Phone handler | **Hitesh** | Button phone on speaker (missed call, keypresses, hang-up for the drop demo); the simulator tab for bounce and as fallback |
| Buyer dashboard operator | **Nahyan** | Two buyer laptops: bid, outbid, double-click; owns the backup laptop |
| FPO agent and slides | **Anirudh** | Agent PWA on a phone (verification photo), slide clicker |
| Fallback call | **Darshan** decides, **Hitesh** executes | Rule: 10 s with no ring or no audio → "switching to the simulator" out loud, continue the script |

**Who answers which jury questions**

| Topic | First answer | Second |
|---|---|---|
| Distributed systems, Redis, locks, idempotency, queues (Akamai, Google) | Darshan | Nahyan |
| Network physics, 8 kHz audio, DTMF signalling, TTS (Qualcomm, Gnani) | Hitesh | Darshan |
| Spatial clustering, data, price floor (IISc) | Anirudh | Darshan |
| Buyer behaviour, marketplace design, disintermediation | Nahyan | Anirudh |
| Unit economics, legal, what is simulated | Anirudh | Darshan |

Honesty rule for everyone: answer from plan §14. If you do not know, say "we have not verified that" rather than guess.

### 9.1 Acceptance checklist (run at H18 and after freeze, by Anirudh)

- [ ] Simulator missed call → callback → listing confirmed in under 90 s, and it appears on the dashboard in under 1 s.
- [ ] Hang up after QTY_CONFIRM, missed call again → "welcome back" and resume at PRICE.
- [ ] Price below floor → warning; "raise" stores the floor; "keep" stores the farmer's price.
- [ ] The listing that crosses 20 quintals turns the cluster READY and creates one verification task.
- [ ] Verification from the venue succeeds; a faked far location gets TOO_FAR.
- [ ] Two buyers bid; a double-click records one bid; the outbid buyer's screen updates live.
- [ ] Auction close → accept/reject calls; deal created only if accepted quantity ≥ the buyer's minimum.
- [ ] Bounce switch on → stored numbers still correct; ops page shows BOUNCE rows.
- [ ] Flush Redis during a call → the call continues.
- [ ] Three failed calls → one helper ticket; the agent sees the same 2-digit code the IVR spoke.
- [ ] No farmer phone number in any buyer or agent network response.
- [ ] The button phone completes one listing through Exotel (or "phone leg simulated" is on the slide).
- [ ] The backup laptop runs the demo offline.
- [ ] The whole script runs twice in a row with `demo_reset.py` in between.

---

## 10. Risks and cut line

### 10.1 Top 8 delivery risks

| # | Risk | Likelihood | Effect | Mitigation built into this division |
|---|---|---|---|---|
| 1 | Darshan's critical path slips (engine or bidding takes longer) | High | Everything after CP2 slips | Scope already cut to fit 18 h; stubs let D4 proceed without A3/H4; cut line below starts with his items |
| 2 | Exotel applet wiring does not behave as documented | High | No real phone | Spike time-boxed to 45 minutes in D7; simulator is a complete demo on its own |
| 3 | Bhashini key or quality fails | Medium | No audio | edge-tts decision at H3; audio is pre-generated, so an outage after H7 does not matter |
| 4 | No native-speaker review of Kannada/Hindi prompts | Medium | Embarrassing or wrong prompts | Review is part of H2; unreviewed lines fall back to Hindi or are rewritten shorter |
| 5 | Gemini-built UI does not match the real API | Medium | Broken screens at CP2 | Contracts frozen at H2, mock server mirrors them, N5 and CP2 reserve time for mismatches |
| 6 | Fatigue errors after H16 | High | Bugs at freeze | Staggered rests; freeze at H19; only Darshan merges after freeze |
| 7 | Venue network or tunnel fails | Medium | No Exotel, no phone PWA | Everything local; phone hotspot; backup laptop; video |
| 8 | Git or merge chaos with four people | Medium | Lost work | Folder ownership, small PRs, "zip it to Darshan" rule |

### 10.2 Cut line: dropped first to last if time runs out

Decide at each checkpoint. If a checkpoint is more than 1 hour late, cut the next item.

1. Ops monitor page (A6) → show `/api/ops/calls` JSON in a browser tab
2. Map (part of N3) → list only
3. Hindi audio → Kannada only
4. Deal payment buttons → deal ends at CONFIRMED with payee details
5. Triage ticket UI (part of A5) → the IVR still speaks the code; mention it verbally
6. Real Exotel phone (D7, N6, N7) → simulator only, stated on the slide
7. Backup laptop (N8) → video only as fallback
8. Agent PWA verification (A5) → admin button marks the cluster verified

**Never cut:** engine with resume and idempotency, debounce, price guardrail, clustering, bidding with one leading bid, accept/reject calls, simulator page, buyer dashboard list and bid form.

**Stretch (only after CP3 is green and before H19):** Marathi clips; "9 for more crops"; proxy listing with farmer confirmation call; a 50-call asyncio load script with p95 printed on the ops page.

---

## 11. Gemini starter prompts

**How to use.** For every task, paste **P0** first, then the task prompt, into a new Gemini chat (or an Antigravity agent task scoped to your folder). Ask for complete files, not fragments. Test against the mock server (`python mock/mock_server.py`, port 8001) before opening a PR. Save Antigravity's Opus credits for integration bugs at CP2/CP3.

### P0: shared context (paste before every prompt)

```
You are helping a student team build "Annadata Dhwani", a keypad-and-voice produce marketplace for
Indian farmers who only have button phones. A farmer gives a missed call, the system calls back,
plays recorded prompts in Kannada or Hindi, and the farmer types crop, quantity (quintals) and price
(rupees per quintal) on the keypad. Listings are pooled by FPO collection point into 2-5 tonne
"clusters". FPO field agents verify a cluster with a live photo. Buyers bid on clusters in a web
dashboard; farmers accept or reject the winning bid by keypad.

Stack (fixed, all free): Python 3.12, FastAPI, asyncpg, redis.asyncio (server is Valkey),
PostgreSQL 16 + PostGIS; frontend React 18 + TypeScript + Vite + Tailwind CSS, react-leaflet,
vite-plugin-pwa. No paid services, no new frameworks, no state-management libraries beyond React
hooks. Money is rupees per quintal (number). Phone numbers are E.164 strings like "+919845012345".
Times are ISO-8601 UTC strings.

Environment: frontend reads import.meta.env.VITE_API_BASE (e.g. http://localhost:8001) and
VITE_WS_BASE (e.g. ws://localhost:8001). A helper src/lib/api.ts already exists and exports
  api.get(path), api.post(path, jsonBody, extraHeaders?), api.postForm(path, FormData)
which add "Authorization: Bearer <token>" from localStorage key "token" and throw an Error whose
.status and .body (parsed JSON like {"error":"CODE",...}) are set on non-2xx responses.

Rules: output complete, runnable files with their full paths. Only create or edit the files I name.
Do not invent API fields; use exactly the shapes I give. Handle loading, empty and error states.
After the code, give: (1) how to run it, (2) a short manual test list matching my acceptance criteria.
```

### Nahyan

**N1 (manual): Exotel trial**

```
I must set up an Exotel trial account (India cloud telephony) for a student demo. Facts I know:
the trial lasts 7 days, gives about 500 free credits, allows calls only to up to 10 whitelisted
numbers, gives one test ExoPhone, and all APIs and App Bazaar applets are available. Exotel's
developer docs describe a "Missed call" setting under ExoPhones that auto-hangs-up after 1-2 rings
and sends a POST webhook with CallSid, From, To, Status=missed-call.
Give me a step-by-step checklist to: sign up; whitelist 5 numbers; find the trial ExoPhone; enable
missed-call mode on it; find Account SID, API key and API token; and verify that a call from a
whitelisted phone is cut after 1-2 rings without being answered. For each step tell me what
screenshot to take for our setup document. Warn me about anything that commonly goes wrong.
Output: a numbered checklist plus a Markdown template for docs/exotel_setup.md with headings for
each step and a results table (date, step, result, notes). Do not ask me for my credentials.
```

**N2: dashboard list and detail**

```
Build the buyer dashboard list and detail view.
Files: frontend/src/routes/Buyer.tsx, frontend/src/components/buyer/ClusterList.tsx,
frontend/src/components/buyer/ClusterDetail.tsx, frontend/src/components/buyer/types.ts.

API (exact):
GET /api/clusters?status=OPEN,READY,BIDDING,CONFIRMING,DEAL -> {"clusters":[Cluster,...]}
GET /api/clusters/{id} -> Cluster plus
  "lots":[{"lot_no":1,"qty_qtl":3,"ask_price":3600}],
  "price_ref":{"modal_price":3565,"afpp":3430,"basis":"DISTRICT_FRESH","price_date":"2026-11-12"} or null,
  "msp":5205 or null
Cluster = {"id":"7f0c..","code":104,"crop_code":"ragi","crop_name":"Ragi","district":"Mandya",
 "collection_point":{"name":"Keregodu FPO yard","lat":12.63,"lon":76.92},
 "status":"OPEN|READY|BIDDING|CONFIRMING|DEAL|CLOSED|NO_BID|FAILED","total_qtl":24.0,
 "listing_count":8,"min_ask":3600,"wavg_ask":3742,"grade":"A|B|C"|null,"photo_url":"/media/v/x.jpg"|null,
 "bidding_ends_at":"2026-11-13T12:30:00Z"|null,"best_bid":{"price_per_qtl":3800,"mine":false}|null,
 "version":12}
basis values: DISTRICT_FRESH ("mandi price on <date>"), DISTRICT_7D ("7-day district average"),
STATE_7D ("7-day state average").

Layout (Tailwind, desktop first, works at 1280px): left column list, right column detail.
List: status filter chips (multi-select), crop dropdown, cards showing crop, total in tonnes and
quintals ("2.4 t · 24 qtl"), lots count, min/avg ask, grade badge, status badge with colour,
countdown to bidding_ends_at (updates every second, "ended" when past), best bid or "no bids".
Detail: header, collection point, lot table, photo if present (prefix VITE_API_BASE), price
reference box (mandi modal, fair farm-gate price AFPP, MSP as context with the note "MSP is shown
for context, not used as a floor"), a placeholder <div id="bid-slot"> for the bid form.
Export a function upsertCluster(list, incoming) that replaces an item only if incoming.version is
higher (used later by live events). Show a small "Demo data" tag in the header.
Acceptance: against the mock server all 5 fixture clusters render; filters work; selecting a card
loads the detail; countdown ticks; no console errors.
```

**N3: map and live events hook**

```
Build (1) a cluster map and (2) a reusable live-events hook.
Files: frontend/src/components/buyer/ClusterMap.tsx, frontend/src/lib/ws.ts; edit
frontend/src/routes/Buyer.tsx only to mount the map above the list and to use the hook.

(1) ClusterMap props: {clusters: Cluster[], selectedId?: string, onSelect(id)}. react-leaflet,
OpenStreetMap tiles https://tile.openstreetmap.org/{z}/{x}/{y}.png with attribution
"© OpenStreetMap contributors". One CircleMarker per collection_point (lat, lon), radius scaled by
total_qtl (min 6, max 20), colour by status. If a tile fails to load, hide the map and show
"Map unavailable" (the list must keep working). Cluster type is in components/buyer/types.ts:
{id, code, crop_name, status, total_qtl, collection_point:{name,lat,lon}, version, ...}.

(2) ws.ts exports useEvents(onEvent: (e: {seq:number,type:string,payload:any}) => void,
onResync: () => void). Protocol (exact):
- connect to `${VITE_WS_BASE}/ws?token=${localStorage.token}&since=${lastSeq}`
- lastSeq is stored in localStorage key "seq" (default 0)
- server messages are JSON {"seq":1042,"type":"cluster.updated","payload":{...}}
- a message {"type":"resync"} (no seq) means: call onResync() (caller refetches REST)
- delivery is at-least-once: ignore any message whose seq <= lastSeq; otherwise store seq, call onEvent
- on close: reconnect with backoff 1s, 2s, 4s, 8s, max 15s; reset to 1s after a successful open
- clean up on unmount; expose {connected:boolean} for a small status dot.
Event types used by the dashboard: cluster.updated (payload = Cluster), listing.created,
bid.placed {cluster_id,bid_id,price_per_qtl,buyer_is_you}, bid.confirming {cluster_id,bid_id,
accepted_qtl,rejected_qtl,pending_qtl}, bid.failed, deal.created, deal.updated.
In Buyer.tsx: on cluster.updated call upsertCluster (replace only if version is higher); on resync
refetch GET /api/clusters; show a green/red connection dot.
Acceptance: with the mock server, the scripted story updates the list and map live; turning Wi-Fi
off for 20 s then on reconnects, replays missed events once, and the list equals a fresh REST load.
```

**N4: bidding, confirmation and deal views**

```
Build the bid form, confirmation progress and deal card.
Files: frontend/src/components/buyer/BidForm.tsx, ConfirmProgress.tsx, DealCard.tsx; edit
ClusterDetail.tsx only to render BidForm in the bid slot and ConfirmProgress/DealCard when relevant.

API (exact):
POST /api/clusters/{id}/bids, header "Idempotency-Key: <uuid>", body {"price_per_qtl":3850,"min_qty_qtl":15}
  201 or 200 {"id":"..","status":"LEADING","price_per_qtl":3850,"min_qty_qtl":15}
  409 {"error":"BID_TOO_LOW","min_next":3810} | 409 {"error":"CLUSTER_NOT_BIDDING"} | 422 {"error":"MIN_QTY_TOO_HIGH"}
GET /api/bids/mine -> {"bids":[{"id","cluster_id","price_per_qtl","min_qty_qtl",
  "status":"LEADING|OUTBID|CONFIRMING|DEAL|FAILED|CANCELLED",
  "progress":{"accepted_qtl":9,"rejected_qtl":3,"pending_qtl":12}|null}]}
GET /api/deals/mine -> {"deals":[{"id","cluster_id","qty_qtl":17,"price_per_qtl":3850,
  "gross_value":65450,"platform_fee":981.75,"status":"CONFIRMED|PAYMENT_REPORTED|PAID|CANCELLED",
  "pickup_by":"2026-11-16","fpo":{"name":"Keregodu FPO","payee_details":"UPI keregodu-fpo@bank"}}]}
POST /api/deals/{id}/payment-reported {"payment_ref":"UTR123456"} -> {"status":"PAYMENT_REPORTED"}
Live events (from useEvents in src/lib/ws.ts): bid.placed, bid.confirming {cluster_id,bid_id,
accepted_qtl,rejected_qtl,pending_qtl}, bid.failed {cluster_id,bid_id,accepted_qtl,min_qty_qtl},
deal.created {deal_id,cluster_id,qty_qtl,price_per_qtl,gross_value,platform_fee,pickup_by},
deal.updated {deal_id,status}.

BidForm: only enabled when cluster.status === "BIDDING". Inputs price (default best bid + 10, or
min_ask) and minimum quantity (default total_qtl, max total_qtl). Generate one
crypto.randomUUID() when the user clicks "Place bid" and REUSE it if the request fails with a
network error and the user retries; generate a new one after any server response. Disable the
button while sending (double-click must send one request). Show: success toast; BID_TOO_LOW ->
"Bid at least ₹<min_next>"; other errors in plain words. Helper line: "At ₹X, N of M quintals have an
asking price at or below your bid" computed from the cluster's lots.
ConfirmProgress: horizontal stacked bar accepted (green) / rejected (grey) / pending (amber) in
quintals with numbers, plus "Deal needs ≥ min_qty_qtl accepted".
DealCard: quantity, price, gross value, platform fee "1.5% fee, invoiced to you", pickup date, FPO
name and payee details with a note "Pay the FPO directly. Loading only after the FPO confirms
payment.", payment reference input -> POST, status timeline CONFIRMED -> PAYMENT_REPORTED -> PAID.
Format rupees with Indian grouping (65,450).
Acceptance: against the mock, a double-click sends one request; bidding too low shows min_next; the
scripted story ends on a deal card; reporting payment changes the timeline.
```

**N5: switch to the real backend**

```
Our React buyer dashboard was built against a mock server on port 8001. The real FastAPI backend
now runs on port 8000 with the same contract. Give me a 15-minute checklist to switch and verify:
change frontend/.env.local VITE_API_BASE to http://localhost:8000 and VITE_WS_BASE to
ws://localhost:8000, restart Vite, log in with POST /api/auth/buyer/login {"email","password"}
(response {"token","buyer":{...}}, store token in localStorage "token"), then check each screen.
For each check, tell me what to look at in the browser DevTools Network tab (status code, response
JSON fields) and how to write a precise mismatch report for the backend owner in this format:
"MISMATCH <endpoint>: expected <field/type>, got <field/type>, screenshot attached".
Also give me a small TypeScript runtime guard function assertCluster(x) that checks the fields
id, status, total_qtl, version, collection_point.lat/lon exist and logs a clear console warning if not.
```

**N6 (manual): Exotel App Bazaar flow**

```
In Exotel's App Bazaar I must build a call flow named "annadata-ivr" for a keypad IVR whose logic
lives on our server. Design (fixed): Gather applet 1 -> Passthru applet 1 -> Gather 2 -> Passthru 2
-> ... -> Gather 12 -> Passthru 12 -> Hangup. Every Passthru's failure/other branch goes to Hangup.
Gather k uses a dynamic URL: https://<OUR_DOMAIN>/tel/exotel/<SECRET>/gather?step=k
(our server returns JSON {"gather_prompt":{"audio_url":"..."},"max_input_digits":1,
"finish_on_key":"#","input_timeout":6}). Passthru k URL:
https://<OUR_DOMAIN>/tel/exotel/<SECRET>/digits?step=k (our server returns 200 to continue or 404
to end). The ExoPhone's missed-call webhook: https://<OUR_DOMAIN>/tel/exotel/<SECRET>/missed.
Give me: a click-by-click procedure for one Gather+Passthru pair; a table of all 24 applets with
the exact URL to paste (use placeholders <OUR_DOMAIN> and <SECRET>); how to find the flow's App ID;
how to place a test call from the dashboard; and a list of 4 things to observe and record during
the first test: (a) does Gather call our URL and use our JSON, (b) what exact format the digits
parameter has at the Passthru (we expect literal quotes around it), (c) does a non-200 Passthru
response follow the failure branch, (d) can an applet point back to an earlier applet (a loop).
Output also a results table template for docs/exotel_setup.md.
```

**N7 (manual): real phone test log**

```
Make me a test protocol for testing a missed-call IVR on a real button phone with a teammate at
the server. Tests: 5 complete listings (missed call -> callback within 10 s -> choose crop ->
quantity -> price -> confirm); 1 dropped call (remove the battery after entering quantity, then give
a missed call again; expected: "welcome back" and resume at the price step); 1 bid acceptance
(server sends an offer call; press 1 then 1); a prepaid balance check before and after a missed
call on two different operators (expected: no deduction). For each test give: steps, what to say
to the server-side teammate, what to time with a stopwatch, pass/fail rule. Output a Markdown
results table (run, time, operator, callback seconds, result, notes) to paste into docs/exotel_setup.md.
```

**N8 (manual): backup laptop**

```
Write me a Windows 11 setup checklist for a backup demo laptop that must run this stack fully
offline: Docker Desktop (containers postgis/postgis:16-3.4 and valkey/valkey:8 from a
docker-compose.yml), Python 3.12 with a virtualenv and pip install -r backend/requirements.txt,
Node 20 with npm, FFmpeg (winget install Gyan.FFmpeg), Git. Steps after install: git clone,
copy .env (received privately), docker compose up -d, load db/001_schema.sql and
db/002_reference.sql with psql inside the container (give the exact docker exec command for a
container named annadata-db-1, database annadata, user postgres), run
python backend/scripts/seed_demo.py --reset, run uvicorn app.main:app --port 8000 from backend/,
build the frontend (npm ci && npm run build in frontend/), open http://localhost:8000/health.
Include: how to pre-pull the Docker images while online, how to test with Wi-Fi off, common
Windows errors (WSL2 not enabled, port 5432 in use, execution policy for venv activation) and fixes.
Output: docs/backup_laptop.md content.
```

**N9: rehearsal card (buyer operator)**

```
I operate two buyer laptops in a 7-minute live demo of a crop marketplace. My moments: (1) show
clusters filling live as farmers list by phone; (2) after the FPO agent verifies a cluster, buyer A
bids, buyer B outbids, then buyer A double-clicks a higher bid (the system must record one bid);
(3) watch the confirmation bar fill as farmers press keys; (4) show the deal card with the 1.5% fee
and "pay the FPO directly". Write me a one-page cue card: exact clicks, what I say in one sentence
at each moment, what to do if the screen does not update (refresh: events replay), and the signal
to switch to the backup laptop. Also 5 likely jury questions about the buyer side
(disintermediation, why buyers would pay 1.5%, fake buyers, no-show trucks, price manipulation)
with honest 2-sentence answers: buyers are admin-approved; 3 no-shows suspend a buyer; "no payment,
no loading"; disintermediation is an unsolved business risk; farmers can always reject.
```

### Hitesh

**H1 (manual): Bhashini**

```
Help me get a working Bhashini (India government language API) text-to-speech call. Facts: register
at bhashini.gov.in (ULCA), verify email, then in My Profile copy the userID and generate an API key.
Config call: POST https://meity-auth.ulcacontrib.org/ulca/apis/v0/model/getModelsPipeline with
headers userID and ulcaApiKey and body
{"pipelineTasks":[{"taskType":"tts","config":{"language":{"sourceLanguage":"kn"}}}],
 "pipelineRequestConfig":{"pipelineId":"<PIPELINE_ID>"}}.
The response contains pipelineInferenceAPIEndPoint.callbackUrl, pipelineInferenceAPIEndPoint.
inferenceApiKey {name, value}, and a serviceId inside pipelineResponseConfig.
Compute call: POST to callbackUrl with header <inferenceApiKey.name>: <inferenceApiKey.value> and body
{"pipelineTasks":[{"taskType":"tts","config":{"language":{"sourceLanguage":"kn"},"serviceId":"<id>",
 "gender":"female"}}],"inputData":{"input":[{"source":"<text>"}]}}. The audio comes back base64
encoded (22050 Hz WAV), likely at pipelineResponse[0].audio[0].audioContent (verify by printing).
Write a single Python script bhashini_test.py (httpx, reads BHASHINI_USER_ID, BHASHINI_API_KEY,
BHASHINI_PIPELINE_ID from environment) that does both calls for "kn" and "hi" with one short
sentence each, prints the JSON paths it found, and saves kn_test.wav and hi_test.wav. Explain how to
find the pipeline ID in the Bhashini API documentation. If any step fails, print the full response.
```

**H2: prompts.yaml**

```
Write backend/prompts.yaml for a phone IVR used by farmers in Karnataka. Format:
<clip_id>:
  en: "<English>"
  kn: "<Kannada, simple spoken village Kannada, not formal written style>"
  hi: "<Hindi, simple spoken Hindi>"
  reviewed: false
Rules: each line under 12 words where possible; numbers written as words; "quintal" kept as
"quintal" (farmers use it); "press" = the common spoken verb for pressing a phone key.
Special: lang_option kn = "For Kannada, press 1" in Kannada; hi = "For Hindi, press 2" in Hindi.
qty_1..qty_50 = "<n> quintal(s)" written as words in each language. d_0..d_9 = digit names.
cropkey_<crop>_<k> = "For <crop>, press <k>" for crops ragi, paddy_common (say "paddy"), maize
and k = 1,2,3 (9 clips).
Clip ids and English meaning (exact list, produce every one):
welcome: Welcome to Annadata Dhwani.
consent: We will save your name, phone number, village and the crops you list, to find buyers for you. We do not record this call. Press 1 to agree, or 2 to exit.
main_menu: You already have a crop listed. Press 1 to list a new crop. Press 0 for a helper.
crop_menu_intro: Which crop do you want to sell?
helper_key_0: For a helper, press 0.
crop_ragi: Ragi. | crop_paddy_common: Paddy. | crop_maize: Maize.
ask_qty: How many quintals? One quintal is one hundred kilos. Type the number, then press hash.
you_entered: You entered
confirm_1_2: If correct, press 1. To enter again, press 2.
mandi_price_was: The mandi price in your district was
fair_price_is: The fair price at your village is
rupees_per_qtl: rupees per quintal.
no_price_today: No mandi price is available today.
ask_price: Type your price per quintal in rupees, then press hash.
guard_warn: Your price is below the fair price of
guard_options: To raise your price to the fair price, press 1. To keep your price, press 2. To type again, press 3.
final_intro: You are listing
at_price: at a price of
final_confirm: To confirm, press 1. To start again, press 2.
listed_ok: Your crop is listed.
your_number_is: Your listing number is
will_call: We will call you when a buyer makes an offer. Goodbye.
welcome_back: Welcome back. Let us continue where you stopped.
bad_input: Sorry, that was not valid.
already_listed: You already have this crop listed.
bye: Thank you. Goodbye.
helper_will_call: A helper from your FPO will call you.
helper_code_is: Only talk to a helper who tells you this code:
not_registered: This number is not registered with your FPO.
offer_intro: Good news. A buyer offers
for_your: for your
your_ask_was: Your asking price was
offer_options: To accept, press 1. To reject, press 2. To hear again, press 9.
offer_confirm: You are accepting this offer. To confirm, press 1. To go back, press 2.
offer_done: Accepted. Your FPO will tell you the pickup day. Goodbye.
offer_rejected: You rejected the offer. Your crop stays listed. Goodbye.
Sentence fragments (you_entered, at_price, fair_price_is, etc.) will be followed by spoken numbers,
so they must sound natural when followed by a number. After the YAML, list every line where you
are unsure of the Kannada or Hindi wording so a native speaker can check them first.
```

**H3: prewarm_audio.py**

```
Write backend/scripts/prewarm_audio.py.
Input: backend/prompts.yaml (format: clip_id: {en, kn, hi, reviewed}). Languages: kn, hi.
Output: audio/<lang>/<clip_id>.wav plus audio/<lang>/<clip_id>.sha (sha256 of "lang|voice|text").
For each clip and language: skip if the .wav exists and the .sha matches; else synthesise, convert,
write atomically (temp file then os.replace).
Engines (choose with --engine bhashini|edge, default bhashini; on any Bhashini error for a clip,
fall back to edge for that clip and log it):
- bhashini: config POST https://meity-auth.ulcacontrib.org/ulca/apis/v0/model/getModelsPipeline
  headers userID, ulcaApiKey; body {"pipelineTasks":[{"taskType":"tts","config":{"language":
  {"sourceLanguage":"<lang>"}}}],"pipelineRequestConfig":{"pipelineId":"<BHASHINI_PIPELINE_ID>"}};
  take callbackUrl and inferenceApiKey {name,value} from pipelineInferenceAPIEndPoint and serviceId
  from pipelineResponseConfig[0].config[0].serviceId (cache per language). Compute POST to callbackUrl,
  header {name: value}, body {"pipelineTasks":[{"taskType":"tts","config":{"language":{"sourceLanguage":
  "<lang>"},"serviceId":"<id>","gender":"female"}}],"inputData":{"input":[{"source":"<text>"}]}};
  audio = base64 at pipelineResponse[0].audio[0].audioContent (WAV). Env: BHASHINI_USER_ID,
  BHASHINI_API_KEY, BHASHINI_PIPELINE_ID. Timeout 60 s, 2 retries, 0.5 s pause between requests.
- edge: edge_tts.Communicate(text, voice, rate="-5%").save(mp3) with voices kn-IN-SapnaNeural,
  hi-IN-SwaraNeural.
Conversion (subprocess, check=True): ffmpeg -y -i <in> -af
"highpass=f=300,lowpass=f=3400,loudnorm=I=-16:TP=-3:LRA=7" -ar 8000 -ac 1 -c:a pcm_s16le <out.wav>
Also: --only <clip_id> to regenerate one clip; --check to verify every file with Python's wave
module (8000 Hz, 1 channel, sampwidth 2) and print missing ids compared to the YAML; a final summary
(generated, skipped, failed, engine used per language). Python 3.12, httpx, pyyaml, edge-tts; asyncio.
Acceptance: about 220 files; --check reports 0 missing and all 8000/1/2.
```

**H4: audio.py mixer**

```
Write backend/app/services/audio.py and backend/tests/test_audio.py.
Clip files are audio/<lang>/<clip_id>.wav (8000 Hz, mono, 16-bit PCM). AUDIO_ROOT defaults to
Path(__file__).resolve().parents[3] / "audio" and can be overridden by env var AUDIO_ROOT.
Exact interface:
def digit_clips(n: int) -> list[str]   # 3430 -> ["d_3","d_4","d_3","d_0"]; 0 -> ["d_0"]
def mix(clips: list[str], lang: str) -> str
  # a clip id "hi:lang_option" forces language hi for that clip; others use `lang`
  # sha = sha256("|".join([lang] + clips)).hexdigest()[:24]; output AUDIO_ROOT/mix/<sha>.wav
  # if the file exists return sha immediately (cache); else concatenate frames with 150 ms of
  # silence (zero bytes) between clips using the standard wave module; write to a temp file in
  # the same folder and os.replace it (safe under concurrent requests); raise FileNotFoundError
  # naming the missing clip
def mix_url(clips: list[str], lang: str, base_url: str) -> str  # f"{base_url}/audio/mix/{sha}.wav"
def missing_clips(clip_ids: list[str], langs: list[str]) -> list[str]  # "kn/ask_qty" style entries
Tests (pytest, tmp_path with generated sine-wave WAVs): digit_clips cases; mix duration equals sum
of clips + 150 ms gaps; second call returns the same sha without rewriting (mtime unchanged);
"hi:" prefix picks the hi file; missing clip raises; 20 threads mixing the same list produce one
valid file. No external libraries except pytest.
```

**H5: simulator phone page**

```
Build a browser "button phone" simulator that talks to our IVR backend over WebSocket.
Files: frontend/src/routes/Sim.tsx, frontend/src/components/sim/Phone.tsx,
frontend/src/components/sim/Keypad.tsx, frontend/src/components/sim/dtmf.ts.
Protocol (exact). Socket: `${VITE_WS_BASE}/tel/sim/ws?phone=${encodeURIComponent(phone)}`
client->server {"t":"missed_call"}
server->client {"t":"ring","call_id":"sim-17"}
client->server {"t":"answer","call_id":"sim-17"}
server->client {"t":"play","call_id":"sim-17","audio_url":"/audio/mix/ab12.wav","max_digits":1,
                "finish_on_key":"","timeout_s":6,"state":"CROP"}
client->server {"t":"digit","call_id":"sim-17","d":"1","ts_ms":Date.now(),"seq":n} (every key, n increments per call)
client->server {"t":"timeout","call_id":"sim-17","seq":n} sent timeout_s seconds after the audio ENDS
               if no key was pressed since that play arrived (cancel the timer on any key)
server->client {"t":"hangup","call_id":"sim-17"}; client->server {"t":"hangup","call_id":"sim-17"} on red key
audio_url is relative: play `${VITE_API_BASE}${audio_url}`; a new play stops the previous audio.
Phone component props {phone: string, label: string}. UI: a phone-shaped card (Tailwind) with a small
screen (status: idle / ringing / in call + state name + call timer), a green "Give missed call"
button when idle, a pulsing "Answer" button when ringing, a 3x4 keypad 1-9,*,0,# plus green and red
keys, a scrolling log of sent/received messages (time, direction, JSON).
dtmf.ts: play standard DTMF tones with the WebAudio API (row 697/770/852/941 Hz, column
1209/1336/1477 Hz, 100 ms, gain 0.1) on each key press.
Two switches: "Inject key bounce" (send every digit twice, the second after a random 30-60 ms with
its own seq, same d); "Drop call" button (close the socket without sending hangup, show "call
dropped", reconnect after 2 s in idle state).
Sim.tsx: shows two phones side by side; each has a dropdown of seeded demo farmers loaded from a
const array in the file: [{phone:"+919800000001",label:"Ramesh, Keregodu"},{phone:"+919800000002",
label:"Lakshmi, Keregodu"},{phone:"+919800000003",label:"Manju, Hosahalli"}] (editable later).
Acceptance: against the mock server the scripted call plays audio, keys produce tones and digit
messages, bounce sends doubles 30-60 ms apart (visible in the log), timeout fires after audio end,
drop closes the socket and the phone returns to idle.
```

**H6 (manual): handset and noise test**

```
Design a 30-minute listening test for IVR prompts recorded at 8 kHz telephone quality, played on a
cheap button-phone speaker. We have 10 mixed prompts (5 quantity readbacks like "you entered fifteen
quintals" and 5 prices spoken digit by digit like "three four three zero rupees per quintal") in
Kannada and Hindi. Protocol: play each prompt through a real phone call (or the phone speaker) in
(a) a quiet room and (b) with loud background noise (a fan plus a crowd/tractor noise video at high
volume). A listener who has not seen the list writes what they hear. Give me: the randomised order
sheet, the scoring rule (pass = 10/10 numbers correct in both conditions), what to change if it
fails (raise loudnorm target from -16 to -14 LUFS, slow the TTS rate, add 250 ms gaps between
digits, rewrite the sentence shorter) and a results table for docs/audio_tests.md.
```

**H7 (manual): backup video**

```
I must record a 3-minute backup video of a live demo in case everything fails on stage. The demo:
a button phone gives a missed call and gets called back; Kannada prompts; farmer types crop,
quantity, price; a price warning; a dropped call that resumes; a web dashboard where the cluster
fills to 2 tonnes; an FPO agent verifies with a phone photo; two buyers bid; farmers accept by
keypad; a deal card appears; an ops screen shows keypad-bounce events dropped and a Redis flush
survived. Give me: a shot list with timings, how to record screen plus phone audio together for
free on Windows (OBS Studio settings: 1080p, 30 fps, audio from a phone line-in or a second
recorder), how to add English subtitles for the Kannada audio for free (e.g. Shotcut or
DaVinci Resolve free), export settings under 200 MB, and a checklist to copy it to two laptops and
a USB stick and test playback offline.
```

**H8: jury Q&A, voice and network**

```
Prepare me for jury questions from Qualcomm and Gnani engineers about our keypad IVR. Facts to use
(do not add claims): GSM/AMR-NB voice is narrowband, about 300-3400 Hz at 8 kHz sampling. On the
radio leg a GSM handset signals DTMF to the network as a signalling message and the network
regenerates the tone; RFC 2833/4733 telephone-events exist only on SIP/VoIP legs; with our cloud
provider we receive digits over HTTP and never see RTP. We found no numeral-specific Indic ASR
benchmark on 8 kHz audio; IndicWhisper reports 26.8% WER on Hindi phone-recorded speech
(Gramvaani). Our debounce: drop the same digit repeated within 120 ms and any digit within 40 ms,
only on paths with per-digit timing (simulator); on the cloud PBX we get a finished string, so we
rely on single-digit menus, range checks and spoken readback with confirm. 120 ms is our estimate.
Prompts are pre-generated (Bhashini or edge-tts), band-passed 300-3400 Hz, normalised to -16 LUFS,
8 kHz mono 16-bit. Numbers are spoken digit by digit. Write 10 hard questions with honest answers
under 45 seconds each, and mark the 3 claims I must never overstate.
```

**H9: rehearsal card (phone handler)**

```
I handle the button phone and the browser phone simulator in a 7-minute live demo. My moments:
give a missed call and answer the callback on speaker; press 1 (crop), 3 then # (quantity), confirm 1,
type 3200 then # (below the fair price, triggering a warning), press 1 to raise; hang up before the
final confirm, give a missed call again, hear "welcome back", confirm; later on the simulator turn on
"inject key bounce" and enter quantity 4 to show it stored as 4; later answer the buyer-offer call
and press 1 then 1. Write a one-page cue card: each action, the exact keys, what the phone should
say, what I say to the jury in one sentence, and the fallback rule (no ring or no audio for 10 s ->
say "switching to the simulator" and do the same steps on the simulator tab).
```

### Anirudh

**A1 (manual): data.gov.in key and samples**

```
I need a free API key from data.gov.in and real sample responses from the "Current Daily Price of
Various Commodities from Various Markets (Mandi)" resource, id 9ef84268-d588-465a-a308-a864a43d0070.
Endpoint: https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070?api-key=<KEY>&format=json
&limit=100&filters[state.keyword]=Karnataka&filters[district]=Mandya&filters[commodity]=<name>.
Fields returned: state, district, market, commodity, variety, grade, arrival_date (dd/mm/yyyy),
min_price, max_price, modal_price (rupees per quintal). The public sample key returns only 10 rows.
Give me: steps to register and find my key; a tiny Python script fetch_samples.py (httpx) that,
with KEY from the environment, fetches Mandya and Mysuru for commodity names "Ragi (Finger Millet)",
"Paddy(Dhan)(Common)" and "Maize" (and if a query returns 0 rows, retries with only state+district
and prints the distinct commodity names present so I can copy the exact spelling), and saves each
raw JSON to contracts/fixtures/agmark_<district>_<crop>.json. Print counts and the exact commodity strings.
```

**A2: reference seed SQL**

```
Write db/002_reference.sql (PostgreSQL 16 + PostGIS) plus a 10-line Python helper
db/make_hashes.py that prints bcrypt hashes (library bcrypt) for a password read from env SEED_PASSWORD.
Tables already exist (do not create them). Columns:
districts(code text PK, name, state, agmark_state, agmark_district, default_lang in ('kn','hi','mr'))
crops(code text PK, name_en, agmark_name, msp numeric, max_listing_qtl numeric default 50,
      min_price numeric not null, max_price numeric not null)
crop_calendar(district_code, month smallint 1-12, crop_code, rank smallint, PK(district_code,month,crop_code))
deduction_rules(district_code PK, transport_per_qtl, handling_per_qtl, pct_deduction numeric(5,4), source_note)
fpos(id uuid PK default gen_random_uuid(), name, district_code, payee_details)
collection_points(id uuid PK default, fpo_id, name, district_code, geog geography(Point,4326))
agents(id uuid PK default, fpo_id, name, phone unique, pin_hash, active boolean default true)
buyers(id uuid PK default, org_name, email unique, password_hash, phone, license_no,
       status in ('PENDING','APPROVED','SUSPENDED'), strikes smallint default 0)
Data: districts KA-MANDYA (Mandya, Karnataka, agmark_state 'Karnataka', agmark_district 'Mandya', kn)
and KA-MYSURU (Mysuru, Karnataka, 'Karnataka', 'Mysore' -- verify spelling from the API samples, kn).
crops: ragi (Ragi, agmark '<exact from samples>', msp 5205, bounds 1500-9000), paddy_common (Paddy,
msp 2441, bounds 1000-5000), maize (Maize, msp 2410, bounds 1000-5000).
crop_calendar for both districts, months 10, 11, 12: ragi 1, paddy_common 2, maize 3.
deduction_rules both districts: transport 50, handling 10, pct 0.0200, note 'assumed; confirm with FPO'.
One FPO 'Keregodu Farmer Producer Company' in KA-MANDYA with payee_details 'UPI keregodu-fpo@bank (demo)'.
Three collection points: 'Keregodu FPO yard' (12.6300 N, 76.9200 E), 'Hosahalli point'
(12.5800, 76.8800), 'Venue demo point' (use placeholders :venue_lat, :venue_lon as psql variables
-v venue_lat=.. -v venue_lon=..). Use ST_SetSRID(ST_MakePoint(lon, lat),4326)::geography (longitude first!).
Use fixed UUIDs (write them as literals) so other scripts can refer to them, and ON CONFLICT DO NOTHING
everywhere. Agents: Kavya +919800000101, Suresh +919800000102 with pin_hash '<HASH_PIN>'.
Buyers (APPROVED): buyer1@demo.test 'Mysuru Grain Traders', buyer2@demo.test 'Mandya Agro Foods',
admin@demo.test 'Admin', password_hash '<HASH_PW>'. Explain how to replace <HASH_PIN>/<HASH_PW>.
Acceptance: psql -v venue_lat=12.97 -v venue_lon=77.59 -f db/002_reference.sql runs twice without errors.
```

**A3: price ingestion and pricing.py**

```
Write backend/scripts/ingest_prices.py, backend/app/services/pricing.py, backend/tests/test_pricing.py.
Tables (exist): districts(code, agmark_state, agmark_district), crops(code, agmark_name),
deduction_rules(district_code, transport_per_qtl, handling_per_qtl, pct_deduction),
mandi_prices(id bigserial, district_code, crop_code, market, price_date date, min_price, max_price,
 modal_price not null, source text, fetched_at; UNIQUE(district_code,crop_code,market,price_date)),
price_floors(district_code, crop_code, as_of date, price_date date, modal_price, afpp,
 basis in ('DISTRICT_FRESH','DISTRICT_7D','STATE_7D'); PK(district_code,crop_code,as_of)).
API: GET https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070 params api-key
(env DATA_GOV_KEY), format=json, limit=1000, filters[state.keyword]=<agmark_state>,
filters[commodity]=<agmark_name>. Response {"records":[{"district","market","arrival_date":"12/11/2026",
"min_price","max_price","modal_price"}...]} (prices may be strings). One call per state x crop returns
all districts; filter district in Python (case-insensitive) for the district rows; use all rows for the state median.
pricing.py (exact interface):
def compute_afpp(modal: float, pct_deduction: float, transport: float, handling: float) -> int:
    raw = modal*(1-pct_deduction) - transport - handling; return int(raw // 10 * 10)
async def get_floor(pool, redis, district_code: str, crop_code: str) -> dict | None
    # 1) redis key f"floor:{district_code}:{crop_code}" (JSON) 2) price_floors row with as_of = today (IST)
    # 3) newest price_floors row with as_of within 7 days 4) None. Never raise (log and return None).
    # return {"modal_price": float, "afpp": int, "basis": str, "price_date": "YYYY-MM-DD"}
ingest_prices.py (asyncio, asyncpg pool from env DATABASE_URL, redis.asyncio from REDIS_URL):
for each district x crop: fetch (3 retries, 10 s timeout, backoff 1/2/4 s); upsert district rows
into mandi_prices (source 'data.gov.in'); outlier filter: drop a modal more than 40% away from the
median of that district+crop's stored modals in the last 7 days (if any); floor basis:
DISTRICT_FRESH = median of today's district modals if the newest arrival_date is within 2 days;
else DISTRICT_7D = median of stored district modals over 7 days; else STATE_7D = median of the state
rows from this call; else write nothing. afpp via compute_afpp with the district's deduction_rules.
Upsert price_floors (as_of = today IST); SET floor:* in redis with EX 93600. Flag --from-fixtures DIR
reads contracts/fixtures/agmark_<district>_<crop>.json instead of calling the API. Print a table.
Tests: compute_afpp(3565, 0.02, 50, 10) == 3430; median and outlier helpers; get_floor returns None
when nothing exists (use a fake pool/redis object). Acceptance: real run writes floors for 6 pairs.
```

**A4: demo seed script**

```
Write backend/scripts/seed_demo.py (asyncio + asyncpg, env DATABASE_URL). Reference data and fixed
UUIDs already exist from db/002_reference.sql: FPO id <FPO_UUID>, collection points <CP_KEREGODU>
(12.63, 76.92), <CP_HOSAHALLI> (12.58, 76.88), <CP_VENUE>; districts KA-MANDYA; crops ragi,
paddy_common, maize. (Replace the placeholders with the literals from 002_reference.sql.)
Tables to fill (exact columns):
farmers(id uuid default, phone unique E.164, name, fpo_id, village, district_code,
 geog geography(Point,4326), collection_point_id, lang 'kn' or NULL, consent_version, consent_at, status 'ACTIVE')
clusters(id uuid default, collection_point_id, crop_code, status, total_qtl, listing_count,
 min_ask, wavg_ask, grade, bidding_ends_at, version) -- only one OPEN/READY cluster per (point, crop) is allowed
listings(id uuid default, farmer_id, cluster_id, crop_code, qty_qtl, ask_price, afpp_at_listing,
 guardrail 'NONE', source 'IVR', session_id NULL, status 'ACTIVE')
mandi_prices(district_code, crop_code, market, price_date, min_price, max_price, modal_price, source 'seed')
Seed: 40 farmers with Kannada first names and villages, phones +919800000001..+919800000040
(the first 4 will be replaced by the team's real numbers via env TEAM_PHONES="+91..,+91..,+91..,+91.."),
each placed at a random point 0.5-4 km from its collection point (use a fixed random seed), with
lang 'kn' and consent_version 'v1' for farmers 5-40 and NULL for 1-4 (so the live demo hears the
language and consent prompts). Cluster A: Keregodu, ragi, status OPEN, 6 listings totalling 17 qtl
(2,3,3,3,3,3) asks 3550-3700. Cluster B: Hosahalli, paddy_common, status BIDDING, 8 listings 26 qtl,
grade 'B', bidding_ends_at now()+1 day. Compute total_qtl, listing_count, min_ask and quantity-weighted
wavg_ask in SQL after inserting listings. Seven days of mandi_prices for each district x crop
(ragi modal around 3550, paddy 2200, maize 2100, small daily noise), market 'Mandya'.
--reset: TRUNCATE listings, bid_responses, bids, deals, verifications, call_jobs, call_sessions,
triage_tickets, consent_log, dtmf_events, events, clusters, farmers CASCADE, then reseed.
All in one transaction. Acceptance: running twice with --reset gives identical counts (print them).
```

**A5: FPO agent PWA**

```
Build the mobile FPO agent app (Android Chrome, low-end phones).
Files: frontend/src/routes/Agent.tsx, frontend/src/components/agent/AgentLogin.tsx, TaskList.tsx,
VerifyCapture.tsx, TicketList.tsx, DealConfirm.tsx; add vite-plugin-pwa config in a separate file
frontend/pwa.config.ts exporting the plugin options (name "Annadata FPO", short_name "FPO",
theme_color "#166534", display "standalone", icons 192 and 512 placeholders) for the lead to wire in.
API (exact):
POST /api/auth/agent/login {"phone":"+919800000101","pin":"1234"} -> {"token","agent":{"id","name","fpo_id"}}
  (store token in localStorage "token")
GET /api/agent/tasks -> {"verify":[Cluster...], "tickets":[{"id","village","first_name","reason":
  "IVR_FAIL_3|UNKNOWN_CALLER|HELP_KEY","status":"OPEN|ASSIGNED|RESOLVED","created_at"}],
  "deals":[{"id","cluster_code","status":"CONFIRMED|PAYMENT_REPORTED|PAID","qty_qtl","gross_value"}]}
  Cluster has id, code, crop_name, total_qtl, listing_count, collection_point:{name,lat,lon}.
POST /api/agent/clusters/{id}/verification multipart: photo (image/jpeg), grade (A|B|C|REJECT),
  moisture_pct (optional), lat, lon, accuracy_m, captured_at (ISO)
  201 {"cluster_id","status":"BIDDING","bidding_ends_at"} | 422 {"error":"TOO_FAR","distance_m":1840}
  | 422 {"error":"STALE_CAPTURE"} | 422 {"error":"LOW_ACCURACY"} | 409 {"error":"ALREADY_VERIFIED"}
POST /api/agent/triage/{id}/claim -> {"status":"ASSIGNED"}
POST /api/agent/triage/{id}/bridge -> {"verbal_code":"55","mode":"simulated"|"exotel"} | 409 {"error":"CODE_USED"}
POST /api/agent/deals/{id}/payment-confirmed -> {"status":"PAID"}
Use api.get/post/postForm from src/lib/api.ts. Poll tasks every 10 s.
VerifyCapture: live camera with navigator.mediaDevices.getUserMedia({video:{facingMode:"environment"}})
into a <video>; "Capture" draws to a canvas, makes a JPEG with canvas.toBlob(..,"image/jpeg",0.7);
at capture time call navigator.geolocation.getCurrentPosition({enableHighAccuracy:true,timeout:15000});
show accuracy; big grade buttons A/B/C/Reject; optional moisture number; Submit sends the multipart.
Do NOT offer a file picker or gallery upload. Show TOO_FAR as "You are <distance_m> m from
<point name>. Go to the collection point." If camera or location is denied or the page is not HTTPS,
show a clear message ("Open this app through the https link").
TicketList: first name + village + reason (never a phone number), Claim, then "Call farmer" which calls
bridge and shows the verbal code in very large digits with "Say this code first"; mode "simulated"
shows a banner "Call simulated in demo".
DealConfirm: "Payment received" button for PAYMENT_REPORTED deals, with a confirm dialog.
Mobile-first Tailwind, touch targets ≥ 48 px, works at 360 px width.
Acceptance: against the mock server on a real Android phone over HTTPS: login, capture and submit,
lat=0 gives TOO_FAR message, ticket code shows, payment button works.
```

**A6: ops monitor page**

```
Build an operations monitor for a live demo projector.
File: frontend/src/routes/Ops.tsx (and frontend/src/components/ops/*.tsx if you want to split).
API (exact; admin token in localStorage "token"):
GET /api/ops/calls (poll 1 s) -> {"sessions":[{"phone_masked":"+91•••••2345","kind":"LISTING|BID_OFFER",
  "state":"PRICE","provider":"sim|exotel","version":7,"updated_at"}],"jobs":[{"id","kind":"CALLBACK|BID_OFFER",
  "status":"QUEUED|DIALING|IN_CALL|DONE|FAILED|CANCELLED","attempts":1,"run_at"}],
  "breaker":{"calls_today":14,"budget":200}}
GET /api/ops/dtmf?limit=50 (poll 1 s) -> {"events":[{"session_id","state_before":"QTY","digits":"3",
  "state_after":"QTY_CONFIRM","dropped_reason":null|"BOUNCE"|"DUPLICATE_EVENT"|"OUT_OF_RANGE","at"}]}
GET /health (poll 5 s) -> {"db":"ok","redis":"ok","tts_clips":220,"price_age_days":0,"provider":"sim",
  "public_base_url_ok":true}
POST /api/ops/chaos/flush-redis -> {"ok":true}
POST /api/admin/clusters/{id}/close-auction -> {"status":"CONFIRMING"} (input box for a cluster id or code)
Layout for a 1920x1080 projector, dark theme, large fonts: top bar health lights (green/red per field,
price age in days, provider); left: live call sessions as cards with a big state badge and version
number (highlight a card for 1 s when its version changes); middle: job queue table and a breaker gauge
(calls_today / budget); right: DTMF log, newest first, dropped rows in red with the reason;
bottom: "Flush Redis" red button with a confirm dialog and a "Close auction" control. Pause polling
when the tab is hidden. Acceptance: against the mock all panels render and update; flush shows a toast.
```

**A7 (manual): acceptance and chaos run**

```
Turn this acceptance checklist into a test script I can execute alone in 90 minutes on a running
demo system (browser simulator phone, buyer dashboard, agent phone app, ops page, a terminal):
[paste §9.1 of TASK_DIVISION.md here]. Also include these failure injections: Redis flush during a
call; backend restart during a call; a dropped call at each IVR step; the same keypad webhook sent
twice; Wi-Fi off for 30 s on a dashboard. For each item: preconditions, exact steps, expected result,
pass/fail box, and a bug report template "BUG <step>: expected <x>, saw <y>, time, screenshot".
Order the items so setup is reused and the run takes under 90 minutes.
```

**A8: pitch deck**

```
Write slide content (titles, bullets, speaker notes, one suggested visual each) for a 6-slide pitch
to engineers from Google, Akamai, Qualcomm, Gnani and IISc, for "Annadata Dhwani", a missed-call and
keypad marketplace for button-phone farmers. Use only these facts and label estimates as estimates:
86% of Indian landholdings are small or marginal (Agriculture Census 2015-16); our estimate is
roughly 30 million such farmers still on 2G-only phones (about 126 million small holdings times a
fifth to a quarter on 2G; not a published figure); harvests of 150-400 kg are too small for a truck
of 2-5 tonnes; mandi price feed: Mandya ragi modal ₹3,565 per quintal on 12 Nov 2026 vs MSP ₹5,205.
Unit economics per cluster (model, assumed call rate ₹0.60/min): 24 quintals at ₹3,500 = ₹84,000;
1.5% buyer fee = ₹1,260; telephony about ₹26; FPO verification ₹50; contribution about ₹1,184;
the free callback costs about ₹1.56 per listing vs ₹157.50 of fee. Production fixed costs: Exotel
plan ₹9,999 for 5 months, DLT about ₹5,900; break-even about 14 closed clusters in 5 months.
Slides: 1 Problem (MOQ trap, price blindness, no smartphone); 2 How it works (missed call -> keypad
listing -> pooled cluster -> FPO verification -> buyer bids -> keypad accept); 3 Live demo cue;
4 Engineering proof (DTMF not speech for numbers, 8 kHz audio, drop recovery, idempotent webhooks,
Postgres row locks for bids, Redis disposable); 5 Unit economics; 6 What is real, simulated, and
paid in production (real: engine, data, prices, audio, clustering, bidding, one real phone call on
an Exotel trial; simulated: other farmers' phones, buyers, payment, masked helper call; paid in
production: telephony plan, DLT, call minutes; legal: state market licences and data-protection
rules from May 2027). Plain language, no hype words, max 6 bullets per slide.
```

**A9: rehearsal card (agent and slides)**

```
I operate the FPO agent phone app and the slides in a 7-minute demo, and I answer jury questions on
prices, unit economics and law. My moment: when the cluster reaches 2 tonnes, I open the agent app,
take a live photo of a grain sample at the venue, choose grade A, submit, and the cluster moves to
bidding on the buyer screens. Write a one-page cue card (clicks, one sentence to say, fallback: if
the phone app fails, the lead marks the cluster verified from the admin control). Then give 6 hard
questions with honest 2-sentence answers, using these facts: the price feed is the government
open-data mandi feed, current day only and sometimes thin (7 rows for Mandya on the day we tested),
so we store it daily and fall back to 7-day district then state medians and say the basis aloud;
fair farm-gate price = mandi modal x 0.98 - ₹60 per quintal (assumed, to confirm with an FPO);
MSP is not used as a floor because ragi traded at ₹3,565 vs MSP ₹5,205; the platform never holds
money (buyer pays the FPO directly); production needs telecom registration (DLT), possibly state
market licences (Karnataka reportedly licenses e-commerce platforms for notified produce), and
data-protection duties from May 2027; disintermediation is an unsolved business risk.
```

---

## 12. Open issues and assumptions

| # | Issue | Decision |
|---|---|---|
| 1 | The plan was written for 14 days; you have 24 hours | Applied the plan's cut line hard; see §2 and §10. The plan's §12 roadmap is replaced by §6 of this file |
| 2 | Your summary mentions per-farmer counter-bids, H3, and Redis Lua locks for bids | The plan cut counter-bids and H3 and puts bid correctness in Postgres row locks. Followed the plan |
| 3 | Masked triage bridge with verbal OTP | Simplified: ticket + IVR-spoken 2-digit code + agent screen; the bridge call is simulated (a real Exotel bridge is not in the 24-hour scope) |
| 4 | 50–55 % cap for Darshan | Meaningless in hours for a 24-hour event (he is at 26 %); the real constraint is his critical path, handled by scope cuts and backups |
| 5 | Productive hours per person | 20 of 24 [Assumed], with one 90-minute rest each, staggered |
| 6 | Dynamic TTS for prices and bid offers | Removed: numbers are spoken digit by digit from fixed clips. Simpler and immune to TTS outages; slightly less natural |
| 7 | Native Kannada/Hindi reviewer | [Assumed] someone on the team or a friend reachable by phone. If not, ship fewer, simpler lines |
| 8 | Exotel credentials belong to Nahyan | He shares the keys privately with Darshan; the account stays in his name. Only Darshan can run ngrok (his laptop) |
| 9 | Exotel trial availability within the 24 hours | [Assumed] signup works instantly (the trial needs no KYC to start). If not, the phone leg is simulated |
| 10 | Admin role | Seeded buyer row `admin@demo.test`, treated as admin by Darshan's auth, to avoid an extra table |
| 11 | Districts and crops | Mandya and Mysuru, ragi / paddy / maize only (C3) [Assumed]; Mysuru's spelling in the price feed must be read from the A1 samples |
| 12 | Gemini tools | Gemini 3.1 Pro in AI Chat for single files; Antigravity agents for one folder at a time; Opus credits saved for integration bugs |
| 13 | Venue coordinates for the demo collection point | Taken on site at H0 by Anirudh (phone GPS) and passed to A2 as `venue_lat`/`venue_lon` |
| 14 | Team phone numbers | The 4 team phones become seeded farmers 1–4 (env `TEAM_PHONES`) and are the Exotel whitelist |

### 12.1 Plan coverage (every plan module and roadmap item, assigned once or cut)

| Plan item | Task | | Plan item | Task |
|---|---|---|---|---|
| §7.0 repo, compose, env | D1 | | §7.6 bidding, queue, BID_OFFER | D6 |
| §7.1 simulator adapter | D2 | | §7.6 outbound call retries, budget | D6 |
| §7.1 simulator page | H5 | | §7.7 buyer dashboard | N2, N3, N4, N5 |
| §7.1 Exotel adapter | D7 (code), N1, N6, N7 (account, flow, tests) | | §7.8 agent PWA | A5 (UI), D5 (endpoint) |
| §7.1 Asterisk | CUT (stretch list) | | §7.9 triage | D3 (ticket, code), D5 (endpoints), A5 (UI); proxy listing CUT |
| §7.2 engine, flows | D2 | | Ops monitor (plan E9) | A6 (UI), D5 (endpoints) |
| §7.2 debounce, resume, idempotency | D3 | | Plan §13 tests | Unit/integration in D2–D6; acceptance A7; load: stretch |
| §7.3 prompts, TTS, FFmpeg | H1, H2, H3 | | Plan §10 demo plan | D9, D10, N9, H9, A9; video H7; backup N8 |
| §7.3 audio mixer | H4 | | Plan §11 economics | A8 |
| §7.3 dynamic TTS | CUT (digit-by-digit) | | Plan §14 Q&A | H8, N9, A9, Darshan |
| §7.4 price ingestion, AFPP | A1, A3 | | Plan roadmap day 1 contracts | D1 + §3 of this file |
| §7.4 crop calendar | A2 (static) | | Roadmap day 8 payment/pickup/ledger | Payment buttons D5/N4/A5; pickup and ledger CUT |
| §7.5 clustering, farmer import | D4; import replaced by A4 seed | | Roadmap day 11 cloud mirror | CUT |
| Reference and demo data | A2, A4 | | Roadmap Marathi | CUT (stretch) |
