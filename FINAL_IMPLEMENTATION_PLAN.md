# Annadata Dhwani (अन्नदाता ध्वनि): Final Implementation Plan

**Version:** 1.0, 13 November 2026 · **Team:** Debug4X (4 people) · **Event:** Seva First Innovation Challenge 2026, theme "Samriddh Annadata, Samriddh Bharat"

**How to read the tags.** `[Verified]` = read on the primary source during research on 12–13 Nov 2026. `[Likely]` = from a secondary source or a search snippet of the primary source. `[Assumed]` = our own estimate or design judgement, not checked against any source. Section 15 lists every URL.

**Phase 0 inventory.** There is no `plans/` folder. Three plan documents were found in the project root and all three were read in full:

| # | File | One-line summary |
|---|---|---|
| P1 | `annadata_dhwani_architecture_blueprint.md` | "Production" architecture: Exotel, Bhashini, IndicWhisper, Geo-DID numbers, AgriStack, escrow, ONDC. Ambitious, with several unverifiable claims. |
| P2 | `annadata_dhwani_2_0_24_hour_hackathon_execution_plan.md` | 24-hour hackathon plan: Exotel trial, ngrok, Supabase, Upstash, edge-tts, Next.js, roles for 3–4 people. |
| P3 | `Now as we have all the details give me a detailed.md` | PRD + TRD: Twilio trial plus browser simulator ("dual mode"), schema, 9 vulnerabilities, 7-day phased build, `prewarm_audio.py`. |

**Timeline assumption.** The brief refers to "the number of days in Section 0", but no Section 0 was supplied. The event is not a timed hackathon: submissions closed on 6 Nov 2026 and the finale falls between 30 Nov and 17 Dec 2026 [Verified on the official portal; the exact finale dates conflict between sources]. This plan therefore assumes a **14-day build, 14–27 Nov 2026** [Assumed], with a working end-to-end demo at Day 7 so that a shorter window still produces a demo. Confirm with your institution's coordinator that the entry was lodged before 6 Nov.

---

## 1. Executive summary

1. We are building a voice-and-keypad produce marketplace that any button phone can use: a farmer gives a missed call, the system calls back free of charge, speaks in Kannada, Hindi or Marathi, and the farmer types crop, quantity and price on the keypad.
2. It is for members of Farmer Producer Organisations (FPOs) who have no smartphone, and for the FPO itself, which gets a tool to pool 150–400 kg lots at its collection point into 2–5 tonne truckloads that wholesale buyers will actually bid for.
3. During the call the farmer hears yesterday's mandi price for their district and a fair farm-gate floor; if they type a price below the floor they are warned and can raise it with one key.
4. Buyers bid on pooled, FPO-graded clusters in a live web dashboard; the winning bid triggers automatic calls in which each farmer presses 1 to accept or 2 to reject, and the deal closes only if enough quantity accepts.
5. The jury demo runs end to end at zero cost on one laptop: a real ₹1,000 phone rings through the Exotel trial, a browser phone simulator with real 8 kHz audio is the always-available fallback, and we inject a dropped call, keypad bounce, a duplicate webhook and a Redis flush live to show the system recovering.

---

## 2. Merge decisions

### 2.1 What the research overturned

These claims in the original plans are wrong or unsupported and are removed from all team material:

| Claim in the plans | Finding | Tag |
|---|---|---|
| Exotel returns `nXML` with `<Play>`/`<Gather>` (P1, P2) | No such format in Exotel's documentation. Flows are built from applets; a Gather applet calls our URL and we return JSON. | [Verified] |
| Exotel gives "<40 ms" webhook latency (P1) | No such figure is published by Exotel. | [Verified absence] |
| Exotel trial has ₹1,000 credit (P2) | 7-day trial, ₹500 credit, calls only to 10 whitelisted numbers. | [Verified] |
| Twilio trial gives ~$15.50 and an Indian number (P3) | The trial is now free units (about 75 voice minutes), 30 days, 5 verified recipients, and Twilio lists only toll-free Indian numbers. | [Verified] |
| "Strict RFC-2833 DTMF from the farmer's phone" (P1) | A GSM handset signals DTMF to the network out of band; the network regenerates the tone. RFC 2833/4733 exists only on SIP legs. With Exotel we receive digits over HTTP and never see RTP. | [Likely] |
| "100 % numeric capture accuracy" (P1) | Not achievable as stated: double digits and wrong keys still occur. Accuracy comes from range checks and spoken readback. | [Assumed] |
| "~28 % WER on numerals over 8 kHz" (P1, P3) | No source found. The closest citable figure is IndicWhisper at 26.8 % WER on Hindi phone-recorded speech (Gramvaani), which is not numeral-specific. | [Verified for the 26.8 figure] |
| 250 ms DTMF debounce (P1) | Too long (it would delete the second `0` in `3800`) and impossible on Exotel's Gather, which returns a finished string. | [Assumed] |
| Webhook HMAC verification (P3) | Twilio-only. Exotel documents no webhook signature. | [Verified absence] |
| Flat 6 % logistics deduction (brief) | Market fee is 0.6 % (Karnataka) and 0.75 % (Maharashtra) and is paid by the buyer; the farmer's real costs are per-quintal transport and handling. | [Verified for the fee rates] |
| MSP as a price fallback (implied) | Mandya ragi modal was ₹3,565 on 12 Nov 2026 against an MSP of ₹5,205. An MSP floor would make every listing unsellable. | [Verified] |
| "35–40 million small farmers on 2G phones" (all) | No source states this. It is our estimate (section 14, Q13). | [Assumed] |
| Platform-run escrow with IMPS/e-RUPI payout (P1) | Pooling buyer money needs RBI Payment Aggregator authorisation (net worth ₹15 crore). A startup cannot issue e-RUPI. | [Likely] |
| SMS receipts (P1, P3) | Need DLT registration, about ₹5,900. Not free. | [Likely] |

### 2.2 Feature scoring and decisions

Scores are 1–5, where 5 is best in every column: **F** feasibility for 4 students in 14 days, **I** impact on the core problem, **J** jury impact, **C** cost (5 = free), **D** dependency safety (5 = no approvals or third parties).

| # | Feature or decision | Source | F | I | J | C | D | Decision | Reason |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Missed call → free callback | P1 P2 P3 | 4 | 5 | 4 | 3 | 3 | KEEP | The core access mechanism. Real on the Exotel trial, simulated otherwise. |
| 2 | Exotel as the PBX | P1 P2 | 3 | 4 | 4 | 2 | 2 | SIMPLIFY | One adapter behind an interface; trial only. No paid plan in the free path. |
| 3 | Twilio trial | P3 | 3 | 2 | 2 | 3 | 3 | CUT (contingency only) | No Indian missed-call number. Kept as a documented fallback if the Exotel trial is refused. |
| 4 | Browser phone simulator | P3 | 5 | 3 | 4 | 5 | 5 | KEEP, upgrade | Becomes the primary development and fallback path, with 8 kHz audio, bounce and drop injection. |
| 5 | Asterisk + softphone | brief | 3 | 1 | 4 | 5 | 4 | SIMPLIFY (stretch) | Real SIP and RFC 4733 for the jury, but first item below the cut line. |
| 6 | DTMF-only uplink, TTS downlink | all | 5 | 5 | 5 | 5 | 5 | KEEP | The central engineering idea; restated honestly (section 2.1). |
| 7 | Bhashini TTS | P1 | 4 | 4 | 4 | 5 | 3 | KEEP | Free for proof-of-concept use. Used only to pre-generate audio, never inside a call. |
| 8 | edge-tts | P2 P3 | 5 | 3 | 1 | 5 | 2 | SIMPLIFY | Emergency fallback only: unofficial Microsoft endpoint, broke in Jan 2026. |
| 9 | Pre-generated, hashed audio cache | P2 P3 | 5 | 4 | 4 | 5 | 5 | KEEP | Removes TTS latency and outage risk from the call path. |
| 10 | FFmpeg 8 kHz conversion, loudness, band-pass | P1 | 5 | 3 | 5 | 5 | 5 | KEEP | Cheap and demonstrates network physics. |
| 11 | IndicWhisper "key 9" voice crop entry | P1 P3 | 2 | 2 | 2 | 5 | 3 | CUT | Needs GPU-class latency and 16 kHz audio; contradicts the DTMF thesis. Replaced by "9 = more crops, 0 = helper". |
| 12 | "AI seasonal crop predictor" | P1 P3 | 5 | 4 | 3 | 5 | 5 | SIMPLIFY | It is a lookup table, not AI. Renamed "seasonal shortlist", built from 3 years of mandi arrivals, personalised by the farmer's last crop. |
| 13 | Redis session with 30-min TTL and resume | all | 5 | 4 | 5 | 5 | 5 | KEEP | Plus a Postgres checkpoint so a Redis flush does not lose sessions. |
| 14 | Redis Lua locks | P1 | 4 | 3 | 5 | 5 | 5 | SIMPLIFY | Lua for session compare-and-set, rate limits and the per-farmer call lock. Money and bid correctness moved to Postgres constraints. |
| 15 | DTMF debounce 250 ms | P1 | 4 | 3 | 5 | 5 | 5 | REPLACE | 120 ms same-digit window on per-digit paths; range checks and readback everywhere. |
| 16 | Rate limiting missed calls | P1 P2 P3 | 5 | 3 | 4 | 5 | 5 | KEEP | 3 per 10 minutes and 6 per day per number, plus a global daily budget. |
| 17 | Agmarknet price via data.gov.in | P2 P3 | 5 | 5 | 4 | 5 | 3 | KEEP | Live-tested. Daily ingestion with a fallback chain. |
| 18 | AFPP guardrail, flat 6 % | brief | 5 | 5 | 4 | 5 | 5 | REPLACE | Per-district rule: 2 % margin plus ₹/quintal transport and handling. |
| 19 | "Press 1 to raise to the floor" | P1 P3 | 5 | 5 | 4 | 5 | 5 | KEEP | |
| 20 | Quantity and price sanity caps | P3 | 5 | 3 | 4 | 5 | 5 | KEEP | Per-crop bounds table instead of AgriStack acreage. |
| 21 | PostGIS `ST_DWithin` clustering | all | 5 | 5 | 4 | 5 | 5 | SIMPLIFY | Anchor clusters to fixed FPO collection points, not a drifting centroid. |
| 22 | H3 hexagons | P1 | 3 | 1 | 2 | 5 | 4 | CUT | Adds nothing over `ST_DWithin` at pilot scale; not available on Supabase. |
| 23 | Over-subscription buffer 15–20 % | P1 | 4 | 3 | 3 | 5 | 5 | REPLACE | The bid carries `min_qty_qtl`; a deal closes if accepted quantity meets it. |
| 24 | Geo-DID virtual numbers per taluk | P1 | 1 | 2 | 2 | 1 | 1 | CUT | Each number is a paid rental. |
| 25 | FPO CSV pre-seeding | P1 | 5 | 5 | 3 | 5 | 4 | KEEP | The only location source. Unknown callers go to the helper queue. |
| 26 | LGD fuzzy join, telecom-circle prefix, spoken village name | P1 | 2 | 2 | 1 | 5 | 3 | CUT | LGD coordinates unconfirmed; prefix is unreliable after number portability; spoken names need ASR. |
| 27 | AgriStack Farmer ID link | P1 P3 | 1 | 1 | 2 | 5 | 1 | CUT | No public self-serve API found. |
| 28 | React dashboard with live updates | all | 5 | 4 | 4 | 5 | 5 | KEEP | React + Vite; FastAPI WebSocket with replay by sequence number. |
| 29 | Supabase Realtime as the event bus | P2 | 4 | 2 | 2 | 5 | 3 | CUT | Would bypass the backend's access rules and tie the demo to a cloud service. |
| 30 | Per-farmer counter-bid by keypad | P1 P3 | 2 | 2 | 3 | 3 | 5 | CUT | N farmers × M rounds of calls is slow, costly and confusing. Replaced by an ascending auction on the web and one accept/reject call. |
| 31 | Outbound accept/reject call | all | 4 | 5 | 5 | 3 | 3 | KEEP | With a second "press 1 to confirm" step. |
| 32 | FPO verification PWA with geo-tagged photo | all | 4 | 4 | 4 | 5 | 5 | KEEP | Live camera capture plus browser geolocation; EXIF is not relied on. |
| 33 | ₹50 per cluster agent payout | P1 P3 | 5 | 3 | 3 | 5 | 5 | SIMPLIFY | Recorded as a ledger entry; paid by the FPO outside the system. |
| 34 | Masked triage bridge | P1 | 3 | 4 | 4 | 3 | 2 | SIMPLIFY | Queue, proxy entry and farmer confirmation call are built. The masked call is real only on the Exotel trial, otherwise simulated. |
| 35 | Reverse verbal code | P1 | 5 | 3 | 3 | 5 | 5 | KEEP, fix | The IVR tells the farmer the code; single use, 24-hour expiry. |
| 36 | Proxy entry with farmer voice lock | P1 | 4 | 4 | 4 | 4 | 4 | KEEP | The main control against agent tampering. |
| 37 | Escrow, IMPS, e-RUPI settlement | P1 | 1 | 3 | 2 | 1 | 1 | REPLACE | FPO is seller of record; buyer pays the FPO directly; "no payment, no loading". |
| 38 | DLT SMS receipts | P1 P3 | 2 | 2 | 1 | 1 | 1 | REPLACE | Spoken listing number, and status on the next missed call. |
| 39 | ONDC / eNAM / Beckn sync | P1 P3 | 1 | 2 | 2 | 5 | 1 | CUT | Roadmap slide only. |
| 40 | AES-256 at rest, RBAC | P1 | 3 | 2 | 3 | 5 | 5 | SIMPLIFY | Role checks in the API, numbers masked in every buyer-facing response; disk encryption left to the host. |
| 41 | 2 % buyer cancellation penalty from escrow | P1 | 1 | 2 | 1 | 1 | 1 | REPLACE | Strike system: 3 no-shows suspends the buyer. |
| 42 | Seeded demo data | P2 P3 | 5 | 2 | 3 | 5 | 5 | KEEP | Clearly labelled as seed data on screen. |
| 43 | Supabase + Upstash + ngrok as the main stack | P2 P3 | 4 | 2 | 2 | 5 | 2 | REPLACE | Local Docker Compose is primary; the cloud is a mirror and backup. |
| 44 | GitHub Actions keep-alive cron | P3 | 5 | 1 | 1 | 5 | 4 | SIMPLIFY | UptimeRobot ping on the cloud mirror only. |
| 45 | Next.js | P2 | 4 | 2 | 1 | 5 | 5 | REPLACE | Plain React + Vite: one static bundle served by FastAPI, no second server. |

Where the plans disagreed: **Exotel vs Twilio** → Exotel trial (it has a native missed-call number in India), behind an adapter. **Supabase Realtime vs SSE vs WebSocket** → backend WebSocket. **Next.js vs React** → React + Vite. **edge-tts vs Bhashini** → Bhashini first, edge-tts as fallback. **24 hours vs 7 days** → 14 days with a Day-7 demo.

### 2.3 Removed, and why

- **IndicWhisper voice entry, spoken village names:** unreliable on 8 kHz audio and not buildable on free CPU hosting.
- **Geo-DID numbers, DLT SMS, escrow, e-RUPI, paid Exotel plan:** cost money or need regulatory approval.
- **AgriStack, LGD join, ONDC/eNAM sync:** depend on access we cannot get.
- **H3, over-subscription buffer, per-farmer counter-bids, Supabase Realtime, Next.js:** complexity without benefit at this scale.
- **Claims:** "<40 ms", "nXML", "100 % accuracy", "28 % WER", "structurally impossible to charge the farmer", "AI predictor".

---

## 3. Final architecture

### 3.1 Component diagram

```mermaid
flowchart TB
  subgraph Phones["Farmer side"]
    FP["Button phone (real GSM)"]
    SIM["Browser phone simulator<br/>8 kHz audio, bounce and drop switches"]
    SP["Softphone (stretch)"]
  end

  subgraph Tel["Telephony adapters (one interface)"]
    EX["Exotel adapter<br/>trial account, HTTP webhooks"]
    SA["Simulator adapter<br/>WebSocket, per-digit events"]
    AS["Asterisk adapter (stretch)<br/>SIP, RFC 4733"]
  end

  subgraph Core["FastAPI backend (one process + one worker)"]
    ENG["Call engine<br/>state machine"]
    PRC["Price service<br/>AFPP floor"]
    CLU["Clustering service"]
    BID["Bidding service"]
    JOB["Call-job worker<br/>SKIP LOCKED queue"]
    WS["WebSocket hub"]
    AUD["Audio service<br/>mix + static files"]
  end

  subgraph Data["State"]
    PG[("PostgreSQL + PostGIS<br/>system of record, outbox")]
    RD[("Valkey / Redis<br/>sessions, locks, limits")]
    FS[("Disk: audio cache, photos")]
  end

  subgraph Offline["Offline jobs"]
    TTS["TTS pipeline<br/>Bhashini → FFmpeg"]
    ING["Daily price ingestion<br/>data.gov.in"]
  end

  subgraph Web["React app (one bundle)"]
    BUY["Buyer dashboard"]
    PWA["FPO agent PWA"]
    OPS["Ops monitor"]
  end

  FP <--> EX
  SIM <--> SA
  SP <--> AS
  EX & SA & AS --> ENG
  ENG --> PRC & CLU
  ENG <--> RD
  ENG --> PG
  CLU --> PG
  BID --> PG
  BID --> JOB
  JOB --> EX & SA & AS
  PG --> WS
  RD -. pub/sub .-> WS
  WS --> BUY & PWA & OPS
  BUY & PWA --> BID
  TTS --> FS
  ING --> PG
  AUD --> FS
  EX & SA -. fetch audio .-> AUD
```

Design rules that the rest of the plan follows:
- **One engine, three adapters.** Every telephone path calls `engine.handle_event()`. The simulator is not a mock of the product; it is a second front end to the same state machine.
- **Postgres is the truth, Redis is disposable.** Any fact that involves consent, a listing, a bid or a deal is committed in Postgres under a constraint.
- **No network call to a third party inside a telephony webhook.** Prices and audio are prepared beforehand.
- **Outbound calls go through a durable queue** with retries, backoff, calling hours and a daily budget.

### 3.2 Data flow for each main workflow

**A. Farmer ingress (missed call → callback)**
1. The farmer dials the platform number and hears it ring once or twice; the provider hangs up before answering, so no call is charged [Likely: the call is never answered; Exotel documents auto-hangup after 1–2 rings].
2. The adapter receives the missed-call event, collapses duplicates (20 s), and checks the roster: a registered `ACTIVE` farmer continues; an unknown number gets at most one callback per day that says "you are not registered, a helper will contact you" and opens a triage ticket.
3. `allow_callback.lua` enforces 3 per 10 minutes, 6 per day and the global budget. If allowed, a `CALLBACK` job is inserted (`dedupe_key = cb:{phone}:{minute}`).
4. The worker takes the job, acquires `lock:call:{phone}`, dials, and the engine starts or resumes the `LISTING` flow.

**B. Listing**
`LANG` and `CONSENT` (first call only) → `CROP` (3 crops for the district and month, last-used crop first) → `QTY` → `QTY_CONFIRM` → `PRICE` → (`GUARD`) → `FINAL` → commit → `DONE`. Location is never asked: it comes from the FPO roster.

**C. AFPP guardrail**
1. A daily job stores `price_floors` for each pilot district and crop.
2. `PRICE` speaks: "Mandya mandi price yesterday was 3,565. Fair farm-gate price is 3,430."
3. If the typed price is below `afpp × 0.97`, `GUARD` offers 1 = raise to the floor, 2 = keep, 3 = re-enter. The choice is stored in `listings.guardrail`.
4. With no usable price data the engine says so, skips the guardrail and stores `NO_PRICE_DATA`.

**D. Clustering**
On commit, one transaction: lock `(collection_point, crop)`, find or create the joinable cluster, insert the listing, update totals. At 20 quintals (2 t) the cluster becomes `READY` and the FPO agent gets a verification task. A `READY` cluster keeps accepting lots until the agent verifies it; verification freezes membership, and the next lot for that pickup point and crop opens a new cluster. A cluster that passes 50 quintals (5 t) is flagged urgent in the agent's task list.

**E. FPO verification**
The agent opens the PWA at the collection point, takes a live photo of the sample, enters grade and optional moisture. The server checks the reported position is within 500 m of the collection point and the capture is under 10 minutes old. Success moves the cluster to `BIDDING` and opens the auction window (24 hours in the pilot, 3 minutes in the demo).

**F. Buyer bidding**
Approved buyers see clusters live. A bid states price per quintal and the minimum quantity the buyer will take. Each bid must beat the best by at least ₹10. Farmers are not called during the auction.

**G. Outbound accept/reject**
At window close the best bid becomes `CONFIRMING`. One `BID_OFFER` job per listing is queued. Each farmer hears the offer and their own asking price, presses 1 then 1 again to accept, or 2 to reject. When every response is in, or after 2 hours (demo: 90 seconds), the round resolves: accepted quantity ≥ `min_qty_qtl` creates a deal; otherwise the bid fails and the cluster returns to `BIDDING` once, then `NO_BID`.

**H. Triage bridge**
Three failed calls in 24 hours, the `0` key, or an unknown caller opens a ticket. The IVR tells the farmer a two-digit code. An agent claims the ticket, starts the masked call (both sides see the platform number), says the code, and may enter the listing on the farmer's behalf. The listing stays `PENDING_CONFIRM` until the farmer confirms it on an automatic call.

**I. Settlement handoff**
The FPO is the seller of record. The deal note shows the FPO's payee details and the amount. The buyer pays the FPO directly and reports the reference; the FPO agent confirms receipt; only then can pickup be recorded ("no payment, no loading"). At pickup the agent enters weighed quantities per lot; the FPO pays its members as it already does. The platform records a 1.5 % fee owed by the buyer and a ₹50 verification fee owed to the FPO agent. The platform never touches trade money.

### 3.3 Sequence: farmer call

```mermaid
sequenceDiagram
  autonumber
  participant F as Farmer phone
  participant P as Provider (Exotel / simulator)
  participant A as Adapter
  participant E as Call engine
  participant R as Redis
  participant D as Postgres

  F->>P: Dial platform number (rings, not answered)
  P->>A: missed-call event (phone)
  A->>R: SET miss:{phone} NX EX 20
  A->>D: farmer lookup by phone
  A->>R: EVAL allow_callback.lua
  A->>D: INSERT call_jobs (CALLBACK, dedupe_key)
  Note over D: worker: SELECT … FOR UPDATE SKIP LOCKED
  D-->>A: job
  A->>R: SET lock:call:{phone} token NX PX 300000
  A->>P: place outbound call
  P->>F: Ring, farmer answers
  P->>A: prompt request (call_id)
  A->>E: handle_event(START)
  E->>R: GET sess:{phone}
  alt session found (dropped earlier)
    E-->>A: Action("welcome back" + saved state prompt)
  else no session
    E->>D: rehydrate from call_sessions or create
    E-->>A: Action(first prompt)
  end
  A-->>P: audio URL, digits to collect, timeout
  P->>F: Play 8 kHz prompt
  F->>P: Keypad digits
  P->>A: digits (call_id, event_id)
  A->>R: SET evt:{call_id}:{event_id} NX
  A->>E: handle_event(DIGITS)
  E->>R: EVAL session_cas.lua (version+1)
  E->>D: upsert call_sessions, insert dtmf_events
  E-->>A: next Action
  Note over F,P: … CROP → QTY → PRICE → GUARD → FINAL …
  F->>P: 1 (final confirm)
  P->>A: digits
  A->>E: handle_event(DIGITS)
  E->>D: BEGIN; advisory lock; find/create cluster; INSERT listing; UPDATE cluster; INSERT events; COMMIT
  D-->>E: listing code
  E->>R: PUBLISH ad:events
  E-->>A: Action(DONE prompt, hangup)
  P->>F: "Listed. Your number is 4-2-7."
  P->>A: call ended
  A->>R: EVAL release_lock.lua
```

### 3.4 Sequence: buyer bid to deal

```mermaid
sequenceDiagram
  autonumber
  participant B as Buyer dashboard
  participant API as FastAPI
  participant D as Postgres
  participant W as Call-job worker
  participant F as Farmers (n phones)
  participant AG as FPO agent PWA

  B->>API: POST /api/clusters/{id}/bids (Idempotency-Key)
  API->>D: BEGIN; SELECT cluster FOR UPDATE; check status=BIDDING and price ≥ best+10
  API->>D: INSERT bid (LEADING); previous best → OUTBID; UPDATE cluster.best_bid_id; INSERT events; COMMIT
  D-->>B: WebSocket bid.placed, cluster.updated (all buyers)
  Note over API,D: auction window ends (scheduler or admin close)
  API->>D: BEGIN; cluster → CONFIRMING; best bid → CONFIRMING; INSERT bid_responses (PENDING) per listing; INSERT call_jobs (BID_OFFER) per listing; COMMIT
  loop each job, max 5 at once
    W->>D: claim job (SKIP LOCKED)
    W->>F: outbound call, OFFER prompt
    F-->>W: 1 then 1 (accept) or 2 (reject)
    W->>D: UPDATE bid_responses SET response=… WHERE response='PENDING'
    D-->>B: WebSocket bid.confirming (accepted / rejected / pending quintals)
  end
  alt accepted_qtl ≥ min_qty_qtl
    API->>D: BEGIN; INSERT deal; bid → DEAL; cluster → DEAL; accepting listings → ACCEPTED; the rest re-pooled; COMMIT
    D-->>B: deal.created (FPO payee details, amount)
    D-->>AG: task.created (PICKUP)
    B->>API: POST /deals/{id}/payment-reported
    AG->>API: POST /deals/{id}/payment-confirmed
    AG->>API: POST /deals/{id}/pickup (weights)
  else not enough accepted
    API->>D: bid → FAILED; cluster → BIDDING (first time) or NO_BID
    D-->>B: bid.failed
  end
```

---

## 4. Tech stack (all free)

Every row is free for development, the demo and a small pilot. "Limit hit" says what happens and what we do.

| Component | Role | Licence or free-tier limit | Why it is enough | If the limit is hit |
|---|---|---|---|---|
| Python 3.12, FastAPI, Uvicorn | Backend, webhooks, WebSocket | MIT / BSD [Assumed, standard] | One process handles hundreds of concurrent calls' worth of webhooks | None |
| asyncpg | Postgres driver | Apache-2.0 [Assumed] | Async, supports `SKIP LOCKED` and advisory locks | None |
| PostgreSQL 16 + PostGIS 3.4 (`postgis/postgis` image) | System of record, spatial queries, job queue, outbox | PostgreSQL licence / GPL-2 [Assumed] | Pilot data is a few MB | None locally |
| Valkey 8 (`valkey/valkey` image) | Sessions, locks, rate limits, pub/sub | BSD-3 [Likely]. Chosen over Redis 8, which is tri-licensed RSAL/SSPL/AGPL [Verified] | Protocol-compatible with `redis-py`; Lua supported | None locally |
| redis-py | Client | MIT [Assumed] | | |
| Docker Desktop (or Podman) | Runs Postgres and Valkey | Free for education and personal use [Verified] | Two containers | Use Podman |
| React 18, Vite, Tailwind, vite-plugin-pwa | Buyer dashboard, agent PWA, simulator, ops view | MIT [Assumed] | One static bundle served by FastAPI | None |
| Leaflet + OpenStreetMap tiles | Cluster map | BSD-2; tiles free for light use with attribution, no SLA [Verified] | A few hundred tile requests | Map panel hides; the list view is unaffected |
| Bhashini pipeline API | Pre-generating prompts in kn, hi, mr | Free, "for the purposes of PoC only" [Verified]; rate limits undocumented [Assumed] | About 400 clips generated once, plus about 50 a day | Fall back to Indic Parler-TTS offline or edge-tts; cached audio keeps working |
| AI4Bharat Indic Parler-TTS | Offline TTS fallback | Apache-2.0, gated download [Verified]; slow on CPU [Assumed] | Batch generation only | Use edge-tts |
| edge-tts | Emergency TTS fallback | LGPL-3; unofficial Microsoft endpoint, no SLA [Verified] | Demo only | Use cached audio |
| indic-numtowords | Numbers to words in hi, kn, mr | MIT [Verified] | Used when building price sentences | Digit-by-digit clips |
| FFmpeg | 8 kHz mono conversion, band-pass, loudness | LGPL/GPL [Verified] | Local tool | None |
| data.gov.in mandi API (resources `9ef84268…` and `35985678…`) | Daily prices and 3-year history | Free; sample key returns 10 rows per call; registered key lifts that [Verified for the cap; registration terms Likely] | About 30 calls a day | Use the last stored price (fallback chain) |
| Exotel trial | Real GSM calls in the demo | 7 days, ₹500 credit, 10 whitelisted numbers, all APIs [Verified] | About 250 call-minutes at an assumed ₹1–2 per minute; the demo needs under 30 | Switch to the simulator |
| Browser phone simulator (ours) | Development, tests, demo fallback | Our code | Unlimited | — |
| Asterisk + Linphone (stretch) | Real SIP/RTP path | GPL-2 / GPL-3 [Assumed] | Local | Drop it |
| ngrok free | HTTPS URL for Exotel webhooks and for phones using the PWA | 1 static domain, 20,000 requests a month, 1 GB out [Verified] | A demo uses a few hundred requests | `cloudflared` quick tunnel (URL changes) |
| pytest, httpx, Locust | Tests and load | MIT [Assumed] | | |
| **Cloud mirror (backup only)** | | | | |
| Render free web service (Singapore) | Hosts the backend | Sleeps after 15 min idle, about 1 min wake, 750 h a month, WebSockets work [Verified] | Backup demo | Wake it 10 minutes before; UptimeRobot ping every 5 min |
| Neon free (Singapore) | Postgres + PostGIS | 1 GB per project, scale-to-zero after 5 min, PostGIS supported [Verified] | Pilot data is tiny | Supabase free (500 MB, pauses after 7 idle days, Mumbai region) [Verified] |
| Upstash Redis free (Mumbai) | Redis | 500,000 commands a month, 256 MB [Verified] | A call uses about 60 commands, so roughly 8,000 calls a month | In-process fallback dict for sessions |
| Cloudflare Pages | Static front end | 500 builds a month [Verified] | | GitHub Pages |
| UptimeRobot free | Keep-alive ping | 50 monitors, 5-min interval [Verified] | | cron-job.org |

**Paid in production, stated plainly.** A real launch cannot be free: an Exotel plan starts at ₹9,999 for 5 months [Verified], DLT registration is about ₹5,900 [Likely], per-minute call charges apply, and Bhashini's free API is for proof of concept only [Verified]. Section 11 puts these into the unit economics.

---

## 5. Data model

PostgreSQL is the system of record for everything that has money or consent attached. Redis (Valkey) holds only state that is safe to lose: live call sessions (checkpointed to Postgres), locks, rate-limit counters and caches.

### 5.1 PostgreSQL + PostGIS schema (DDL)

Run as `db/001_schema.sql`. Works on `postgis/postgis:16-3.4` (local), Supabase and Neon. `gen_random_uuid()` is built in from PostgreSQL 13.

```sql
CREATE EXTENSION IF NOT EXISTS postgis;

-- ---------- reference data ----------
CREATE TABLE districts (
  code          text PRIMARY KEY,            -- 'KA-MANDYA'
  name          text NOT NULL,
  state         text NOT NULL,               -- 'Karnataka'
  agmark_state  text NOT NULL,               -- spelling used by the price API
  agmark_district text NOT NULL,
  default_lang  text NOT NULL CHECK (default_lang IN ('kn','hi','mr'))
);

CREATE TABLE crops (
  code          text PRIMARY KEY,            -- 'ragi'
  name_en       text NOT NULL,
  agmark_name   text NOT NULL,               -- commodity name in the price API
  msp           numeric(10,2),               -- Rs/quintal, NULL if no MSP
  max_listing_qtl numeric(6,2) NOT NULL DEFAULT 50,
  min_price     numeric(10,2) NOT NULL,      -- hard sanity bounds for keypad entry
  max_price     numeric(10,2) NOT NULL
);

CREATE TABLE crop_calendar (                 -- the "seasonal shortlist"
  district_code text REFERENCES districts(code),
  month         smallint CHECK (month BETWEEN 1 AND 12),
  crop_code     text REFERENCES crops(code),
  rank          smallint NOT NULL,           -- 1 = most likely
  PRIMARY KEY (district_code, month, crop_code)
);

CREATE TABLE deduction_rules (               -- AFPP inputs, one row per district
  district_code     text PRIMARY KEY REFERENCES districts(code),
  transport_per_qtl numeric(8,2) NOT NULL,
  handling_per_qtl  numeric(8,2) NOT NULL,
  pct_deduction     numeric(5,4) NOT NULL,   -- e.g. 0.0200 = 2 %
  source_note       text NOT NULL
);

-- ---------- actors ----------
CREATE TABLE fpos (
  id   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL,
  district_code text NOT NULL REFERENCES districts(code),
  payee_details text                          -- shown to buyer on the deal note (UPI ID / account)
);

CREATE TABLE collection_points (
  id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  fpo_id  uuid NOT NULL REFERENCES fpos(id),
  name    text NOT NULL,
  district_code text NOT NULL REFERENCES districts(code),
  geog    geography(Point,4326) NOT NULL
);
CREATE INDEX collection_points_geog_gix ON collection_points USING GIST (geog);

CREATE TABLE farmers (
  id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  phone     text NOT NULL UNIQUE,            -- E.164, '+9198...'
  name      text NOT NULL,
  fpo_id    uuid NOT NULL REFERENCES fpos(id),
  village   text NOT NULL,
  district_code text NOT NULL REFERENCES districts(code),
  geog      geography(Point,4326) NOT NULL,  -- village centroid from FPO roster
  collection_point_id uuid NOT NULL REFERENCES collection_points(id),
  lang      text CHECK (lang IN ('kn','hi','mr')),      -- NULL until chosen
  consent_version text,                      -- NULL until consent given
  consent_at timestamptz,
  status    text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','BLOCKED')),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX farmers_geog_gix ON farmers USING GIST (geog);

CREATE TABLE agents (
  id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  fpo_id   uuid NOT NULL REFERENCES fpos(id),
  name     text NOT NULL,
  phone    text NOT NULL UNIQUE,
  pin_hash text NOT NULL,
  active   boolean NOT NULL DEFAULT true
);

CREATE TABLE buyers (
  id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  org_name  text NOT NULL,
  email     text NOT NULL UNIQUE,
  password_hash text NOT NULL,
  phone     text NOT NULL,
  license_no text,                           -- APMC trader / GST number, checked by admin
  status    text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','APPROVED','SUSPENDED')),
  strikes   smallint NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- ---------- prices ----------
CREATE TABLE mandi_prices (
  id bigserial PRIMARY KEY,
  district_code text NOT NULL REFERENCES districts(code),
  crop_code  text NOT NULL REFERENCES crops(code),
  market     text NOT NULL,
  price_date date NOT NULL,
  min_price  numeric(10,2), max_price numeric(10,2),
  modal_price numeric(10,2) NOT NULL,
  source     text NOT NULL,                  -- 'data.gov.in' | 'seed'
  fetched_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (district_code, crop_code, market, price_date)
);

CREATE TABLE price_floors (                  -- one row per district x crop x day
  district_code text NOT NULL REFERENCES districts(code),
  crop_code  text NOT NULL REFERENCES crops(code),
  as_of      date NOT NULL,                  -- the day the floor was computed for
  price_date date,                           -- date of the newest price used
  modal_price numeric(10,2) NOT NULL,
  afpp       numeric(10,2) NOT NULL,
  basis      text NOT NULL CHECK (basis IN ('DISTRICT_FRESH','DISTRICT_7D','STATE_7D')),
  PRIMARY KEY (district_code, crop_code, as_of)
);

-- ---------- marketplace ----------
CREATE TABLE clusters (
  id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code      serial UNIQUE,                   -- short human id, 'C-104'
  collection_point_id uuid NOT NULL REFERENCES collection_points(id),
  crop_code text NOT NULL REFERENCES crops(code),
  status    text NOT NULL DEFAULT 'OPEN' CHECK (status IN
            ('OPEN','READY','BIDDING','CONFIRMING','DEAL','CLOSED','NO_BID','FAILED')),
  total_qtl numeric(8,2) NOT NULL DEFAULT 0,
  listing_count int NOT NULL DEFAULT 0,
  min_ask   numeric(10,2),
  wavg_ask  numeric(10,2),
  grade     text CHECK (grade IN ('A','B','C')),
  bidding_ends_at timestamptz,
  best_bid_id uuid,
  version   int NOT NULL DEFAULT 0,
  opened_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
-- at most one joinable cluster per pickup point and crop
CREATE UNIQUE INDEX clusters_one_joinable
  ON clusters (collection_point_id, crop_code) WHERE status IN ('OPEN','READY');

CREATE TABLE call_sessions (                 -- durable checkpoint of the Redis session
  id        uuid PRIMARY KEY,
  phone     text NOT NULL,
  farmer_id uuid REFERENCES farmers(id),
  kind      text NOT NULL CHECK (kind IN ('LISTING','BID_OFFER','PROXY_CONFIRM','UNKNOWN_CALLER')),
  provider  text NOT NULL CHECK (provider IN ('sim','exotel','asterisk')),
  provider_call_id text,
  state     text NOT NULL,
  data      jsonb NOT NULL DEFAULT '{}',
  version   int NOT NULL DEFAULT 0,
  outcome   text,                            -- 'COMPLETED','DROPPED','FAILED_INPUT','EXPIRED'
  started_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  ended_at  timestamptz
);
CREATE INDEX call_sessions_phone_idx ON call_sessions (phone, updated_at DESC);

CREATE TABLE listings (
  id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code      serial UNIQUE,                   -- spoken to the farmer digit by digit
  farmer_id uuid NOT NULL REFERENCES farmers(id),
  cluster_id uuid NOT NULL REFERENCES clusters(id),
  crop_code text NOT NULL REFERENCES crops(code),
  qty_qtl   numeric(6,2) NOT NULL CHECK (qty_qtl > 0),
  ask_price numeric(10,2) NOT NULL CHECK (ask_price > 0),
  afpp_at_listing numeric(10,2),
  guardrail text NOT NULL DEFAULT 'NONE' CHECK (guardrail IN ('NONE','RAISED','KEPT_BELOW','NO_PRICE_DATA')),
  source    text NOT NULL CHECK (source IN ('IVR','AGENT_PROXY')),
  session_id uuid UNIQUE REFERENCES call_sessions(id),   -- idempotency: one listing per call session
  status    text NOT NULL DEFAULT 'ACTIVE' CHECK (status IN
            ('PENDING_CONFIRM','ACTIVE','ACCEPTED','SOLD','WITHDRAWN','EXPIRED')),
  actual_qtl numeric(6,2),                   -- weighed at pickup
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL DEFAULT now() + interval '7 days'
);
-- one live listing per farmer per crop
CREATE UNIQUE INDEX listings_one_live ON listings (farmer_id, crop_code)
  WHERE status IN ('PENDING_CONFIRM','ACTIVE','ACCEPTED');
CREATE INDEX listings_cluster_idx ON listings (cluster_id);

CREATE TABLE verifications (
  id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  cluster_id uuid NOT NULL UNIQUE REFERENCES clusters(id),
  agent_id  uuid NOT NULL REFERENCES agents(id),
  grade     text NOT NULL CHECK (grade IN ('A','B','C','REJECT')),
  moisture_pct numeric(4,1),
  photo_path text NOT NULL,
  geog      geography(Point,4326) NOT NULL,
  accuracy_m numeric(8,1),
  distance_m numeric(8,1) NOT NULL,          -- to the collection point, computed server-side
  captured_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE bids (
  id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  cluster_id uuid NOT NULL REFERENCES clusters(id),
  buyer_id  uuid NOT NULL REFERENCES buyers(id),
  price_per_qtl numeric(10,2) NOT NULL CHECK (price_per_qtl > 0),
  min_qty_qtl numeric(8,2) NOT NULL CHECK (min_qty_qtl > 0),
  status    text NOT NULL DEFAULT 'LEADING' CHECK (status IN
            ('LEADING','OUTBID','CONFIRMING','DEAL','FAILED','CANCELLED')),
  idempotency_key text NOT NULL,
  confirm_deadline timestamptz,              -- set when the bid enters CONFIRMING
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (buyer_id, idempotency_key)
);
CREATE INDEX bids_cluster_idx ON bids (cluster_id, price_per_qtl DESC);
ALTER TABLE clusters ADD CONSTRAINT clusters_best_bid_fk FOREIGN KEY (best_bid_id) REFERENCES bids(id);

CREATE TABLE call_jobs (                     -- durable outbound-call queue
  id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  phone     text NOT NULL,
  farmer_id uuid REFERENCES farmers(id),
  kind      text NOT NULL CHECK (kind IN ('CALLBACK','BID_OFFER','PROXY_CONFIRM')),
  payload   jsonb NOT NULL DEFAULT '{}',
  status    text NOT NULL DEFAULT 'QUEUED' CHECK (status IN
            ('QUEUED','DIALING','IN_CALL','DONE','FAILED','CANCELLED')),
  attempts  smallint NOT NULL DEFAULT 0,
  max_attempts smallint NOT NULL DEFAULT 3,
  run_at    timestamptz NOT NULL DEFAULT now(),
  dedupe_key text NOT NULL UNIQUE,           -- e.g. 'bid:{bid_id}:{listing_id}'
  provider_call_id text,
  last_error text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX call_jobs_due_idx ON call_jobs (run_at) WHERE status = 'QUEUED';

CREATE TABLE bid_responses (
  id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  bid_id    uuid NOT NULL REFERENCES bids(id),
  listing_id uuid NOT NULL REFERENCES listings(id),
  response  text NOT NULL DEFAULT 'PENDING' CHECK (response IN ('PENDING','ACCEPT','REJECT','NO_ANSWER')),
  responded_at timestamptz,
  UNIQUE (bid_id, listing_id)
);

CREATE TABLE deals (
  id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  cluster_id uuid NOT NULL UNIQUE REFERENCES clusters(id),
  bid_id    uuid NOT NULL UNIQUE REFERENCES bids(id),
  buyer_id  uuid NOT NULL REFERENCES buyers(id),
  qty_qtl   numeric(8,2) NOT NULL,
  price_per_qtl numeric(10,2) NOT NULL,
  gross_value numeric(12,2) NOT NULL,
  platform_fee numeric(12,2) NOT NULL,       -- 1.5 % of gross, invoiced to buyer
  status    text NOT NULL DEFAULT 'CONFIRMED' CHECK (status IN
            ('CONFIRMED','PAYMENT_REPORTED','PAID','PICKED_UP','DISPUTED','CANCELLED')),
  pickup_by date NOT NULL,
  payment_ref text,                          -- UTR typed by buyer
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE ledger (
  id       bigserial PRIMARY KEY,
  deal_id  uuid NOT NULL REFERENCES deals(id),
  entry    text NOT NULL CHECK (entry IN ('PLATFORM_FEE','FPO_VERIFICATION_FEE')),
  amount   numeric(12,2) NOT NULL,
  status   text NOT NULL DEFAULT 'DUE' CHECK (status IN ('DUE','PAID','VOID')),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (deal_id, entry)
);

-- ---------- support, audit, realtime ----------
CREATE TABLE triage_tickets (
  id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  phone    text NOT NULL,
  farmer_id uuid REFERENCES farmers(id),
  reason   text NOT NULL CHECK (reason IN ('IVR_FAIL_3','UNKNOWN_CALLER','HELP_KEY')),
  status   text NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','ASSIGNED','RESOLVED')),
  agent_id uuid REFERENCES agents(id),
  verbal_code char(2),                       -- told to the farmer by IVR, shown to agent only at bridge time
  code_expires_at timestamptz,
  code_used boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX triage_one_open ON triage_tickets (phone) WHERE status IN ('OPEN','ASSIGNED');

CREATE TABLE consent_log (
  id bigserial PRIMARY KEY,
  farmer_id uuid NOT NULL REFERENCES farmers(id),
  version text NOT NULL, lang text NOT NULL,
  session_id uuid NOT NULL, digit char(1) NOT NULL,
  at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE dtmf_events (                   -- evidence trail for every commercial keypress
  id bigserial PRIMARY KEY,
  session_id uuid NOT NULL,
  event_id text NOT NULL,
  state_before text NOT NULL, digits text NOT NULL, state_after text NOT NULL,
  dropped_reason text,                       -- 'BOUNCE','DUPLICATE_EVENT','OUT_OF_RANGE', NULL if applied
  at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (session_id, event_id)
);

CREATE TABLE events (                        -- outbox: source for WebSocket fan-out and replay
  seq bigserial PRIMARY KEY,
  type text NOT NULL,
  audience text NOT NULL DEFAULT 'all' CHECK (audience IN ('all','buyer','agent','ops')),
  payload jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
```

### 5.2 Redis (Valkey) key design

| Key | Type | TTL | Purpose |
|---|---|---|---|
| `sess:{phone}` | string (JSON) | 1800 s, refreshed on every event | Live call session; survives a dropped call so the next callback resumes |
| `callmap:{provider}:{call_id}` | string → phone | 3600 s | Resolve a provider call id to a session; also proves we initiated the call |
| `evt:{call_id}:{event_id}` | string (cached Action JSON) | 3600 s | Webhook idempotency: a retried event returns the same answer without re-applying |
| `lock:call:{phone}` | string (random token) | 300 s, extended on every event | One live call per farmer; released by compare-and-delete Lua |
| `dtmf:last:{call_id}` | string `digit:ts_ms` | 5 s | Per-digit debounce (simulator and Asterisk adapters only) |
| `rl:cb:{phone}:10m` | counter | 600 s | Max 3 callbacks per 10 minutes per number |
| `rl:cb:{phone}:day` | counter | 86400 s | Max 6 callbacks per day per number |
| `budget:calls:{yyyymmdd}` | counter | 172800 s | Global daily outbound-call cap (circuit breaker) |
| `miss:{phone}` | string | 20 s | Collapse duplicate missed-call webhooks |
| `fail:{phone}` | counter | 86400 s | Failed IVR attempts; 3 opens a triage ticket |
| `floor:{district}:{crop}` | string (JSON) | 93600 s (26 h) | Cache of today's `price_floors` row |
| `rl:login:{email_or_phone}` | counter | 900 s | 5 failed logins lock the account for 15 minutes |
| `ad:events` | pub/sub channel | none | Fan-out of `events` rows to WebSocket processes |

Rules:
- Nothing in Redis is the only copy of a committed fact. If Redis is flushed, rate-limit counters reset (acceptable), locks vanish (calls in flight continue; the Postgres unique indexes still prevent duplicates) and sessions are rehydrated from `call_sessions`.
- Session JSON shape (identical to `call_sessions.data` plus the header fields):

```json
{
  "id": "5b0c…uuid", "phone": "+919845012345", "farmer_id": "…uuid",
  "kind": "LISTING", "provider": "sim", "provider_call_id": "sim-17",
  "state": "PRICE", "version": 7, "lang": "kn",
  "data": {"crop": "ragi", "crop_page": 0, "qty": 3, "price": null,
           "afpp": 3650, "modal": 3900, "basis": "DISTRICT_FRESH",
           "retries": 0, "bid_id": null, "listing_id": null}
}
```

### 5.3 Lua scripts

```lua
-- lua/session_cas.lua : atomic compare-and-set of the session
-- KEYS[1]=sess:{phone}   ARGV[1]=expected_version  ARGV[2]=new_json  ARGV[3]=ttl_seconds
-- returns 1 = written, 0 = version mismatch (concurrent or stale handler), -1 = session missing
local cur = redis.call('GET', KEYS[1])
if not cur then
  if ARGV[1] ~= '0' then return -1 end
else
  if tostring(cjson.decode(cur).version) ~= ARGV[1] then return 0 end
end
redis.call('SET', KEYS[1], ARGV[2], 'EX', tonumber(ARGV[3]))
return 1
```

```lua
-- lua/allow_callback.lua : check three limits, then count, atomically
-- KEYS[1]=rl:cb:{phone}:10m  KEYS[2]=rl:cb:{phone}:day  KEYS[3]=budget:calls:{date}
-- ARGV[1]=limit_10m  ARGV[2]=limit_day  ARGV[3]=daily_budget
-- returns 1 = allowed, 0 = per-number limit hit, -1 = global budget hit
local a = tonumber(redis.call('GET', KEYS[1]) or '0')
local b = tonumber(redis.call('GET', KEYS[2]) or '0')
local c = tonumber(redis.call('GET', KEYS[3]) or '0')
if c >= tonumber(ARGV[3]) then return -1 end
if a >= tonumber(ARGV[1]) or b >= tonumber(ARGV[2]) then return 0 end
if redis.call('INCR', KEYS[1]) == 1 then redis.call('EXPIRE', KEYS[1], 600) end
if redis.call('INCR', KEYS[2]) == 1 then redis.call('EXPIRE', KEYS[2], 86400) end
if redis.call('INCR', KEYS[3]) == 1 then redis.call('EXPIRE', KEYS[3], 172800) end
return 1
```

```lua
-- lua/release_lock.lua : delete the lock only if we still own it
-- KEYS[1]=lock:call:{phone}  ARGV[1]=token
if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]) end
return 0
```

Acquire the lock with `SET lock:call:{phone} {token} NX PX 300000`. The lock is an efficiency guard (it stops two simultaneous calls to one farmer). Correctness never depends on it: listings, bids and responses are protected by Postgres constraints, because a Redis lock without fencing tokens can be held by two clients after a pause or failover.

### 5.4 Call state machine

Three flows share one engine. `Action` is what the engine returns to a telephony adapter: a list of audio clips, how many digits to collect, the terminator, the timeout and whether to hang up.

**Flow LISTING** (callback after a missed call from a registered farmer)

| State | Prompt (summary) | Input | Valid keys → next state | Timeout |
|---|---|---|---|---|
| `LANG` (first call only) | "Kannada 1, Hindi 2, Marathi 3", each phrase in its own language | 1 digit | 1/2/3 → `CONSENT` | 6 s |
| `CONSENT` (first call only) | What is stored and why; "press 1 to agree" | 1 digit | 1 → `MAIN`; 2 → `BYE` | 8 s |
| `MAIN` (only if the farmer has a live listing) | Status of the live listing, then "1 new listing, 2 withdraw listing, 0 helper" | 1 digit | 1 → `CROP`; 2 → `WITHDRAW_CONFIRM`; 0 → `HELP` | 6 s |
| `WITHDRAW_CONFIRM` | "Withdraw your CROP listing? 1 yes, 2 no" (refused with an explanation if the cluster is already in bidding) | 1 digit | 1 → listing `WITHDRAWN`, recompute cluster → `BYE`; 2 → `MAIN` | 6 s |
| `CROP` | Up to 3 crops for district and month; "9 more crops, 0 helper" | 1 digit | 1–3 → `QTY`; 9 → `CROP` (next page, max 3 pages); 0 → `HELP` | 6 s |
| `QTY` | "Enter quintals, then press hash" | up to 2 digits, `#` or timeout ends | 1..`max_listing_qtl` → `QTY_CONFIRM`; else re-prompt | 8 s |
| `QTY_CONFIRM` | "You entered N quintals. 1 correct, 2 re-enter" | 1 digit | 1 → `PRICE`; 2 → `QTY` | 6 s |
| `PRICE` | Reference price with its date; "enter your price per quintal, then hash" | up to 5 digits, `#` or timeout ends | within `[min_price, max_price]` → `GUARD` if below floor, else `FINAL`; else re-prompt | 10 s |
| `GUARD` | "Your price is below the fair farm-gate price F. 1 raise to F, 2 keep yours, 3 re-enter" | 1 digit | 1 → `FINAL` (price = F); 2 → `FINAL`; 3 → `PRICE` | 8 s |
| `FINAL` | Reads back crop, quantity and price (digit by digit); "1 confirm, 2 start again" | 1 digit | 1 → commit → `DONE`; 2 → `CROP` | 8 s |
| `DONE` | "Listed. Your number is c-o-d-e. We will call when a buyer offers." | none | hang up | — |
| `HELP` | "A helper will call you. Their code is X-Y." | none | open triage ticket, hang up | — |
| `BYE` | Short goodbye | none | hang up | — |

**Flow BID_OFFER** (outbound call for a winning bid)

| State | Prompt | Valid keys → next |
|---|---|---|
| `OFFER` | "A buyer offers P per quintal for your N quintals of CROP. Your asking price was A. 1 accept, 2 reject, 9 repeat" | 1 → `OFFER_CONFIRM`; 2 → record REJECT → `BYE`; 9 → `OFFER` |
| `OFFER_CONFIRM` | "You are accepting P. Press 1 to confirm, 2 to go back" | 1 → record ACCEPT → `DONE_OFFER`; 2 → `OFFER` |

**Flow PROXY_CONFIRM** (outbound call after an agent enters a listing on the farmer's behalf): `PROXY_READBACK` reads the agent-entered crop, quantity and price; 1 → listing `PENDING_CONFIRM` → `ACTIVE`; 2 → listing `WITHDRAWN` and the ticket is flagged for review.

**Flow UNKNOWN_CALLER** (callback to a number that is not on any roster, at most once a day): one state, `NOT_REGISTERED`, plays "you are not registered; a helper will call you; their code is X-Y", opens a triage ticket and hangs up.

If the farmer picks a crop for which they already have a live listing, `CROP` plays `already_listed` and returns to `MAIN`.

**Engine rules (apply to every state)**
- **Terminal states** are `DONE`, `DONE_OFFER`, `HELP`, `BYE` and `NOT_REGISTERED`. Their Action has `hangup=true`. Any event that arrives after a terminal prompt returns `hangup_now=true`, which tells the adapter to end the call.
- **Retries:** an invalid key or a timeout replays the prompt, at most 2 times per state. The third failure plays `BYE`, increments `fail:{phone}` and, at 3 failed calls in 24 h, opens a triage ticket.
- **Unknown input never commits.** Only an explicit `1` in `FINAL`, `OFFER_CONFIRM` or `PROXY_READBACK` creates a binding record.
- **Terminator tolerance:** multi-digit states accept `#` or the input timeout as the end of entry, because many users forget the hash key.
- **Total call cap:** 240 s. The engine hangs up after that with the session preserved for resume.
- **Resume:** when a callback starts and `sess:{phone}` exists with `kind=LISTING` and a state after `CROP`, the engine plays "welcome back, continuing your CROP listing" and re-enters the saved state. `LANG` and `CONSENT` are never repeated once stored on the farmer row.
- **Session TTL:** 1800 s after the last event. On expiry the draft is dropped and `call_sessions.outcome` is set to `EXPIRED` by a sweeper that runs every 5 minutes.
- **Checkpoint:** after every accepted transition the session is written to Redis (Lua CAS) and upserted into `call_sessions`. On a Redis miss the engine rehydrates from `call_sessions` if `updated_at` is within 30 minutes.

**DTMF debounce and validation values**

| Layer | Value | Applies to | Why |
|---|---|---|---|
| Same-digit bounce window | 120 ms | simulator, Asterisk (per-digit events) | A repeat of the same digit faster than 120 ms is not a human press [Assumed, engineering judgement]. The original plans' 250 ms would delete real double digits such as the `00` in `3800`. |
| Minimum gap, any digit | 40 ms | simulator, Asterisk | Below the tone-plus-pause the network itself enforces (65–70 ms tone, 65 ms gap in the 3GPP DTMF procedure) [Likely] |
| Event idempotency | `evt:{call_id}:{event_id}` | all adapters | A retried webhook must not be applied twice |
| Single-key menus | collect exactly 1 digit | all adapters | A bounced `11` becomes `1`; the extra digit is discarded by the provider's `max_input_digits=1` |
| Range check | per-crop `max_listing_qtl`, `min_price`, `max_price` | all adapters | Catches `38000` typed for `3800` and `33` typed for `3` when out of range |
| Readback and confirm | `QTY_CONFIRM`, `FINAL`, `OFFER_CONFIRM` | all adapters | The only defence that works when the provider hands over a finished digit string with no timing (Exotel Gather) |

Honest limit: with a cloud PBX that returns the collected string (Exotel's Gather), the application never sees per-digit timing, so a timing debounce cannot run there. Range checks and readback are the real protection on that path; the 120 ms window is real only on the simulator and Asterisk paths.

---

## 6. API and event specification

Base URL in the demo: `http://localhost:8000` (tunnelled as `https://<static>.ngrok-free.app` for the telephone provider and for phones). All JSON. Times are ISO-8601 UTC. Money is rupees per quintal as a number.

### 6.1 Authentication

| Endpoint | Body | Response |
|---|---|---|
| `POST /api/auth/buyer/login` | `{email, password}` | `{token, buyer:{id, org_name, status}}` |
| `POST /api/auth/agent/login` | `{phone, pin}` | `{token, agent:{id, name, fpo_id}}` |
| `POST /api/auth/buyer/register` | `{org_name, email, password, phone, license_no}` | `201 {id, status:"PENDING"}` |

Tokens are HS256 JWTs (`sub`, `role` in `buyer|agent|admin`, `exp` 12 h) sent as `Authorization: Bearer`. Passwords and PINs are hashed with bcrypt. Admin is a single seeded account.

### 6.2 Buyer API (role `buyer`, status `APPROVED`)

| Endpoint | Purpose | Notes |
|---|---|---|
| `GET /api/clusters?status=BIDDING,READY,OPEN&crop=&district=` | List clusters | Never returns farmer names or phones |
| `GET /api/clusters/{id}` | Detail: lots (anonymised as "Lot 1…n" with quantity and ask), grade, photo URL, best bid, time left | |
| `POST /api/clusters/{id}/bids` | Place a bid | Header `Idempotency-Key: <uuid>` required |
| `GET /api/bids/mine` | Buyer's bids with status and confirmation progress | |
| `GET /api/deals/mine` | Deals with FPO payee details and amount due | |
| `POST /api/deals/{id}/payment-reported` | `{payment_ref}` | `CONFIRMED → PAYMENT_REPORTED` |

Cluster object (used in REST and WebSocket payloads):

```json
{"id":"…","code":104,"crop_code":"ragi","crop_name":"Ragi","district":"Mandya",
 "collection_point":{"name":"Keregodu FPO yard","lat":12.63,"lon":76.92},
 "status":"BIDDING","total_qtl":24.0,"listing_count":8,
 "min_ask":3600,"wavg_ask":3742,"grade":"A","photo_url":"/media/v/…jpg",
 "bidding_ends_at":"2026-11-27T12:30:00Z",
 "best_bid":{"price_per_qtl":3800,"mine":false},"version":12}
```

Place bid:

```
POST /api/clusters/{id}/bids      Idempotency-Key: 0b9c…
{"price_per_qtl": 3850, "min_qty_qtl": 15}

201 {"id":"…","status":"LEADING","price_per_qtl":3850,"min_qty_qtl":15}
409 {"error":"BID_TOO_LOW","min_next":3810}      // must be >= the cluster's min_ask and beat the best bid by >= Rs 10
422 {"error":"MIN_QTY_TOO_HIGH"}                 // min_qty_qtl exceeds the cluster's total
409 {"error":"CLUSTER_NOT_BIDDING"}
403 {"error":"BUYER_NOT_APPROVED"}
200 (same body as the original 201) when the Idempotency-Key was already used by this buyer
```

### 6.3 Agent API (role `agent`)

| Endpoint | Purpose |
|---|---|
| `GET /api/agent/tasks` | Clusters in `READY` at the agent's FPO (to verify), deals awaiting pickup, open triage tickets |
| `POST /api/agent/clusters/{id}/verification` | multipart: `photo` (JPEG ≤ 2 MB), `grade`, `moisture_pct?`, `lat`, `lon`, `accuracy_m`, `captured_at` → `201` and cluster `READY → BIDDING`; `422 {"error":"TOO_FAR","distance_m":1840}` if more than 500 m from the collection point; `422 {"error":"STALE_CAPTURE"}` if older than 10 minutes |
| `POST /api/agent/triage/{id}/claim` | `OPEN → ASSIGNED` |
| `POST /api/agent/triage/{id}/bridge` | Starts the masked call (agent ↔ platform number ↔ farmer); returns `{verbal_code:"55", mode:"exotel"|"simulated"}` once, and marks the code used |
| `POST /api/agent/triage/{id}/proxy-listing` | `{crop_code, qty_qtl, ask_price}` → creates listing `PENDING_CONFIRM` and a `PROXY_CONFIRM` call job |
| `POST /api/agent/deals/{id}/payment-confirmed` | FPO confirms money received: `PAYMENT_REPORTED → PAID` |
| `POST /api/agent/deals/{id}/pickup` | `{weights:[{listing_id, actual_qtl}]}` → only allowed when `PAID`; `→ PICKED_UP`, listings `SOLD`, ledger rows written |
| `POST /api/agent/deals/{id}/no-show` | Buyer truck did not come by `pickup_by`: deal `CANCELLED`, buyer `strikes+1`, cluster back to `BIDDING` |

### 6.4 Admin and ops API (role `admin`)

| Endpoint | Purpose |
|---|---|
| `POST /api/admin/farmers/import` | CSV `phone,name,village,lat,lon,fpo_name` → upsert farmers, assign nearest collection point within 5 km |
| `POST /api/admin/buyers/{id}/approve` | `PENDING → APPROVED` |
| `POST /api/admin/prices/refresh` | Run price ingestion now |
| `POST /api/admin/clusters/{id}/close-auction` | End the bidding window now (used in the demo) |
| `GET /api/ops/calls` | Live sessions and the call-job queue |
| `GET /health` | `{db:"ok", redis:"ok", tts_cache: 412, price_age_days: 1}` |

### 6.5 Telephony webhooks

All adapters call one engine function and translate its `Action`.

**Simulator (WebSocket `/tel/sim/ws`)**

| Direction | Message |
|---|---|
| client → server | `{"t":"missed_call","phone":"+919845012345"}` |
| server → client | `{"t":"ring","call_id":"sim-17"}` |
| client → server | `{"t":"answer","call_id":"sim-17"}` |
| server → client | `{"t":"play","call_id":"sim-17","audio_url":"/audio/mix/ab12….wav","max_digits":1,"finish_on_key":"","timeout_s":6}` |
| client → server | `{"t":"digit","call_id":"sim-17","d":"1","ts_ms":1731480000123,"seq":4}` |
| client → server | `{"t":"timeout","call_id":"sim-17","seq":5}` |
| either | `{"t":"hangup","call_id":"sim-17"}` |

The simulator sends each digit separately with a client timestamp, so the 120 ms debounce runs for real. It has two test switches: "inject key bounce" (sends each digit twice, 30–60 ms apart) and "drop call" (closes the call without a hangup message).

**Exotel** (`{secret}` is a 32-character random path token, because Exotel documents no webhook signature)

| Endpoint | Called by | Behaviour |
|---|---|---|
| `POST /tel/exotel/{secret}/missed` | Missed-call webhook, form-encoded `CallSid, From, To, Status=missed-call` | Dedupe (`miss:{phone}`), rate-limit, enqueue a `CALLBACK` job. Always `200`. |
| `GET /tel/exotel/{secret}/gather?CallSid=&CallFrom=&step=k` | Gather applet number *k*, dynamic URL | Returns the prompt for the current state: `{"gather_prompt":{"audio_url":"https://…/audio/mix/ab12.wav"},"max_input_digits":1,"finish_on_key":"#","input_timeout":6}` |
| `GET /tel/exotel/{secret}/digits?CallSid=&digits=&step=k` | Passthru applet number *k* | Strips the literal quotes around `digits`, applies the transition with `event_id=k`. `200` = continue to Gather *k+1*; `404` = flow ends (hang-up branch). |
| `POST /tel/exotel/{secret}/status` | StatusCallback | Marks the call job `DONE`/`FAILED`, releases the lock, schedules a retry if unanswered |

Requests whose `CallSid` is not in `callmap:exotel:*` are rejected with `403`: the platform only accepts events for calls it started.

**Outbound call request the Exotel adapter makes** [Verified against Exotel's connect-to-flow reference]:

```
POST https://api.exotel.com/v1/Accounts/{sid}/Calls/connect.json      (Basic auth api_key:api_token)
From={farmer_phone}&CallerId={exophone}&CallType=trans&TimeLimit=240&TimeOut=30
&Url=http://my.exotel.com/{sid}/exoml/start_voice/{app_id}
&StatusCallback=https://<host>/tel/exotel/{secret}/status&CustomField={job_id}
```

**Masked bridge request** (same endpoint, two-number form): `From={agent_phone}&To={farmer_phone}&CallerId={exophone}`. Both people see only the platform number.

### 6.6 WebSocket events (`/ws?token=<jwt>&since=<seq>`)

Server → client only. Every message is one row of `events`: `{"seq":1042,"type":"…","payload":{…}}`. On connect the server replays rows with `seq > since` (maximum 500; if more, it sends `{"type":"resync"}` and the client reloads via REST). The client stores the last `seq` and reconnects with exponential backoff (1 s, 2 s, 4 s, capped at 15 s).

| Type | Audience | Payload |
|---|---|---|
| `cluster.updated` | all | Cluster object (section 6.2) |
| `listing.created` | all | `{cluster_id, crop_code, qty_qtl, ask_price, source}` (no farmer identity) |
| `bid.placed` | buyer | `{cluster_id, bid_id, price_per_qtl, buyer_is_you}` |
| `bid.confirming` | buyer | `{cluster_id, bid_id, accepted_qtl, rejected_qtl, pending_qtl}` |
| `deal.created` | buyer, agent | `{deal_id, cluster_id, qty_qtl, price_per_qtl, gross_value, platform_fee, pickup_by}` |
| `deal.updated` | buyer, agent | `{deal_id, status}` |
| `bid.failed` | buyer | `{cluster_id, bid_id, accepted_qtl, min_qty_qtl}` |
| `task.created` | agent | `{kind:"VERIFY"|"TRIAGE"|"PICKUP", ref_id}` |
| `call.state` | ops | `{phone_masked:"+91•••••2345", kind, state, provider}` |

Clients must treat events as hints and de-duplicate by `seq`; delivery is at-least-once.

### 6.7 Idempotency rules (summary)

| Operation | Key | Enforced by |
|---|---|---|
| Missed-call webhook | phone, 20 s window | `miss:{phone}` `SET NX` |
| Any telephony event | `(call_id, event_id)` | `evt:` key caches the Action |
| Concurrent handlers on one session | session `version` | `session_cas.lua` |
| Listing creation | `session_id` | `listings.session_id UNIQUE` plus `listings_one_live` |
| Bid placement | `(buyer_id, Idempotency-Key)` | `bids` unique constraint; replay returns the stored bid |
| Farmer response to a bid | `(bid_id, listing_id)` | `UPDATE … WHERE response='PENDING'` (first write wins) |
| Outbound call job | `dedupe_key` | `call_jobs.dedupe_key UNIQUE` |
| Deal creation | `cluster_id`, `bid_id` | `deals` unique constraints |
| Verification | `cluster_id` | `verifications.cluster_id UNIQUE` |

---

## 7. Module-by-module build guide

### 7.0 Repository, environment and first run

```
annadata-dhwani/
  docker-compose.yml            # db (postgis/postgis:16-3.4) + cache (valkey/valkey:8)
  .env.example
  db/001_schema.sql             # section 5.1
  db/002_seed.sql               # districts, crops, deduction_rules, 1 FPO, 3 collection points, admin
  backend/app/
    main.py config.py db.py cache.py
    lua/session_cas.lua allow_callback.lua release_lock.lua
    engine/actions.py engine.py flows.py debounce.py
    telephony/base.py sim.py exotel.py asterisk.py
    services/pricing.py clustering.py bidding.py jobs.py events.py audio.py triage.py
    api/auth.py buyer.py agent.py admin.py ws.py
  backend/scripts/
    prewarm_audio.py ingest_prices.py build_crop_calendar.py import_farmers.py seed_demo.py
  backend/prompts.yaml          # every spoken sentence, per language
  backend/tests/
  frontend/src/routes/Buyer.tsx Agent.tsx Sim.tsx Ops.tsx  src/lib/ws.ts api.ts
  audio/{kn,hi,mr}/*.wav  audio/mix/*.wav   media/v/*.jpg
```

`.env.example` (the names are used throughout this section):

```
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/annadata
REDIS_URL=redis://localhost:6379/0
JWT_SECRET=change-me
PUBLIC_BASE_URL=http://localhost:8000        # the ngrok URL when Exotel or phones are used
TELEPHONY_PROVIDER=sim                        # sim | exotel | asterisk
WEBHOOK_SECRET=32-random-chars
EXOTEL_SID= EXOTEL_API_KEY= EXOTEL_API_TOKEN= EXOPHONE= EXOTEL_APP_ID=
DATA_GOV_KEY=                                 # free key from data.gov.in
BHASHINI_USER_ID= BHASHINI_API_KEY=
DEMO_MODE=1                                   # 1: auction 3 min, confirm round 90 s, calling hours off
DAILY_CALL_BUDGET=200
```

First run: `docker compose up -d` → `pip install -r backend/requirements.txt` (fastapi, uvicorn[standard], asyncpg, redis, pyjwt, bcrypt, httpx, python-multipart, pyyaml, indic-numtowords) → `python backend/scripts/prewarm_audio.py` → `python backend/scripts/seed_demo.py` → `uvicorn app.main:app --port 8000` → `npm run build` in `frontend/` (FastAPI serves `frontend/dist` at `/`). FFmpeg must be on the PATH.

### 7.1 Telephony adapters (IVR)

**Purpose.** Translate each provider's events into engine calls and each engine `Action` into what the provider can play.

**Inputs/outputs.** In: missed call, call answered, digits, timeout, hang-up, call status. Out: place call, play one audio URL and collect digits, hang up, bridge two numbers.

**Interface**

```python
# telephony/base.py
class TelephonyAdapter(Protocol):
    name: str                                            # 'sim' | 'exotel' | 'asterisk'
    async def place_call(self, phone: str, job_id: str) -> str: ...   # returns provider_call_id
    async def bridge(self, agent_phone: str, farmer_phone: str) -> str: ...
```

**Build steps**
1. **Simulator adapter first (Day 1–2).** WebSocket endpoint `/tel/sim/ws` with the messages in section 6.5. On `play`, the adapter starts a per-call digit buffer; it feeds each `digit` through `debounce.accept_digit`, and calls the engine with `DIGITS` when the buffer reaches `max_digits`, the finish key arrives, or the client reports `timeout`. `place_call` sends `ring` to the socket registered for that phone.
2. **Simulator page** (`Sim.tsx`): a phone keypad, a "give missed call" button, a phone-number selector (seeded farmers), an audio element that plays the returned 8 kHz WAV, and the two switches "inject key bounce" and "drop call". Keys play local DTMF tones with the WebAudio API for realism.
3. **Exotel adapter (Day 8–10, after the trial starts).**
   - In the Exotel dashboard: whitelist the team's phones (maximum 10), turn on missed-call mode for the trial number and point its webhook to `POST {PUBLIC_BASE_URL}/tel/exotel/{WEBHOOK_SECRET}/missed` [Verified: feature and payload].
   - Build one flow in App Bazaar: `Gather(1) → Passthru(1) → Gather(2) → Passthru(2) → … → Gather(12) → Passthru(12) → Hangup`. Each Gather uses the dynamic URL `…/gather?step=k`; each Passthru uses `…/digits?step=k`, with its failure branch wired to Hangup. Twelve pairs cover the longest path (LANG, CONSENT, MAIN, CROP ×2, QTY, QTY_CONFIRM, PRICE, GUARD, FINAL plus two retries). If the flow runs out of pairs the call ends and the session resumes on the next callback.
   - **This applet wiring is [Assumed].** Exotel's two Passthru documents disagree on GET vs POST and on whether a Passthru response can choose the next applet. Hour one of the trial is a spike to confirm: (a) Gather dynamic URL returns our JSON, (b) digits arrive at the Passthru wrapped in quotes, (c) a non-200 Passthru response takes the failure branch, (d) whether an applet can loop back to an earlier one (which would shrink the chain to one pair).
   - `place_call` posts the connect request in section 6.5 and stores `callmap:exotel:{CallSid} → phone`.
4. **Terminal states on Exotel.** `DONE`, `BYE` and `HELP` are returned as a Gather with `max_input_digits=1` and `input_timeout=1`; the following Passthru call returns `404`, which hangs up.
5. **Asterisk adapter (stretch).** `andrius/asterisk` container, one PJSIP endpoint with `dtmf_mode=rfc4733`, codecs `alaw,ulaw`, dialplan `exten => 100,1,AGI(agi://host.docker.internal:4573)`. A 90-line asyncio FastAGI server maps `STREAM FILE` / `WAIT FOR DIGIT` to the engine. Linphone on a laptop registers as the "farmer". On Windows, pin the RTP range (10000–10020) and publish those UDP ports.

**Code skeleton (Exotel)**

```python
# telephony/exotel.py
router = APIRouter(prefix="/tel/exotel/{secret}")

def check(secret: str):
    if not hmac.compare_digest(secret, settings.WEBHOOK_SECRET): raise HTTPException(403)

@router.post("/missed")
async def missed(secret: str, From: str = Form(...), CallSid: str = Form(...)):
    check(secret)
    phone = normalise_e164(From)
    if await cache.set(f"miss:{phone}", "1", nx=True, ex=20):
        await jobs.request_callback(phone)            # rate limit + enqueue, section 7.6
    return {"ok": True}

@router.get("/gather")
async def gather(secret: str, CallSid: str, step: int, CallFrom: str = ""):
    check(secret)
    phone = await cache.get(f"callmap:exotel:{CallSid}")
    if not phone: raise HTTPException(403)
    kind = "START" if step == 1 else "PROMPT"         # PROMPT = re-read current prompt, no transition
    a = await engine.handle_event("exotel", CallSid, phone, kind, event_id=f"g{step}")
    return {"gather_prompt": {"audio_url": audio.mix_url(a.clips, a.lang)},
            "max_input_digits": a.max_digits, "finish_on_key": a.finish_on_key or "#",
            "input_timeout": 1 if a.hangup else a.timeout_s}

@router.get("/digits")
async def digits(secret: str, CallSid: str, step: int, digits: str = ""):
    check(secret)
    phone = await cache.get(f"callmap:exotel:{CallSid}")
    if not phone: raise HTTPException(403)
    d = digits.strip().strip('"')                     # Exotel wraps digits in literal quotes
    a = await engine.handle_event("exotel", CallSid, phone, "DIGITS" if d else "TIMEOUT", d, f"d{step}")
    if a.hangup_now: raise HTTPException(404)         # failure branch → Hangup applet
    return {"ok": True}
```

**Tests**
- Simulator: full listing in under 60 s; with "inject key bounce" on, `QTY` of `3` is stored as 3, not 33, and `dtmf_events` shows a `BOUNCE` row.
- Replay the same `/digits?step=4` request twice: the state advances once.
- A `/gather` request with an unknown `CallSid`, or a wrong secret, returns 403.
- Exotel (manual, on the trial): missed call from a whitelisted button phone is called back within 10 s; prompts are intelligible on the handset speaker.

### 7.2 Call engine (state machine)

**Purpose.** One deterministic function that owns every call: `handle_event(provider, call_id, phone, kind, digits, event_id) → Action`.

**Inputs/outputs.** In: event kind `START | PROMPT | DIGITS | TIMEOUT | HANGUP`. Out: `Action`. Side effects: session in Redis and Postgres, `dtmf_events`, and commits through the clustering, bidding and triage services.

**Build steps**
1. `actions.py`: the `Action` dataclass.
2. `engine.py`: idempotency check, session load (Redis, then Postgres rehydrate), flow step, compare-and-set save, checkpoint, cache the Action.
3. `flows.py`: a table of states (section 5.4). Each state has `prompt(sess) → clips`, input shape, and `on_input(sess, digits) → next_state`. Shared `retry()` logic counts failures in `sess.data["retries"]`.
4. Session start: choose the flow from the call job (`CALLBACK → LISTING`, `BID_OFFER`, `PROXY_CONFIRM`); for `LISTING`, skip `LANG`/`CONSENT` when the farmer row already has them; go to `MAIN` if a live listing exists, else `CROP`.
5. Commit points call services inside one database transaction and are safe to repeat (`ON CONFLICT`).
6. Sweeper task (every 5 min): mark expired sessions, reset stuck jobs.

**Code skeleton**

```python
# engine/actions.py
@dataclass
class Action:
    clips: list[str]                 # clip ids, mixed into one WAV by services/audio.py
    lang: str = "kn"
    max_digits: int = 1
    finish_on_key: str = ""          # "#" on multi-digit states
    timeout_s: int = 6
    hangup: bool = False             # play the clips, then end the call
    hangup_now: bool = False         # set on the event after a hangup Action was delivered

# engine/engine.py
SESSION_TTL = 1800

async def handle_event(provider, call_id, phone, kind, digits="", event_id="") -> Action:
    ek = f"evt:{call_id}:{event_id}"
    if (hit := await cache.get(ek)):                       # duplicate webhook: same answer, no re-apply
        return Action(**json.loads(hit))
    for _ in range(3):                                     # retry on CAS conflict
        sess = await load_session(phone)                   # Redis → call_sessions (≤30 min old) → None
        expected = sess.version if sess else 0
        if kind == "START":
            sess, action = await flows.start(sess, phone, provider, call_id)
        elif kind == "PROMPT":
            action = flows.current_prompt(sess)
        elif kind == "HANGUP":
            await flows.on_hangup(sess); return Action([], hangup=True, hangup_now=True)
        elif sess.state in TERMINAL:                       # event after the goodbye prompt: end the call
            return Action([], hangup=True, hangup_now=True)
        else:                                              # DIGITS or TIMEOUT
            before = sess.state
            action = await flows.step(sess, digits)        # may commit to Postgres (idempotent)
            await db.execute(LOG_DTMF, sess.id, event_id, before, digits, sess.state)
        sess.version = expected + 1
        ok = await cache.evalsha(SESSION_CAS, 1, f"sess:{phone}", expected, sess.to_json(), SESSION_TTL)
        if ok == 1:
            await checkpoint(sess)                         # upsert call_sessions
            await cache.pexpire(f"lock:call:{phone}", 300_000)
            break
    else:
        raise HTTPException(503, "session busy")
    await cache.set(ek, json.dumps(asdict(action)), ex=3600)
    return action

# engine/flows.py (excerpt)
async def on_qty(s, digits):
    crop = CROPS[s.data["crop"]]
    if not digits.isdigit() or not 1 <= int(digits) <= crop.max_listing_qtl:
        return retry(s, "bad_qty")
    s.data["qty"] = int(digits); s.data["retries"] = 0
    return "QTY_CONFIRM"

async def on_price(s, digits):
    crop = CROPS[s.data["crop"]]
    if not digits.isdigit() or not crop.min_price <= int(digits) <= crop.max_price:
        return retry(s, "bad_price")
    s.data["price"] = int(digits); s.data["retries"] = 0
    afpp = s.data.get("afpp")
    return "GUARD" if afpp and int(digits) < afpp * 0.97 else "FINAL"

async def on_final(s, digits):
    if digits == "2": return "CROP"
    if digits != "1": return retry(s, "bad_key")
    res = await clustering.commit_listing(s)               # section 7.5
    s.data["listing_code"] = res["code"]
    return "DONE"

def retry(s, reason):
    s.data["retries"] = s.data.get("retries", 0) + 1
    if s.data["retries"] > 2:
        s.data["failed"] = True                            # on_hangup increments fail:{phone}
        return "BYE"
    return s.state                                         # replay the same prompt

PROMPTS = {
    "QTY":         lambda s: ["ask_qty"],
    "QTY_CONFIRM": lambda s: [f"qty_{s.data['qty']}", "confirm_1_2"],
    "PRICE":       lambda s: [s.data.get("floor_clip", "no_price_today"), "ask_price"],
    "GUARD":       lambda s: ["guard_warn", *digit_clips(s.data["afpp"]), "guard_options"],
    "FINAL":       lambda s: [f"crop_{s.data['crop']}", f"qty_{s.data['qty']}", "price_is",
                              *digit_clips(s.data["price"]), "rupees_per_qtl", "final_confirm"],
    "DONE":        lambda s: ["listed_ok", *digit_clips(s.data["listing_code"]), "will_call"],
}
def digit_clips(n: int) -> list[str]: return [f"d_{c}" for c in str(int(n))]
```

```python
# engine/debounce.py  (simulator and Asterisk only)
SAME_DIGIT_MS, ANY_DIGIT_MS = 120, 40

async def accept_digit(call_id: str, d: str, ts_ms: int) -> bool:
    key = f"dtmf:last:{call_id}"
    last = await cache.get(key)
    await cache.set(key, f"{d}:{ts_ms}", ex=5)
    if last:
        ld, lt = last.split(":"); gap = ts_ms - int(lt)
        if gap < ANY_DIGIT_MS or (ld == d and gap < SAME_DIGIT_MS):
            return False
    return True
```

**Tests**
- Table-driven: for each state, each valid key, each invalid key and a timeout → expected next state.
- Three invalid inputs in one state → `BYE`; three such calls → one triage ticket.
- Drop after `QTY_CONFIRM`, call back within 30 min → the first prompt is "welcome back" followed by `PRICE`.
- Flush Redis mid-call → the next event rehydrates from `call_sessions` and continues.
- Same `event_id` twice → one transition, one `dtmf_events` row.
- Two concurrent `handle_event` calls on one session → exactly one wins the CAS, the other retries and sees the new state.
- `FINAL` confirmed twice (CAS retry) → one listing.

### 7.3 TTS pipeline and audio service

**Purpose.** Produce every prompt as an 8 kHz mono 16-bit WAV before any call needs it, and serve mixed prompts from disk.

**Inputs/outputs.** In: `prompts.yaml` (`clip_id → {kn, hi, mr}` text), daily price sentences, bid-offer sentences. Out: `audio/{lang}/{clip_id}.wav`, `audio/mix/{sha}.wav`.

**Clip inventory (per language)**

| Group | Clip ids | Count |
|---|---|---|
| Fixed prompts | `lang_menu`, `consent`, `main_menu`, `ask_qty`, `ask_price`, `confirm_1_2`, `guard_warn`, `guard_options`, `price_is`, `rupees_per_qtl`, `final_confirm`, `listed_ok`, `will_call`, `welcome_back`, `no_price_today`, `bad_qty`, `bad_price`, `bad_key`, `bye`, `helper_will_call`, `not_registered`, `already_listed`, `offer_options`, `offer_confirm`, `offer_done`, `proxy_intro` | about 26 |
| Crop menu lines | `cropkey_{crop}_{1..3}` ("for ragi press 1"), `crop_{crop}`, `more_crops_9` | about 35 for 8 crops |
| Quantity readback | `qty_1` … `qty_50` ("you entered 15 quintals") | 50 |
| Digits | `d_0` … `d_9` | 10 |
| Dynamic | `dyn_{sha12}`: daily reference-price sentence per district and crop; bid-offer sentence per bid and listing | about 50 a day |

About 120 fixed clips per language, about 360 in total.

**Build steps**
1. Write `prompts.yaml` in English first, then translate. **A native speaker of each language must review every line** before generation; machine-translated agricultural terms are a known failure.
2. `prewarm_audio.py`: for each `(lang, clip_id, text)` compute `sha256(lang|voice|text)`; skip if `audio/{lang}/{clip_id}.wav` exists with a matching `.sha` sidecar; else synthesise → FFmpeg → write.
3. Synthesis order of preference: Bhashini → Indic Parler-TTS (offline) → edge-tts. Use one voice per language for all clips so mixed prompts do not change speaker.
4. Numbers inside sentences are converted to words with `indic-numtowords` before synthesis ("3,565" → words), so the engine does not depend on the TTS reading digits correctly.
5. `services/audio.py`: `mix_url(clips, lang)` concatenates the WAVs with 150 ms of silence between them using the standard `wave` module, writes `audio/mix/{sha}.wav` if absent, and returns `{PUBLIC_BASE_URL}/audio/mix/{sha}.wav`. FastAPI serves `/audio` as static files.
6. `ensure_dynamic(text, lang) → clip_id`: used by the price job and by the bid-offer job **before** a call is queued. If synthesis fails, the caller falls back to a digit-by-digit composition (`offer_price`, `d_3`, `d_8`, `d_5`, `d_0`), which needs no new audio.

**Code skeleton**

```python
# scripts/prewarm_audio.py (core)
CFG_URL = "https://meity-auth.ulcacontrib.org/ulca/apis/v0/model/getModelsPipeline"

async def bhashini_config(lang):
    body = {"pipelineTasks": [{"taskType": "tts", "config": {"language": {"sourceLanguage": lang}}}],
            "pipelineRequestConfig": {"pipelineId": BHASHINI_PIPELINE_ID}}
    r = await http.post(CFG_URL, json=body,
                        headers={"userID": BHASHINI_USER_ID, "ulcaApiKey": BHASHINI_API_KEY})
    j = r.json()
    ep = j["pipelineInferenceAPIEndPoint"]
    svc = j["pipelineResponseConfig"][0]["config"][0]["serviceId"]
    return ep["callbackUrl"], {ep["inferenceApiKey"]["name"]: ep["inferenceApiKey"]["value"]}, svc

async def bhashini_tts(text, lang, cfg) -> bytes:
    url, headers, svc = cfg
    body = {"pipelineTasks": [{"taskType": "tts", "config": {
                "language": {"sourceLanguage": lang}, "serviceId": svc, "gender": "female"}}],
            "inputData": {"input": [{"source": text}]}}
    r = await http.post(url, json=body, headers=headers, timeout=60)
    return base64.b64decode(r.json()["pipelineResponse"][0]["audio"][0]["audioContent"])   # 22.05 kHz WAV

def to_telephony(src: Path, dst: Path):
    subprocess.run(["ffmpeg", "-y", "-i", str(src),
        "-af", "highpass=f=300,lowpass=f=3400,loudnorm=I=-16:TP=-3:LRA=7",
        "-ar", "8000", "-ac", "1", "-c:a", "pcm_s16le", str(dst)], check=True)
```

Tags: the two endpoints, the header names, the request shapes and the 22,050 Hz base64 WAV response are [Verified] against Bhashini's API documentation. The exact response path `pipelineResponse[0].audio[0].audioContent`, the config path for `serviceId` and the value of `BHASHINI_PIPELINE_ID` (take it from the Bhashini documentation page for the MeitY pipeline) are [Likely] and must be confirmed with the first real call. The FFmpeg filter chain is [Assumed] and must be listened to on a real handset.

**Tests**
- Every clip id referenced in `flows.py` exists for all three languages (a unit test walks `PROMPTS`).
- `ffprobe` on 10 random files: 8000 Hz, 1 channel, `pcm_s16le`.
- A mixed prompt of 6 clips is produced in under 50 ms from a warm disk.
- Listening test on a real button phone speaker and in a noisy room: a second person writes down the quantity and price they hear; 10 of 10 must be correct.
- Bhashini unreachable (block the host): `prewarm_audio.py` falls through to the next engine and the run still completes.

### 7.4 Price and AFPP service

**Purpose.** Give the engine a reference price and a fair farm-gate floor for each district and crop, with a known age.

**Inputs/outputs.** In: data.gov.in mandi API; `deduction_rules`. Out: `mandi_prices`, `price_floors`, Redis `floor:{district}:{crop}`, and a spoken sentence clip.

**Formula**

```
afpp = floor_to_10( modal × (1 − pct_deduction) − transport_per_qtl − handling_per_qtl )
```

Seed values for both pilot districts: `pct_deduction = 0.02`, `transport_per_qtl = 50`, `handling_per_qtl = 10` [Assumed; to be corrected with the FPO's real figures]. Worked example with the price seen on 12 Nov 2026: Mandya ragi modal ₹3,565 [Verified] → 3,565 × 0.98 − 60 = 3,433.7 → **AFPP ₹3,430**. The guardrail fires below 3,430 × 0.97 = ₹3,327.

Why not 6 %: the market fee (0.6 % in Karnataka, 0.75 % in Maharashtra) is paid by the buyer [Verified], so it is not a farmer cost; what the farmer avoids by selling at the collection point is transport and handling, which are rupees per quintal, not a percentage. A percentage alone over-deducts on grain and under-deducts on cheap vegetables.

**Fallback chain** (first that succeeds):

| Basis | Rule | Spoken as |
|---|---|---|
| `DISTRICT_FRESH` | Median modal across the district's markets, newest date, at most 2 days old | "mandi price on (date)" |
| `DISTRICT_7D` | Median of stored district modals over the last 7 days | "average mandi price this week" |
| `STATE_7D` | Median modal for the crop across the state, computed from the state-wide API response at ingestion (not stored row by row) | "state average price this week" |
| none | No floor row is written | "No mandi price is available today"; guardrail skipped, `guardrail='NO_PRICE_DATA'` |

MSP is never used as a floor. It is shown on the buyer dashboard for context only.

**Build steps**
1. Register on data.gov.in for a personal API key (free). The public sample key returns only 10 rows per call [Verified].
2. `ingest_prices.py` (run at 07:00 and 19:00 IST by an asyncio scheduler, and on demand): for each pilot district and crop, call resource `9ef84268-d588-465a-a308-a864a43d0070` with `filters[state.keyword]`, `filters[district]`, `filters[commodity]`; upsert rows; compute the floor; write `price_floors`; set the Redis key; call `ensure_dynamic()` for the sentence in each language. The feed carries only the current day [Verified], so storing it daily is what makes the 7-day fallback possible.
3. Backfill once: pull the last 30 days from the historical resource `35985678-0d79-46b4-9ed6-6f13308a1d24` (`filters[State]`, `filters[District]`, `filters[Arrival_Date]=dd-mm-yyyy`; State and District are mandatory, and older rows return prices as strings) [Verified].
4. `build_crop_calendar.py`: from the same historical resource, count rows per district × month × commodity over the last 3 years, map commodity names to `crops.code`, and write the top 9 per month with ranks into `crop_calendar`. Hand-check the result with the FPO.
5. `pricing.get_floor(district, crop)`: Redis → `price_floors` for today → the most recent row within 7 days → `None`.
6. Outlier guard at ingestion: drop a modal that is more than 40 % away from the 7-day median, and log it.

**Code skeleton**

```python
API = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"

async def fetch_today(state, district, commodity):
    p = {"api-key": settings.DATA_GOV_KEY, "format": "json", "limit": 100,
         "filters[state.keyword]": state, "filters[district]": district, "filters[commodity]": commodity}
    for attempt in range(3):
        try:
            r = await http.get(API, params=p, timeout=10); r.raise_for_status()
            return [dict(market=x["market"], date=datetime.strptime(x["arrival_date"], "%d/%m/%Y").date(),
                         min=float(x["min_price"]), max=float(x["max_price"]), modal=float(x["modal_price"]))
                    for x in r.json().get("records", [])]
        except (httpx.HTTPError, KeyError, ValueError):
            await asyncio.sleep(2 ** attempt)
    return []

def compute_afpp(modal: float, rule) -> int:
    raw = modal * (1 - float(rule.pct_deduction)) - float(rule.transport_per_qtl) - float(rule.handling_per_qtl)
    return int(raw // 10 * 10)
```

**Tests**
- Recorded API response → expected rows and floor (3,565 → 3,430).
- API returns nothing → `DISTRICT_7D` is used; with no history → no row, engine plays `no_price_today`.
- A modal of 35,650 (extra digit) is dropped by the outlier guard.
- Guardrail: price 3,300 → `GUARD`; price 3,400 → `FINAL` (inside the 3 % tolerance).
- `/health` reports `price_age_days`.

### 7.5 Clustering engine

**Purpose.** Pool listings of one crop at one FPO collection point into a truckload, without race conditions.

**Inputs/outputs.** In: a confirmed session (farmer, crop, quantity, price). Out: a `listings` row, an updated `clusters` row, `cluster.updated` and `listing.created` events.

**Why collection points and not centroids.** A cluster built around the first farmer's position drifts as members join, so two farmers 9 km apart can share a "5 km" cluster, and the truck still needs one place to load. Every farmer is assigned at import time to the nearest collection point of their FPO within 5 km. The cluster key is `(collection_point_id, crop_code)`, so a lot can never fit two clusters.

**Build steps**
1. `import_farmers.py` / `POST /api/admin/farmers/import`: for each CSV row, normalise the phone to E.164, then assign the collection point:

```sql
SELECT cp.id
FROM collection_points cp
WHERE cp.fpo_id = $1
  AND ST_DWithin(cp.geog, ST_SetSRID(ST_MakePoint($2, $3), 4326)::geography, 5000)   -- lon, lat
ORDER BY ST_Distance(cp.geog, ST_SetSRID(ST_MakePoint($2, $3), 4326)::geography), cp.id
LIMIT 1;
```

   Rows with no collection point within 5 km are rejected with a reason, so the FPO can add a point or fix the coordinates. Village coordinates come from the FPO; if the roster has only village names, the team looks each one up once on OpenStreetMap and the FPO confirms on a map.
2. `clustering.commit_listing(sess)` in one transaction (skeleton below).
3. `recompute_cluster(conn, cluster_id)` is the only code that writes cluster totals; it is called after every listing change.
4. Withdrawal (`MAIN` → 2) is allowed only while the cluster is `OPEN` or `READY`.
5. Daily sweeper: listings past `expires_at` in `OPEN`/`READY` clusters become `EXPIRED`; recompute.

**Code skeleton**

```python
async def commit_listing(s) -> dict:
    async with db.transaction() as conn:
        f = await conn.fetchrow("SELECT id, collection_point_id FROM farmers WHERE id=$1", s.farmer_id)
        crop = s.data["crop"]
        # serialise all joins for this pickup point and crop
        await conn.execute("SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
                           f"{f['collection_point_id']}:{crop}")
        done = await conn.fetchrow("SELECT id, code, cluster_id FROM listings WHERE session_id=$1", s.id)
        if done: return dict(done)                                    # repeated commit: same answer
        cl = await conn.fetchrow("""SELECT id FROM clusters
              WHERE collection_point_id=$1 AND crop_code=$2 AND status IN ('OPEN','READY')
              FOR UPDATE""", f["collection_point_id"], crop)
        if not cl:
            cl = await conn.fetchrow("""INSERT INTO clusters (collection_point_id, crop_code)
                                        VALUES ($1,$2) RETURNING id""", f["collection_point_id"], crop)
        lst = await conn.fetchrow("""INSERT INTO listings
              (farmer_id, cluster_id, crop_code, qty_qtl, ask_price, afpp_at_listing, guardrail, source, session_id, status)
              VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) RETURNING id, code, cluster_id""",
              f["id"], cl["id"], crop, s.data["qty"], s.data["price"], s.data.get("afpp"),
              s.data.get("guardrail", "NONE"), s.data.get("source", "IVR"), s.id,
              "PENDING_CONFIRM" if s.data.get("source") == "AGENT_PROXY" else "ACTIVE")
        c = await recompute_cluster(conn, cl["id"])
        await events.emit(conn, "listing.created", {"cluster_id": str(cl["id"]), "crop_code": crop,
                          "qty_qtl": s.data["qty"], "ask_price": s.data["price"], "source": s.data.get("source", "IVR")})
        await events.emit(conn, "cluster.updated", c)
        if c["status"] == "READY" and c["became_ready"]:
            await events.emit(conn, "task.created", {"kind": "VERIFY", "ref_id": str(cl["id"])}, audience="agent")
        return dict(lst)

RECOMPUTE = """
UPDATE clusters c SET
  total_qtl = a.q, listing_count = a.n, min_ask = a.mn, wavg_ask = a.w,
  status = CASE WHEN c.status IN ('OPEN','READY')
                THEN CASE WHEN a.q >= 20 THEN 'READY' ELSE 'OPEN' END ELSE c.status END,
  version = c.version + 1, updated_at = now()
FROM (SELECT COALESCE(sum(qty_qtl),0) q, count(*) n, min(ask_price) mn,
             round(sum(qty_qtl*ask_price)/NULLIF(sum(qty_qtl),0), 2) w
      FROM listings WHERE cluster_id = $1 AND status IN ('ACTIVE','ACCEPTED')) a
WHERE c.id = $1
RETURNING c.*"""
```

`events.emit` inserts into `events` inside the same transaction and, after commit, publishes the row on `ad:events`. If the publish is lost, the WebSocket hub's 2-second poll of `events` (by `seq`) still delivers it.

**Tests**
- 50 concurrent `commit_listing` calls for one pickup point and crop → exactly one cluster, `total_qtl` equals the sum, no lost update.
- The live-listing unique index: a second ragi listing by the same farmer is refused and the engine plays `already_listed`.
- Total crosses 20 → status `READY` and one `VERIFY` task.
- Import: a farmer 6 km from every point is rejected; a farmer equidistant from two points always gets the same one.
- Withdraw in `READY` drops the total below 20 → status returns to `OPEN`.

### 7.6 Bidding and outbound calls

**Purpose.** Run an ascending auction per cluster, then collect binding accept/reject keypresses from farmers through a durable, rate-limited call queue.

**Inputs/outputs.** In: bids from the dashboard; auction close; farmer keypresses; call status callbacks. Out: `bids`, `bid_responses`, `call_jobs`, `deals`, events.

**Rules**
- A bid must be ≥ the cluster's `min_ask` and ≥ best bid + ₹10, with `min_qty_qtl ≤ total_qtl`.
- Farmers are called only once per auction, for the winning bid.
- Confirmation needs two keypresses (`1`, then `1`).
- A round resolves when no response is `PENDING` or at `confirm_deadline` (2 hours; 90 s in demo mode). Unanswered lots count as not accepted.
- Accepted quantity ≥ `min_qty_qtl` → deal. Otherwise the bid fails; the cluster returns to `BIDDING` with a fresh window once, then `NO_BID`.
- Lots that did not accept are moved to the joinable cluster for the same pickup point and crop and stay `ACTIVE`.
- Outbound calls: at most 5 at once, 3 attempts per job with waits of 2, 10 and 30 minutes (±20 % jitter), only between 08:00 and 20:00 IST (off in demo mode), and never beyond `DAILY_CALL_BUDGET`.

**Code skeleton**

```python
# services/bidding.py
async def place_bid(buyer_id, cluster_id, price, min_qty, idem_key):
    async with db.transaction() as conn:
        prior = await conn.fetchrow("SELECT * FROM bids WHERE buyer_id=$1 AND idempotency_key=$2", buyer_id, idem_key)
        if prior: return dict(prior), False
        c = await conn.fetchrow("""SELECT c.id, c.status, c.total_qtl, c.min_ask, c.best_bid_id, b.price_per_qtl AS best
              FROM clusters c LEFT JOIN bids b ON b.id = c.best_bid_id
              WHERE c.id=$1 FOR UPDATE OF c""", cluster_id)
        if not c or c["status"] != "BIDDING": raise ApiError(409, "CLUSTER_NOT_BIDDING")
        floor = max(c["min_ask"], (c["best"] or 0) + 10)
        if price < floor: raise ApiError(409, "BID_TOO_LOW", min_next=float(floor))
        if min_qty > c["total_qtl"]: raise ApiError(422, "MIN_QTY_TOO_HIGH")
        if c["best_bid_id"]:
            await conn.execute("UPDATE bids SET status='OUTBID' WHERE id=$1", c["best_bid_id"])
        bid = await conn.fetchrow("""INSERT INTO bids (cluster_id,buyer_id,price_per_qtl,min_qty_qtl,idempotency_key)
              VALUES ($1,$2,$3,$4,$5) RETURNING *""", cluster_id, buyer_id, price, min_qty, idem_key)
        cl = await conn.fetchrow("UPDATE clusters SET best_bid_id=$2, version=version+1, updated_at=now() WHERE id=$1 RETURNING *",
                                 cluster_id, bid["id"])
        await events.emit(conn, "bid.placed", {"cluster_id": str(cluster_id), "bid_id": str(bid["id"]),
                          "price_per_qtl": float(price)}, audience="buyer")
        await events.emit(conn, "cluster.updated", cl)
        return dict(bid), True
    # the API layer catches UniqueViolation on (buyer_id, idempotency_key) and re-reads the prior bid

async def close_auction(cluster_id):
    async with db.transaction() as conn:
        c = await conn.fetchrow("SELECT * FROM clusters WHERE id=$1 FOR UPDATE", cluster_id)
        if c["status"] != "BIDDING": return
        if not c["best_bid_id"]:
            await conn.execute("UPDATE clusters SET status='NO_BID', version=version+1 WHERE id=$1", cluster_id); return
        deadline = now() + (timedelta(seconds=90) if settings.DEMO_MODE else timedelta(hours=2))
        await conn.execute("UPDATE bids SET status='CONFIRMING', confirm_deadline=$2 WHERE id=$1", c["best_bid_id"], deadline)
        await conn.execute("UPDATE clusters SET status='CONFIRMING', version=version+1 WHERE id=$1", cluster_id)
        rows = await conn.fetch("""SELECT l.id, f.id AS farmer_id, f.phone FROM listings l JOIN farmers f ON f.id=l.farmer_id
                                   WHERE l.cluster_id=$1 AND l.status='ACTIVE'""", cluster_id)
        for r in rows:
            await conn.execute("INSERT INTO bid_responses (bid_id, listing_id) VALUES ($1,$2) ON CONFLICT DO NOTHING",
                               c["best_bid_id"], r["id"])
            await conn.execute("""INSERT INTO call_jobs (phone, farmer_id, kind, payload, dedupe_key)
                  VALUES ($1,$2,'BID_OFFER',$3,$4) ON CONFLICT (dedupe_key) DO NOTHING""",
                  r["phone"], r["farmer_id"], json.dumps({"bid_id": str(c["best_bid_id"]), "listing_id": str(r["id"])}),
                  f"bid:{c['best_bid_id']}:{r['id']}")

async def record_response(bid_id, listing_id, response):          # called by the engine on OFFER_CONFIRM / reject
    n = await db.execute("""UPDATE bid_responses SET response=$3, responded_at=now()
                            WHERE bid_id=$1 AND listing_id=$2 AND response='PENDING'""", bid_id, listing_id, response)
    if n == "UPDATE 1": await resolve_round(bid_id)                # first write wins; a repeat is a no-op

async def resolve_round(bid_id):
    async with db.transaction() as conn:
        b = await conn.fetchrow("SELECT * FROM bids WHERE id=$1", bid_id)
        c = await conn.fetchrow("SELECT * FROM clusters WHERE id=$1 FOR UPDATE", b["cluster_id"])
        if c["status"] != "CONFIRMING" or c["best_bid_id"] != bid_id: return
        t = await conn.fetchrow("""SELECT
              COALESCE(sum(l.qty_qtl) FILTER (WHERE r.response='ACCEPT'),0)  AS acc,
              COALESCE(sum(l.qty_qtl) FILTER (WHERE r.response='PENDING'),0) AS pend
              FROM bid_responses r JOIN listings l ON l.id=r.listing_id WHERE r.bid_id=$1""", bid_id)
        if t["pend"] > 0 and now() < b["confirm_deadline"]:
            await events.emit(conn, "bid.confirming", {...}, audience="buyer"); return
        if t["acc"] >= b["min_qty_qtl"]:
            gross = t["acc"] * b["price_per_qtl"]
            await conn.execute("""INSERT INTO deals (cluster_id,bid_id,buyer_id,qty_qtl,price_per_qtl,gross_value,platform_fee,pickup_by)
                  VALUES ($1,$2,$3,$4,$5,$6,round($6*0.015,2), current_date + 3) ON CONFLICT DO NOTHING""",
                  c["id"], bid_id, b["buyer_id"], t["acc"], b["price_per_qtl"], gross)
            # accepting listings → ACCEPTED; others re-pooled via find-or-create; bid → DEAL; cluster → DEAL
        else:
            # bid → FAILED; cluster → BIDDING (first failure, new window) or NO_BID; cancel QUEUED jobs for this bid
            ...
```

```python
# services/jobs.py
CLAIM = """UPDATE call_jobs SET status='DIALING', attempts=attempts+1, updated_at=now()
           WHERE id = (SELECT id FROM call_jobs WHERE status='QUEUED' AND run_at <= now()
                       ORDER BY run_at FOR UPDATE SKIP LOCKED LIMIT 1)
           RETURNING *"""
BACKOFF_MIN = [2, 10, 30]
sem = asyncio.Semaphore(5)

async def request_callback(phone):                       # from the missed-call webhook
    day = date.today().strftime("%Y%m%d")
    ok = await cache.evalsha(ALLOW_CALLBACK, 3, f"rl:cb:{phone}:10m", f"rl:cb:{phone}:day",
                             f"budget:calls:{day}", 3, 6, settings.DAILY_CALL_BUDGET)
    if ok != 1: return
    farmer = await db.fetchrow("SELECT id, status FROM farmers WHERE phone=$1", phone)
    if farmer and farmer["status"] == "BLOCKED": return
    minute = int(time.time() // 60)
    await db.execute("""INSERT INTO call_jobs (phone, farmer_id, kind, dedupe_key)
          VALUES ($1,$2,'CALLBACK',$3) ON CONFLICT (dedupe_key) DO NOTHING""",
          phone, farmer["id"] if farmer else None, f"cb:{phone}:{minute}")

async def worker():
    while True:
        job = await db.fetchrow(CLAIM)
        if not job: await asyncio.sleep(1); continue
        asyncio.create_task(run(job))

async def run(job):
    async with sem:
        token = secrets.token_hex(8)
        if not await cache.set(f"lock:call:{job['phone']}", token, nx=True, px=300_000):
            return await requeue(job, minutes=1, count_attempt=False)       # farmer is already on a call
        try:
            await prepare_audio(job)                                        # dynamic clips exist before dialing
            call_id = await adapter.place_call(job["phone"], str(job["id"]))
            await cache.set(f"callmap:{adapter.name}:{call_id}", job["phone"], ex=3600)
            await db.execute("UPDATE call_jobs SET status='IN_CALL', provider_call_id=$2 WHERE id=$1", job["id"], call_id)
        except Exception as e:
            await cache.evalsha(RELEASE_LOCK, 1, f"lock:call:{job['phone']}", token)
            await fail_or_retry(job, str(e))

async def on_call_status(job_id, status):                 # provider status callback / simulator hangup
    # completed → DONE. no-answer / busy / failed → fail_or_retry.
    # fail_or_retry: attempts < max_attempts → QUEUED, run_at = now + BACKOFF_MIN[attempts-1] min ± 20 %;
    #                else FAILED, and for BID_OFFER record_response(..., 'NO_ANSWER').
    ...
```

**Tests**
- 20 buyers bid at once on one cluster → exactly one `LEADING` bid, the highest valid one; all others `OUTBID` or rejected with `BID_TOO_LOW`.
- Same `Idempotency-Key` sent three times → one bid, three identical responses.
- Farmer presses 1-1 on two overlapping calls (forced) → one `ACCEPT`, the second update affects 0 rows.
- 8 lots, 5 accept (15 of 24 quintals), `min_qty_qtl = 15` → deal for 15 quintals; the other 3 lots land in a new `OPEN` cluster.
- Same with `min_qty_qtl = 20` → bid `FAILED`, cluster back to `BIDDING`.
- Kill the worker with jobs `DIALING` → the sweeper re-queues them after 6 minutes; no job is lost or run twice at the same time (`SKIP LOCKED`).
- Unanswered call → retried at about 2, 10, 30 minutes, then `NO_ANSWER`.
- Daily budget set to 3 → the fourth callback request is refused and `/health` shows the breaker.

### 7.7 Buyer dashboard

**Purpose.** Let an approved buyer see pooled clusters, bid, follow confirmation live, and complete the payment handoff.

**Inputs/outputs.** REST (section 6.2) and WebSocket (section 6.6).

**Build steps**
1. Vite + React + TypeScript + Tailwind; routes `/buyer`, `/agent`, `/sim`, `/ops`, `/login`.
2. `lib/ws.ts`: one hook with replay and backoff (skeleton below).
3. `/buyer` layout: left, cluster list with filters (crop, status); centre, Leaflet map with one marker per collection point sized by tonnage; right, detail panel with lots ("Lot 1 · 3 qtl · ask ₹3,600"), grade, photo, countdown, bid form.
4. Bid form: price and minimum quantity; shows "at ₹3,700, 18 of 24 quintals have an asking price at or below your bid" (computed client-side from the lots); a fresh `crypto.randomUUID()` per submission attempt, reused on retry.
5. Confirmation view: progress bar of accepted / rejected / pending quintals driven by `bid.confirming`.
6. Deal view: FPO payee details, amount (accepted quantity × price), platform fee (1.5 %), a field for the payment reference, status timeline.
7. Seed data is labelled "demo data" in the UI.

**Code skeleton**

```ts
// lib/ws.ts
export function useEvents(onEvent: (e: Ev) => void) {
  useEffect(() => {
    let ws: WebSocket, stop = false, delay = 1000;
    const open = () => {
      const since = Number(localStorage.getItem("seq") ?? 0);
      ws = new WebSocket(`${WS_BASE}/ws?token=${token()}&since=${since}`);
      ws.onopen = () => { delay = 1000; };
      ws.onmessage = (m) => {
        const e: Ev = JSON.parse(m.data);
        if (e.type === "resync") { refetchAll(); return; }
        if (e.seq <= Number(localStorage.getItem("seq") ?? 0)) return;   // at-least-once: drop repeats
        localStorage.setItem("seq", String(e.seq));
        onEvent(e);
      };
      ws.onclose = () => { if (!stop) setTimeout(open, delay); delay = Math.min(delay * 2, 15000); };
    };
    open();
    return () => { stop = true; ws.close(); };
  }, []);
}
```

Cluster state in the client is keyed by `id` and replaced only when the incoming `version` is higher, so out-of-order events cannot roll the screen back.

**Tests**
- Two browser windows: a listing made in the simulator appears in both in under 1 second.
- Turn Wi-Fi off for 20 s during bidding, then on → missed events are replayed, no duplicates, final state matches REST.
- A `PENDING` buyer sees clusters but the bid button is disabled and the API returns 403.
- No farmer name or phone appears in any network response (automated check on the JSON).

### 7.8 FPO agent PWA

**Purpose.** Let the FPO's field agent verify a cluster at the collection point, work the helper queue, confirm payment and record pickup, on a low-end Android phone.

**Inputs/outputs.** REST (section 6.3); camera; geolocation.

**Build steps**
1. `/agent` route with `vite-plugin-pwa` (manifest, install prompt, cached shell). It must be opened over HTTPS (the ngrok URL), because camera and location need a secure context.
2. Tabs: **Verify**, **Helper queue**, **Pickups**.
3. Verify screen: live camera preview with `getUserMedia({video:{facingMode:"environment"}})`, capture to canvas, JPEG at quality 0.7 (under 2 MB); at the same moment read `navigator.geolocation.getCurrentPosition({enableHighAccuracy:true})`; send both with grade (A/B/C/Reject) and optional moisture. A file picker is deliberately not offered: `capture="environment"` on a file input is only a hint and still allows gallery uploads [Verified], and EXIF location is often stripped by mobile browsers [Likely].
4. The server computes distance to the collection point and rejects captures more than 500 m away, older than 10 minutes, or with reported accuracy worse than 200 m:

```sql
SELECT ST_Distance(cp.geog, ST_SetSRID(ST_MakePoint($2, $3), 4326)::geography) AS distance_m
FROM clusters c JOIN collection_points cp ON cp.id = c.collection_point_id WHERE c.id = $1;
```

5. Grade `REJECT` returns the cluster to `OPEN` with a note; any other grade moves it to `BIDDING` and sets `bidding_ends_at`.
6. Pickups: shows deals `PAID`; the agent enters weighed quintals per lot; submit moves the deal to `PICKED_UP`, listings to `SOLD`, recomputes `qty_qtl`, `gross_value` and `platform_fee` from actual weights, and writes the two `ledger` rows.

**Code skeleton**

```ts
async function captureAndSend(clusterId: string, grade: string, moisture?: number) {
  const pos = await new Promise<GeolocationPosition>((ok, err) =>
    navigator.geolocation.getCurrentPosition(ok, err, { enableHighAccuracy: true, timeout: 15000 }));
  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth; canvas.height = video.videoHeight;
  canvas.getContext("2d")!.drawImage(video, 0, 0);
  const blob: Blob = await new Promise(r => canvas.toBlob(b => r(b!), "image/jpeg", 0.7));
  const fd = new FormData();
  fd.append("photo", blob, "v.jpg"); fd.append("grade", grade);
  if (moisture != null) fd.append("moisture_pct", String(moisture));
  fd.append("lat", String(pos.coords.latitude)); fd.append("lon", String(pos.coords.longitude));
  fd.append("accuracy_m", String(pos.coords.accuracy)); fd.append("captured_at", new Date().toISOString());
  return api.post(`/api/agent/clusters/${clusterId}/verification`, fd);
}
```

**Tests**
- Submit from 2 km away (use the browser's location override) → `422 TOO_FAR`.
- Submit twice → second returns `409` (unique `cluster_id`).
- An agent from another FPO cannot see or verify the cluster (403).
- Pickup before `PAID` → `409`.
- Works on a ₹6,000 Android phone on mobile data through the tunnel.

### 7.9 Triage bridge (helper queue)

**Purpose.** No farmer is left out because the keypad flow defeated them, without exposing phone numbers or letting an agent invent a listing.

**Inputs/outputs.** In: `fail:{phone}` reaching 3, the `0` key, an unknown caller. Out: `triage_tickets`, a masked call, a `PENDING_CONFIRM` listing, a `PROXY_CONFIRM` call.

**Build steps**
1. `triage.open_ticket(phone, reason)`: insert (the partial unique index keeps one open ticket per phone), generate a random two-digit `verbal_code` with `code_expires_at = now() + 24 h`, emit `task.created`.
2. The `HELP` state (and the third failed call's goodbye) plays `helper_will_call` followed by the two code digits, so the farmer hears the code from the system, not from the caller.
3. Agent PWA "Helper queue": shows village and first name only, never the number. **Claim**, then **Call**.
4. `POST …/bridge`: checks the code has not expired or been used, marks it used, returns it to the agent's screen, and calls `adapter.bridge(agent_phone, farmer_phone)`. On Exotel this is the two-number connect request, so both phones show the platform number [Verified: endpoint; masking behaviour Likely]. On the simulator the response says `mode:"simulated"` and the UI shows a banner.
5. The agent says the code first. The farmer's instruction in the IVR message is: "Only talk to a helper who says this code."
6. Proxy listing: the agent enters crop, quantity and price; the server creates the listing as `PENDING_CONFIRM` (not counted in the cluster) and queues a `PROXY_CONFIRM` call. The farmer hears the entry read back and presses 1 to activate it, or 2 to discard it and flag the ticket.
7. The ticket is `RESOLVED` when the listing is confirmed or the agent closes it with a reason.

**Tests**
- Three failed simulator calls → one ticket, and a fourth failure does not create a second.
- The code is shown once; a second `bridge` call returns `409 CODE_USED`; after 24 hours `409 CODE_EXPIRED`.
- A proxy listing that the farmer rejects never appears on the buyer dashboard.
- A proxy listing that is never confirmed expires after 48 hours (sweeper).
- The agent API never returns a farmer phone number (automated JSON check).

---

## 8. Vulnerability register

Format: ID | Severity | What breaks | How it is exploited or fails | Best fix (all inside this plan) | Free? | Residual risk. Every Critical and High item has its fix in sections 5–7.

### 8.1 Telephony and network

| ID | Sev | What breaks | How it fails | Best fix | Free? | Residual risk |
|---|---|---|---|---|---|---|
| T1 | High | Prompts unintelligible | 8 kHz narrowband (about 300–3,400 Hz) plus a tiny handset speaker and field noise lose consonants and number endings | Short sentences; numbers as whole pre-generated phrases or digit by digit; 300–3,400 Hz band-pass and −16 LUFS normalisation; handset listening test (section 7.3) | Yes | Dialect mismatch; some users still need the helper |
| T2 | High | Wrong quantity or price stored | Double press, wrong key, or a duplicated digit from inband-plus-RFC 4733 double detection on a SIP leg | Range checks per crop, spoken readback and explicit `1` to confirm at `QTY_CONFIRM` and `FINAL`; single-key menus collect exactly 1 digit | Yes | A farmer who confirms a wrong number without listening |
| T3 | Medium | Debounce deletes real digits | A 250 ms window (original plan) drops the second `0` of `3800` | 120 ms same-digit window, 40 ms any-digit window, applied only where per-digit timing exists | Yes | 120 ms is an engineering estimate, tune with real handsets |
| T4 | Medium | Debounce impossible on cloud PBX | Exotel's Gather returns a finished string; timing is invisible | State this openly; rely on T2 controls there | Yes | None beyond T2 |
| T5 | High | Farmer must restart after a drop | 2G call drops mid-flow | Session in Redis for 30 min keyed by phone, checkpoint in Postgres, "welcome back" resume at the saved state | Yes | Drops after 30 min restart |
| T6 | High | Callback never arrives | Provider error, farmer out of coverage, phone busy | Durable `call_jobs`, 3 attempts at 2/10/30 min with jitter, status callback, stuck-job sweeper | Yes | Farmer unreachable all day; they can missed-call again |
| T7 | High | Retry storm | Provider outage makes every job fail and retry together | Jittered backoff, max 3 attempts, 5 concurrent calls, daily budget breaker | Yes | Backlog after a long outage (jobs expire, farmers re-call) |
| T8 | Medium | Two calls to one farmer at once | Farmer missed-calls repeatedly, or a bid call collides with a callback | `miss:{phone}` 20 s dedupe, `lock:call:{phone}`, job re-queued without counting an attempt | Yes | Lock lost on Redis flush; Postgres constraints still protect data |
| T9 | High | Fake events injected | Exotel documents no webhook signature; anyone who learns the URL can post digits | 32-char secret in the path, constant-time compare, accept only `CallSid`s we created (`callmap`), HTTPS only | Yes | Secret leak through logs; rotate it |
| T10 | Medium | Farmer is charged | Provider answers before hanging up, or the farmer calls a non-missed-call number | Use the provider's missed-call mode (auto-hangup after 1–2 rings); test with a prepaid SIM and check the balance before and after | Yes | We cannot guarantee operator behaviour; say "designed to be free", not "impossible to charge" |
| T11 | Medium | Farmer forgets `#` | Multi-digit entry never terminates | Input timeout also ends entry (8–10 s) | Yes | Slow typists cut off; readback catches it |
| T12 | Low | Flow chain too short on Exotel | More than 12 prompt steps in one call | Call ends politely, session resumes on next callback; loop-back wiring if the spike allows | Yes | Extra callback |
| T13 | Medium | Farmer answers, hears nothing | Audio URL unreachable from the provider (tunnel down) | Health check fetches a clip through `PUBLIC_BASE_URL` at start-up and every minute; provider fallback URL plays a static "please call later" | Yes | Tunnel outage during a call |

### 8.2 Distributed systems

| ID | Sev | What breaks | How it fails | Best fix | Free? | Residual risk |
|---|---|---|---|---|---|---|
| D1 | High | Session lost mid-call | Redis restart, flush or eviction | Write-through checkpoint to `call_sessions`; rehydrate on miss | Yes | Up to one in-flight transition lost; the prompt is replayed |
| D2 | High | Step applied twice | Provider retries a webhook (at-least-once) | `evt:{call_id}:{event_id}` returns the cached Action | Yes | Event ids on Exotel depend on the `step` parameter wiring [Assumed] |
| D3 | High | Lost update on a session | Two handlers race (retry overlaps original) | `session_cas.lua` version check; loser retries | Yes | None known |
| D4 | Critical | Duplicate listing or wrong cluster totals | Concurrent joins, repeated commit | Advisory transaction lock per (pickup point, crop), `listings.session_id` unique, totals only via `recompute_cluster` | Yes | None known |
| D5 | Critical | Two winning bids | Two buyers bid at the same instant | `SELECT … FOR UPDATE` on the cluster row inside `place_bid`; single `best_bid_id` | Yes | None known |
| D6 | Critical | Double accept, or accept after the round closed | Farmer presses twice; late call after deadline | `UPDATE … WHERE response='PENDING'`; `resolve_round` re-checks cluster status under lock; deal unique on cluster and bid | Yes | None known |
| D7 | High | Duplicate bid on retry | Buyer's browser retries a timed-out POST | Required `Idempotency-Key`, unique per buyer | Yes | None known |
| D8 | Medium | Dashboard misses or repeats events | WebSocket reconnect; pub/sub message lost | `events` outbox with `seq`, replay with `since`, hub polls every 2 s, client drops `seq` ≤ last and older `version` | Yes | Up to 2 s delay |
| D9 | Medium | Queue backpressure | 200 bid calls queued with 5 lines | Queue is durable; round deadline (2 h) bounds waiting; unanswered = not accepted; dashboard shows pending quintals | Yes | Large clusters may not finish in 2 h; raise concurrency on a paid plan |
| D10 | Medium | Job stuck forever | Worker dies after claiming | Sweeper resets `DIALING`/`IN_CALL` older than 6 min | Yes | A call may be placed twice in rare cases; the engine resumes the session |
| D11 | Medium | Redis lock held by two clients | Process pause beyond TTL | Lock is advisory only; correctness lives in Postgres constraints | Yes | A rare double call |
| D12 | Low | Clock skew on deadlines | Laptop clock wrong | All deadlines computed with database `now()` | Yes | None |

### 8.3 Data and geography

| ID | Sev | What breaks | How it fails | Best fix | Free? | Residual risk |
|---|---|---|---|---|---|---|
| G1 | High | Farmer placed in the wrong cluster | Wrong or missing coordinates in the FPO roster | Import validates every row against a 5 km radius of an FPO collection point and rejects outliers; FPO confirms on a map | Yes | A wrong village inside the radius |
| G2 | Medium | Lot fits two clusters | Radius-based clusters overlap | Cluster key is `(collection_point_id, crop)`; nearest point with id tie-break is assigned once at import | Yes | None |
| G3 | Medium | Unknown caller has no location | Not in any roster | No listing; one "not registered" callback a day and a helper ticket | Yes | Slower onboarding |
| G4 | Low | H3 resolution vs 5 km | Hexagon edges do not match a 5 km circle (resolution 7 has an edge of roughly 1.4 km, resolution 6 roughly 3.7 km [Assumed]) | H3 removed; `ST_DWithin` on `geography` gives true metres | Yes | None |
| G5 | Medium | Same crop, different variety or grade pooled | Fine and coarse paddy in one cluster | Crop list uses variety-level codes where price differs (`paddy_common`, `paddy_fine`); agent grades the cluster and can reject | Yes | Mixed quality inside one grade |
| G6 | Low | Number changed hands | SIM recycled to another person | Consent is asked again if the roster row is re-imported with a new name; FPO owns roster hygiene | Yes | Stale rosters |

### 8.4 Pricing

| ID | Sev | What breaks | How it fails | Best fix | Free? | Residual risk |
|---|---|---|---|---|---|---|
| P1 | High | Guardrail uses stale or missing price | The feed has only the current day and thin coverage (Mandya had 7 rows on 12 Nov 2026) | Store daily; fallback chain with spoken basis and date; skip the guardrail when nothing is usable | Yes | Thinly traded crops often fall back to weekly or state figures |
| P2 | High | Floor too high, listings never sell | Wrong deduction, MSP used as floor, outlier price | Per-district rupee deductions; MSP never a floor; 40 % outlier filter; farmer may always keep their own price | Yes | Deduction values are assumed until the FPO supplies real ones |
| P3 | Medium | Floor too low, farmer under-prices | Mandi modal itself depressed | Speak the mandi price as well as the floor; the auction can only raise the price | Yes | Structural low prices are outside our control |
| P4 | Medium | Buyer collusion or lowballing | Few buyers agree not to outbid | Bid must be ≥ `min_ask`; farmers can reject; onboard at least 3 buyers per district before launch | Yes | Thin buyer side in a pilot |
| P5 | Medium | Shill listings to move the average | A farmer lists a huge quantity at a silly price | Quantity cap per listing, price bounds per crop, one live listing per crop, FPO-roster-only | Yes | Collusion among several real members |
| P6 | Low | Commodity name mismatch | "Ragi(Finger Millet)" vs "Ragi" | `crops.agmark_name` stores the feed's exact string | Yes | New spellings need a manual fix |

### 8.5 Fraud and abuse

| ID | Sev | What breaks | How it is exploited | Best fix | Free? | Residual risk |
|---|---|---|---|---|---|---|
| F1 | High | Call credit drained | Missed-call spam or call-bombing from many numbers | Per-number limits (3 per 10 min, 6 per day), unknown numbers get 1 callback a day, global `DAILY_CALL_BUDGET` breaker | Yes | A determined attacker stops the service for the day but cannot run up cost |
| F2 | High | Fake buyers | Bids with no intent to pay, to block clusters | Admin approval with licence number; 3 strikes suspends; "no payment, no loading" | Yes | First-time no-show still wastes one cycle |
| F3 | High | Fake or inflated lots | Farmer lists grain they do not have | Roster-only, caps, FPO verification before bidding, weighing at pickup; price is paid on weighed quantity | Yes | Shortfall discovered at pickup; buyer's `min_qty` may be missed |
| F4 | High | Agent fakes verification | Uploads an old photo from home | Live camera capture only, server-side distance (≤ 500 m), freshness (≤ 10 min) and accuracy checks; photo shown to buyers | Yes | GPS spoofing apps; add random FPO-manager spot checks |
| F5 | High | Agent invents or alters a listing | Proxy entry at a lower price to favour a buyer | Proxy listings stay `PENDING_CONFIRM` until the farmer confirms on an automatic call that reads the entry back | Yes | A farmer who presses 1 without listening |
| F6 | Medium | Impersonation of the helper | Someone calls the farmer claiming to be the helper | The IVR tells the farmer a single-use two-digit code, valid 24 h; the agent sees it only when the masked call starts | Yes | 1-in-100 guess; it is a recognition aid, not authentication for money |
| F7 | Medium | Replay of the verbal code | Old code reused | `code_used` flag and expiry | Yes | None |
| F8 | High | Disintermediation | Buyer and FPO deal directly next season and skip the fee | Farmer numbers are never shown to buyers or agents; the value we keep providing is pooling of non-smartphone members, price reference and buyer competition; fee kept low | Yes | **Not solved.** The FPO and buyer do meet at pickup. Treat as a business risk (section 16) |
| F9 | Medium | Caller-ID spoofing | A spoofed missed call makes us call a real farmer | We only ever call the roster number back, and nothing is committed without that person's keypress | Yes | Nuisance calls, bounded by F1 |
| F10 | Medium | Credential stuffing on the dashboard | Weak buyer passwords | bcrypt, 5 failed logins → 15 min lock (Redis counter), JWT expiry 12 h | Yes | No second factor in the pilot |

### 8.6 Privacy and legal

| ID | Sev | What breaks | How it fails | Best fix | Free? | Residual risk |
|---|---|---|---|---|---|---|
| L1 | High | Phone numbers exposed | Buyer or agent API leaks them | Buyer responses carry lot numbers only; agent sees village and first name; ops view masks to last 4 digits; automated JSON test | Yes | Database access by the team; restrict and log |
| L2 | High | No valid consent | Calls and storage without notice | `CONSENT` state in the farmer's language on the first call, `consent_log` row with session and keypress; withdrawal through the helper | Yes | Whether a keypress after an audio notice satisfies the DPDP "clear affirmative action" test is untested [Assumed]; substantive DPDP duties start 13 May 2027 [Likely] |
| L3 | Medium | Unlawful call recording | Recording without consent | **No audio is recorded.** Only keypresses are logged | Yes | Less evidence in a dispute |
| L4 | High | Automated calls breach TRAI rules | Auto-dialler calls from an ordinary number at scale; SMS without DLT | Pilot: only calls to roster members who called first or accepted calls in the consent step, on a provider trial. Production: DLT registration, registered headers, 1600-series for service calls through the provider | Pilot yes; production no (about ₹5,900 plus provider plan) | Whether a non-BFSI private sender must use the 1600 series is unverified |
| L5 | High | Handling trade money without a licence | Platform escrow | Platform never receives trade money; buyer pays the FPO | Yes | Fee collection from buyers is by invoice |
| L6 | High | Trading notified produce outside the market yard | State APMC law. Karnataka's 2025 amendment reportedly requires e-commerce platforms trading notified produce to be licensed [Likely]; Maharashtra needs a direct-marketing licence for non-fruit-and-vegetable produce [Likely] | Pilot under an FPO's own sales to licensed traders, with the platform as the FPO's software tool; legal check before any commercial launch | Pilot yes | **Unresolved for production** (section 16) |
| L7 | Medium | Weight disputes | Unverified scale | Weigh on the FPO's stamped scale at pickup; agent enters per-lot weights | Yes | Scale tampering |
| L8 | Medium | Bhashini terms | API is for proof of concept only [Verified] | Fine for the demo and a non-commercial pilot; ask Bhashini for terms or switch to Indic Parler-TTS (Apache-2.0) before charging anyone | Yes | Parler-TTS quality and speed on CPU |
| L9 | Low | Data breach duty | Leak of the roster | Minimal data (name, phone, village), no Aadhaar, no bank details; documented breach contact | Yes | Small team, no security review |

### 8.7 Accessibility

| ID | Sev | What breaks | How it fails | Best fix | Free? | Residual risk |
|---|---|---|---|---|---|---|
| A1 | High | Elderly or low-literacy users fail | Menus too long, time-outs too short | At most 3 options plus 9 and 0; 6–10 s time-outs; 2 replays; third failure → helper | Yes | Some users will always need a person |
| A2 | Medium | Dialect or language gap | Standard Kannada TTS vs local speech; a Tulu or Urdu speaker | Native-speaker review of every prompt; language choice on first call; helper for the rest | Yes | Only 3 languages |
| A3 | Medium | Numbers misheard | "Fifteen" vs "fifty" | Quantity as a whole phrase, price digit by digit, then confirm | Yes | See T2 |
| A4 | Low | Units confusion | Farmers think in bags (50 kg, 100 kg) or kg | Prompt says "quintals, one quintal is 100 kilos"; helper can enter for them | Yes | Some mis-entries; bounded by caps and weighing |
| A5 | Low | Shared phone | Another family member answers a bid call | The offer names the crop and quantity; two-step confirm; reject is always available | Yes | A family member accepts in good faith |

### 8.8 Operations

| ID | Sev | What breaks | How it fails | Best fix | Free? | Residual risk |
|---|---|---|---|---|---|---|
| O1 | High | Nobody verifies grade | No agent available, ₹50 too little | The agent is FPO staff already at the collection point; one visit per cluster, not per farmer; payout rate is a config value | Yes | ₹50 may be too low; decide with the FPO |
| O2 | High | No buyer bids | Thin demand | Cluster goes `NO_BID`; listings stay 7 days; farmer hears status on their next missed call (no extra call cost); FPO sees the list and can sell through its usual channel | Yes | The platform adds nothing when there are no buyers |
| O3 | High | Truck does not arrive | Buyer no-show | `pickup_by` date; agent marks no-show; deal cancelled, buyer strike, cluster back to `BIDDING` | Yes | Farmers lose days; perishable crops are out of scope for the pilot |
| O4 | High | Payment dispute | Buyer claims payment, FPO did not receive it | "No payment, no loading": pickup can be recorded only after the FPO agent confirms receipt | Yes | Dispute over quality after loading is settled between FPO and buyer |
| O5 | Medium | Quality differs at loading | Lot worse than the sample | Deal is at the verified grade; the agent may exclude a lot at pickup (weight 0), which reduces the deal value | Yes | Buyer may refuse the whole load |
| O6 | Medium | Farmer changes mind after accepting | Sells elsewhere before pickup | Lot recorded with weight 0 at pickup; repeated cases flagged to the FPO | Yes | Buyer's minimum quantity can be missed |

### 8.9 Demo day

| ID | Sev | What can fail live | Fallback |
|---|---|---|---|
| X1 | High | Venue Wi-Fi or tunnel down | Everything runs on the laptop; switch `TELEPHONY_PROVIDER` to `sim`; phone hotspot as the second network |
| X2 | High | No GSM signal in the hall, or Exotel trial expired or out of credit | Simulator on the projector with the same audio; say clearly that the phone leg is simulated |
| X3 | Medium | data.gov.in slow or down | Prices already stored that morning; `/health` shows age; seeded history |
| X4 | Medium | Bhashini down | All clips are on disk; dynamic sentences fall back to digit-by-digit clips |
| X5 | Medium | Cold start | Nothing in the primary path sleeps (local). Cloud mirror is woken 10 minutes before |
| X6 | Medium | Map tiles blocked | List view; map panel hides itself on tile error |
| X7 | Low | Laptop failure | Second laptop with the repository, volumes and audio folder cloned the night before; recorded video as last resort |
| X8 | Low | Docker will not start | Native PostgreSQL + PostGIS and Valkey installed as Windows services on the backup laptop |

---

## 9. Enhancements added

Only additions that close a Critical or High gap, or that replace something cut. Effort is in person-days (pd).

| # | Addition | Problem it solves | Why the original plans fell short | Effort | Cost | What it replaces |
|---|---|---|---|---|---|---|
| E1 | Collection-point anchored clusters | Drifting centroids, lots that fit two clusters, no defined loading place | Plans clustered around the first lot | 0.5 pd | Free | H3 and the over-subscription buffer |
| E2 | Postgres checkpoint of sessions and an events outbox | Redis loss mid-call; missed WebSocket events | Plans had Redis as the only session store and no replay | 1 pd | Free | Supabase Realtime |
| E3 | Simulator with 8 kHz audio, per-digit timing, bounce and drop injection | A free, honest way to show network behaviour and a fallback when GSM fails | P3's simulator was a visual mock | 1.5 pd | Free | Twilio trial integration |
| E4 | Durable call-job queue with backoff, calling hours and a daily budget breaker | Retry storms, credit drain, lost callbacks | Plans called the provider directly from the webhook | 1 pd | Free | — |
| E5 | Spoken consent and a keypress evidence log | Consent and dispute evidence without recording audio | Plans had no consent step | 0.5 pd | Free | Call recording |
| E6 | Spoken listing number and status on the next missed call | Receipt without DLT SMS | SMS needs paid registration | 0.5 pd | Free | SMS receipts |
| E7 | FPO as seller of record, "no payment, no loading", buyer strikes | Lawful settlement and no-show handling without holding money | Escrow needs an RBI authorisation | 1 pd | Free | Escrow, e-RUPI, 2 % penalty |
| E8 | Two-step accept and a round that resolves on `min_qty_qtl` | Accidental accepts; clusters falling below truck size | Single keypress; fixed over-subscription | 0.5 pd | Free | Per-farmer counter-bids |
| E9 | Ops monitor page (live sessions, job queue, breaker state) | Lets the jury see the state machine and fault recovery | Not in any plan | 0.75 pd | Free | — |
| E10 | Price fallback chain with spoken basis | Thin and current-day-only price feed | Plans assumed a live price always exists | 0.5 pd | Free | Flat 6 % rule |

Added: about 7.75 pd. Removed (IndicWhisper, Geo-DID, LGD join, AgriStack, escrow, SMS, counter-bids, ONDC sync, H3): well over 15 pd of work that could not have been finished or run for free. Net scope is smaller than any of the three original plans.

---

## 10. Free-path demo plan

### 10.1 What is live and what is simulated

| Part | In the demo | Honest label |
|---|---|---|
| State machine, Redis, Postgres, clustering, bidding, queue, dashboard, PWA | Live, on the laptop | Real |
| Mandi prices | Fetched from data.gov.in that morning, stored | Real data, cached |
| Audio | Bhashini TTS, pre-generated, 8 kHz | Real TTS, not generated live |
| Farmer phone, primary | Real button phone through the Exotel trial (whitelisted number) | Real GSM call, trial account |
| Farmer phones, the other 7 lots | Seeded, plus 2 simulator phones in browser tabs | Simulated, labelled on screen |
| Missed call costing ₹0 | Shown on the real phone | Real, as far as the trial shows; operator billing not independently audited |
| Masked helper call | Real on the Exotel trial if time allows, otherwise simulated banner | State which |
| FPO verification | Real PWA on a team member's phone, with a collection point seeded at the venue's coordinates | Real capture, staged location |
| Buyers | Two team laptops logged in as two buyers | Simulated buyers |
| Payment | Buttons only; no money moves | Simulated |
| SMS, escrow, ONDC, AgriStack | Not shown | Not built |

### 10.2 Set-up (the evening before, and 30 minutes before)

1. Laptop A: `docker compose up -d`, backend, built front end, `DEMO_MODE=1`. Laptop B: identical clone, switched off.
2. `seed_demo.py`: 1 FPO, 3 collection points (one at the venue), 40 farmers, one ragi cluster at 17 quintals (so the live lot tips it to `READY`), two approved buyers, yesterday's and today's prices.
3. `ngrok http 8000 --url <static-domain>`; set `PUBLIC_BASE_URL`; check `/health` through the tunnel from a phone on mobile data.
4. Exotel: confirm credit, whitelisted numbers, webhook URLs; place one test call.
5. Open tabs: `/sim` (two), `/buyer` on two laptops, `/ops` on the projector, `/agent` on a phone.
6. Phone hotspot ready as the second network. Backup video on the desktop.

### 10.3 Script (about 7 minutes)

| Min | Action | What the jury sees | Point made |
|---|---|---|---|
| 0:00 | Give a missed call from the button phone | Phone rings back in seconds; Kannada prompt on speaker; `/ops` shows the session | ₹0 for the farmer; no internet |
| 0:40 | Press 1 for ragi, `3#`, confirm | Readback of "3 quintals" | Keypad for numbers, voice for context |
| 1:20 | Hear the mandi price and floor; type `3200#` | Guardrail warning; press 1 to raise to 3,430 | Price transparency in the call |
| 2:00 | **Hang up before confirming.** Missed-call again | "Welcome back", resumes at the final confirmation | 2G drop recovery |
| 2:40 | Confirm | Dashboard: cluster goes from 17 to 20 quintals, turns `READY` | MOQ trap solved by pooling |
| 3:10 | On a simulator tab, switch on "inject key bounce", enter quantity 4 | `/ops` shows `BOUNCE` rows dropped; stored value is 4 | Keypad bounce handling |
| 3:40 | In a terminal: `valkey-cli FLUSHALL` during a simulator call, then press the next key | Call continues | Redis is disposable; Postgres checkpoint |
| 4:10 | Agent phone: take the verification photo | Cluster moves to `BIDDING`, photo appears for buyers | Trust layer |
| 4:40 | Two buyers bid; one double-clicks | One bid recorded; live outbid on the other screen | Idempotency, row locks |
| 5:10 | Admin closes the auction | Button phone rings with the offer; press 1, 1. Simulator phones accept and reject | Binding keypad consent |
| 6:00 | Round resolves | Deal card: accepted quantity out of the cluster total (for example 17 of 24 quintals), value, 1.5 % fee, FPO payee details | Unit economics on screen |
| 6:30 | One slide: what is real, what is simulated, what costs money in production | | Honesty |

### 10.4 Failure point → fallback

| Failure | Detect | Action (under 30 seconds) |
|---|---|---|
| Button phone does not ring back | 10 s without a ring | Say so, move to the `/sim` tab, continue the same script |
| Tunnel down | `/health` check on the ops page turns red | Switch to hotspot; if still down, simulator only |
| Audio silent on the phone | No prompt after answer | Simulator (plays the same files locally) |
| Dashboard not updating | No change after a listing | Refresh (REST snapshot); events replay by `seq` |
| Backend crash | Any | `uvicorn` restart takes 3 s; sessions and jobs are in Postgres |
| Laptop A dead | Any | Laptop B; then the video |

---

## 11. Unit economics

All of section 11 is a model. Each number is tagged; most cost inputs are [Assumed] because Exotel does not publish per-minute rates [Verified absence].

### 11.1 Inputs

| Input | Value | Tag and source |
|---|---|---|
| Lot size | 3 quintals | [Assumed], within the 150–400 kg range in the brief |
| Cluster | 8 lots, 24 quintals (2.4 t) | [Assumed] |
| Mandya ragi mandi modal | ₹3,565/qtl | [Verified] data.gov.in, 12 Nov 2026 |
| Fair farm-gate floor (AFPP) | ₹3,430/qtl | Computed in section 7.4; deductions [Assumed] |
| Deal price | ₹3,500/qtl | [Assumed] |
| Village trader price | ₹3,030/qtl (15 % below mandi) | [Assumed]; the brief's "20–35 % loss" is not verified |
| Karnataka market fee | 0.6 %, paid by buyer | [Verified] |
| Commission agent charge at the mandi | 5 %, paid by buyer | [Likely] (Bengaluru yard report) |
| Truck for 2.4 t, short haul | ₹4,000 | [Likely] (city shifting rates, upper bound) |
| Platform fee | 1.5 % of settled value, buyer pays | Project decision |
| FPO verification payout | ₹50 per cluster | Project decision |
| Outbound call rate | ₹0.60/min, range ₹0.40–1.20, 60 s billing pulse | [Assumed]; Plivo publishes ₹0.38/min for India [Verified] |

### 11.2 One cluster

| Line | Calculation | Amount |
|---|---|---|
| Gross value | 24 × 3,500 | ₹84,000 |
| **Platform fee (revenue)** | 1.5 % × 84,000 | **₹1,260** |
| Listing callbacks | 8 farmers × 1.3 calls × 2 min × ₹0.60 | ₹12.5 |
| Bid-offer calls | 8 × 1.3 attempts × 1 min × ₹0.60 | ₹6.2 |
| One failed round in four | 0.25 × 8 × 1.3 × 1 min × ₹0.60 | ₹1.6 |
| Helper bridge and proxy confirm | (4 min × 2 legs + 1 min) × ₹0.60 | ₹5.4 |
| Telephony total | about 43 minutes | **₹26** (₹17 at ₹0.40; ₹52 at ₹1.20) |
| FPO payout | | ₹50 |
| **Contribution per closed cluster** | 1,260 − 26 − 50 | **₹1,184** |

**The callback tension, answered.** The free callback costs about ₹1.56 per listing (2 min × ₹0.60 × 1.3). The fee earned on that 3-quintal lot is ₹157.50. The callback is about 1 % of revenue even at the top of the rate range (₹3.12, 2 %). Call cost is not what threatens the model; unsold clusters and fee collection are. If only half of all clusters close, telephony per closed cluster doubles to about ₹52 and contribution is still about ₹1,158.

### 11.3 Who gains

| Party | Without the platform | With the platform | Difference |
|---|---|---|---|
| Farmer, 3 qtl | 3 × 3,030 = ₹9,090 from a village trader [Assumed] | 3 × 3,500 = ₹10,500 | +₹1,410 (+15.5 %) |
| Buyer, per quintal | Mandi: 3,565 + 0.6 % (21) + 5 % (178) = ₹3,764, plus transport from the mandi | 3,500 + fee 52.5 + truck 4,000 ÷ 24 (167) = ₹3,719 | −₹45 before counting mandi-to-warehouse transport |

The buyer's saving is thin and depends on the truck being full. That is exactly why pooling to 2–5 tonnes matters: a 0.75 t pickup at a ₹1,500 minimum costs about ₹200 per quintal, a 4 t truck at ₹4,000 about ₹100 [Likely].

### 11.4 Fixed costs and break-even (production pilot, not the free path)

| Item | Cost | Tag |
|---|---|---|
| Exotel entry plan, 5 months, includes 5,000 credits | ₹9,999 | [Verified] |
| DLT registration | about ₹5,900 | [Likely] |
| Hosting | ₹0 on free tiers at pilot scale | [Assumed] |
| **Total** | **₹15,899** | |

Break-even: 15,899 ÷ 1,158 ≈ **14 closed clusters in 5 months**, about 3 a month.

### 11.5 Honest scale check

An average FPO has about 560 members (56.32 lakh members across 10,000 FPOs) [Likely]. If 30 % have no smartphone and each lists 3 quintals twice a year [Assumed]: 168 × 2 × 3 = 1,008 quintals, about 42 clusters, about ₹52,900 of fee a year per FPO. One modest salary (₹25,000 a month) therefore needs about 6 active FPOs. The model works only as a low-cost tool spread across many FPOs, not as a venture-scale marketplace on one district.

---

## 12. Build roadmap (14 days, 14–27 Nov 2026 [Assumed])

**Owners.** **P1 Telephony and engine** · **P2 Data and markets** (prices, clustering, bidding, queue) · **P3 Front end** (simulator, dashboard, PWA, ops) · **P4 Audio, QA, demo and accounts**. Capacity is 56 person-days; the plan uses about 44 and keeps 12 as buffer.

| Day | P1 | P2 | P3 | P4 | Milestone |
|---|---|---|---|---|---|
| 1 | Repo, Compose, config, Lua loader | Schema, seed SQL | Vite app shell, login, routes | Register Bhashini and data.gov.in keys; `prompts.yaml` in English | Contracts frozen: `Action`, event types, REST shapes |
| 2 | Engine core, simulator adapter | Price ingestion, floor, backfill | Simulator page (keypad, audio) | Translations, native review, `prewarm_audio.py` | |
| 3 | LISTING flow complete | `commit_listing`, outbox, WebSocket hub | `useEvents`, cluster list | Generate kn and hi audio; handset listening test | **M1:** simulator call creates a listing that appears on the dashboard |
| 4 | Resume, checkpoint, idempotency, debounce | `place_bid`, `close_auction` | Cluster detail, bid form, map | Crop calendar, farmer import, `seed_demo.py` | |
| 5 | BID_OFFER flow | Job worker, retries, `resolve_round` | Confirmation and deal views | Engine table tests, chaos scripts | |
| 6 | Integration with P2 | Integration with P1 | Agent PWA: verify | Failure-injection tests | |
| 7 | Fixes | Fixes | Fixes | Record backup video v1 | **M2:** full flow on the simulator, missed call to deal. **This is the cut-line anchor.** |
| 8 | Exotel adapter against a fake-Exotel test client | Payment handoff, pickup, ledger | PWA: pickups, helper queue | Marathi clips; ops data endpoints | |
| 9 | Triage: tickets, codes, PROXY_CONFIRM | Sweepers, strikes, no-bid handling | Ops monitor page | Locust load test | |
| 10 | Exotel trial spike and real-phone call (see note) | Support P1; fix load findings | Polish, empty and error states | Whitelist phones; prepaid-balance test | **M3:** a real button phone completes a listing |
| 11 | Hardening | Cloud mirror: Render, Neon, Upstash | Cloudflare Pages build | Pitch numbers, "real vs simulated" slide | |
| 12 | Stretch: Asterisk path, or bug-fixing | Bug-fixing | Bug-fixing | Dress rehearsal 1 on a hotspot | |
| 13 | Rehearsal 2 with injected failures | same | same | Backup video v2 | **Code freeze** |
| 14 | Buffer: fixes only | | | Printed fallback sheet, backup laptop clone | **M4:** demo-ready |

**Exotel trial timing.** The trial lasts 7 days [Verified]. Start it only when the finale date is confirmed and no more than 6 days away. If the finale is later than that, Day 10 moves to the week of the finale and the adapter is exercised until then with the fake-Exotel client (a 50-line script that sends the documented requests). Ask Exotel support for an extension early; extensions are case by case [Verified].

**Cut line: dropped first to last if time runs out.**
1. Asterisk and softphone path
2. Marathi (ship Kannada and Hindi)
3. Cloud mirror
4. Ops monitor page (use logs)
5. Real masked bridge call (keep queue and proxy entry, bridge simulated)
6. Map (list only)
7. Pickup weights and ledger (deal ends at `CONFIRMED` with payee details)
8. Triage module entirely
9. Real phone through Exotel (simulator only, stated openly)

**Never cut:** engine with resume and idempotency, price guardrail, clustering, bidding, accept/reject calls, basic verification, simulator.

**If only 7 days are available:** stop at M2 (Day 7). If a few more days appear, do the Day 10 work (real phone) and the Day 13 work (rehearsal with injected failures) before anything else.

---

## 13. Test plan

### 13.1 Unit
- Engine transition table: every state × {valid keys, invalid key, timeout}.
- `compute_afpp` and the fallback chain; outlier filter.
- `accept_digit`: gaps of 30, 100, 130 ms for same and different digits.
- Lua scripts against a real Valkey: CAS returns 1/0/−1; limits at boundary values; lock release with a wrong token.
- Phone normalisation (`098450…`, `+9198450…`, `9198450…`).
- Prompt coverage: every clip id used in `flows.py` exists on disk for every language.

### 13.2 Integration (pytest, real Postgres and Valkey in Docker)
- Simulator client script runs a complete listing; asserts rows in `listings`, `clusters`, `events`, `dtmf_events`, `consent_log`.
- Listing → `READY` → verification → two bids → close → responses → deal → payment → pickup → ledger.
- Proxy listing confirmed and rejected paths.
- Fake-Exotel client: missed call, `gather`/`digits` chain, status callback.
- API authorisation matrix: buyer, agent, admin, anonymous on every endpoint.
- Privacy check: no response to a buyer or agent token contains a 10-digit number.

### 13.3 Load (Locust, on the demo laptop)

| Scenario | Load | Pass |
|---|---|---|
| Concurrent calls | 50 simulated calls, each 12 events, 1 s think time | p95 `handle_event` under 150 ms; zero errors; 50 listings |
| Cluster join contention | 50 commits to one (pickup point, crop) in 2 s | 1 cluster; `total_qtl` equals the sum |
| Bid burst | 20 buyers × 5 bids each on one cluster in 5 s | Exactly one `LEADING`; prices strictly increasing in accept order |
| Fan-out | 30 WebSocket clients, 20 events/s | Every client reaches the same final `seq`; no gaps after reconnect |
| Queue | 200 jobs, concurrency 5, simulator auto-answer | All `DONE`; never more than 5 `IN_CALL` |

Redis budget check: count commands per call during the load test and confirm that it fits Upstash's 500,000 a month for the cloud mirror.

### 13.4 Failure injection

| Injection | Expected |
|---|---|
| `FLUSHALL` mid-call | Next event rehydrates from Postgres; call completes |
| Stop Valkey for 10 s | Events return 503; simulator retries; no duplicate listing after recovery |
| Kill the backend mid-call, restart | Session resumes; queued jobs run; stuck jobs swept |
| Drop the call at each state | Resume at that state within 30 min; fresh start after |
| Duplicate every webhook (proxy that replays) | One transition per event id |
| Key bounce on every digit | Stored values correct; `BOUNCE` rows logged |
| Price API returns 500 or empty | Fallback basis spoken; ingestion alarm in `/health` |
| TTS provider unreachable | Digit-by-digit fallback used for a bid offer |
| WebSocket cut for 30 s | Replay by `seq`; state equals REST |
| Postgres restart | Requests fail fast and recover; no partial deal |
| Clock set forward 3 h | Round resolves by deadline; no negative timers |

### 13.5 Acceptance checklist (all must be true at code freeze)
- [ ] A missed call from the simulator produces a callback and a confirmed listing in under 90 s.
- [ ] A dropped call resumes at the right state.
- [ ] A below-floor price triggers the warning, and both "raise" and "keep" are stored correctly.
- [ ] The eighth lot turns a cluster `READY`, and one verification task appears.
- [ ] Verification from the wrong place is refused.
- [ ] Two buyers cannot both lead; a retried bid is not duplicated.
- [ ] Farmers accept and reject by keypad; the deal closes only at or above the buyer's minimum quantity.
- [ ] Pickup cannot be recorded before payment is confirmed.
- [ ] Three failed calls create one helper ticket; a proxy listing needs the farmer's confirmation.
- [ ] No farmer phone number in any buyer or agent response.
- [ ] `FLUSHALL` during a call does not lose it.
- [ ] The whole demo script runs twice in a row without a restart.
- [ ] The real phone path has been run on the Exotel trial at least 5 times (or is declared simulated).
- [ ] The backup laptop runs the demo offline.

---

## 14. Jury Q&A prep

1. **Why keypad tones and not speech recognition?** Numbers are the part that must be right, and 8 kHz narrowband audio with field noise is where recognition is weakest. The best public figure we found is 26.8 % word error for IndicWhisper on Hindi phone-recorded speech; we found no numeral-specific benchmark, so we do not quote one. A keypress is a discrete signal, and we still read every number back.
2. **Is DTMF really "RFC 2833" from a 2G phone?** No. On the radio leg the handset sends a signalling message and the network generates the tone, which is why codec distortion on the uplink does not matter. RFC 2833/4733 appears only on SIP legs. With Exotel we receive digits over HTTP and never see RTP. Our earlier documents overstated this.
3. **How do you debounce keypad bounce?** Where we see per-digit timing (simulator, Asterisk) we drop the same digit repeated within 120 ms and any digit within 40 ms. On a cloud PBX that returns a finished string we cannot, so we rely on single-digit collection for menus, range checks and spoken readback with confirmation. The 120 ms figure is our estimate, not a measured one.
4. **What happens if Redis dies mid-call?** Sessions are checkpointed to Postgres on every transition and rehydrated on a miss. Locks and rate counters reset, which is safe because duplicates are prevented by Postgres unique constraints, not by the lock. We will flush Redis live.
5. **Why are your locks in Postgres and not Redis Lua?** A Redis lock without fencing can be held by two clients after a pause. Money-bearing transitions (cluster join, best bid, accept, deal) use row locks and unique constraints in the system of record. Lua is used where a lost lock is harmless: session compare-and-set, rate limits, one-call-per-farmer.
6. **How do you handle at-least-once webhooks?** Every event has an id; the first application caches its response, repeats get the same response. Commits are idempotent by constraint (`session_id`, `Idempotency-Key`, `(bid, listing)`).
7. **Is it really free for the farmer, and who pays?** The inbound call is never answered, so it should not be billed; we test this with a prepaid balance but cannot audit operators. The platform pays for the callback: about ₹1.56 per listing against ₹157 of fee on a 3-quintal lot, with assumed call rates because Exotel does not publish them.
8. **Where does the price come from and how fresh is it?** The government open-data mandi feed, which carries the current day only and can be thin (7 rows for Mandya on the day we tested). We store it daily, fall back to a weekly district then state median, say the basis and date aloud, and skip the guardrail when there is nothing usable.
9. **Why not use MSP as the floor?** Because the market is below it: ragi traded at ₹3,565 in Mandya against an MSP of ₹5,205. An MSP floor would price every listing out.
10. **Why a 5 km radius, and why not H3?** Five kilometres is our assumption for how far a smallholder will carry a few bags to a collection point. We anchor to FPO collection points and use true metre distances; hexagons add nothing at this scale and their edges do not match a radius.
11. **FPOs already aggregate. What is new?** The aggregation idea is not new, and we do not claim it is. What is new is a tool that lets an FPO include members without smartphones, gives each of them the price reference and a binding yes/no by keypad, and brings competing buyers to the pooled lot. We found advisory voice services and app-based marketplaces, but no keypad-first bidding service; our search was not exhaustive.
12. **What stops the buyer and the FPO from cutting you out?** Nothing technical. Farmer numbers are hidden, but the FPO and buyer meet at pickup. The fee has to stay below the value of pooling and buyer competition. This is our largest business risk.
13. **Where does "35–40 million farmers" come from?** It is our estimate, not a published figure: about 126 million small and marginal holdings, times roughly a fifth to a quarter of mobile users still on 2G, gives about 27–29 million, more if rural areas skew higher. We now say "roughly 30 million, estimated".
14. **Is this legal?** For a pilot through an FPO selling to licensed traders, with consenting members and no money through us, we believe so. For production there are three real hurdles: telecom registration for automated calls and SMS, state market-law licences (Karnataka reportedly now licenses e-commerce platforms for notified produce), and data-protection duties from May 2027. None is solved by code.
15. **What is simulated in this demo?** The other farmers' phones, the buyers, payment, and possibly the masked helper call. The engine, data, prices, audio, clustering, bidding and one real phone call are live. Production telephony is not free; our free path is a 7-day trial plus the simulator.

---

## 15. Sources

All accessed 12 November 2026 unless marked. "Snippet" means the page was seen only as a search result.

**Telephony**
- Exotel pricing (trial: 7 days, 500 credits; plans from ₹9,999): https://exotel.com/pricing/business-phone-system/
- Exotel trial account rules (10 whitelisted numbers, all APIs): https://developer.exotel.com/docs/getting-started/trial-account
- Exotel Gather applet (dynamic URL returns JSON; `gather_prompt`, `max_input_digits`, `finish_on_key`, `input_timeout`): https://docs.exotel.com/business-phone-system/gather-applet
- Exotel Passthru applet (parameters; two documents that disagree): https://support.exotel.com/support/solutions/articles/48283-working-with-passthru-applet and https://developer.exotel.com/docs/app-bazaar/passthru-applet-guide
- Exotel connect-to-flow API: https://developer.exotel.com/docs/voice-v1/api-reference/connect-to-flow
- Exotel missed-call feature (auto-hangup after 1–2 rings, webhook payload): https://developer.exotel.com/docs/call-support/call-features/missed-call
- Exotel two-number call API: https://developer.exotel.com/api/make-a-call-api
- Exotel audio format (snippet): https://support.exotel.com/support/solutions/articles/84548
- Twilio trial rules: https://www.twilio.com/docs/usage/trials · India voice pricing: https://www.twilio.com/en-us/voice/pricing/in · India numbers: https://www.twilio.com/en-us/guidelines/in/regulatory
- Plivo India voice pricing (₹0.38/min): https://www.plivo.com/voice/pricing/in/
- Telnyx trial: https://developers.telnyx.com/docs/account-setup/using-trial-account.md
- 3GPP TS 23.014, DTMF support (snippet): https://www.etsi.org/deliver/etsi_ts/123000_123099/123014/17.00.00_60/ts_123014v170000p.pdf
- 3GPP change request on DTMF timing (snippet): https://3gpp.org/FTP/tsg_cn/TSG_CN/TSGN_06/tdocs/PDF/NP-99452.pdf

**Speech**
- Bhashini onboarding: https://bhashini.gitbook.io/bhashini-apis/pre-requisites-and-onboarding.md
- Bhashini pipeline config call and response: https://bhashini.gitbook.io/bhashini-apis/pipeline-config-call.md · https://bhashini.gitbook.io/bhashini-apis/pipeline-config-call/response-payload.md
- Bhashini compute call and response: https://bhashini.gitbook.io/bhashini-apis/pipeline-compute-call/request-payload.md · https://bhashini.gitbook.io/bhashini-apis/pipeline-compute-call/response-payload.md
- Bhashini terms ("PoC only"): https://bhashini.gitbook.io/bhashini-apis/
- edge-tts: https://pypi.org/project/edge-tts/ · January 2026 breakage: https://github.com/rany2/edge-tts/issues/458
- Azure voice list: https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support?tabs=tts
- Indic Parler-TTS: https://huggingface.co/ai4bharat/indic-parler-tts
- AI4Bharat Indic-TTS: https://github.com/AI4Bharat/Indic-TTS
- IndicWhisper results (Vistaar): https://github.com/AI4Bharat/vistaar · IndicConformer: https://huggingface.co/ai4bharat/indic-conformer-600m-multilingual
- Sarvam pricing and TTS API: https://docs.sarvam.ai/api-reference-docs/pricing · https://docs.sarvam.ai/api-reference-docs/text-to-speech/convert
- indic-numtowords: https://pypi.org/project/indic-numtowords/
- FFmpeg licence: https://ffmpeg.org/legal.html

**Prices and agriculture**
- data.gov.in daily mandi price API (live-tested): https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070
- data.gov.in variety-wise historical resource (live-tested): https://api.data.gov.in/resource/35985678-0d79-46b4-9ed6-6f13308a1d24
- Agmarknet portal: https://agmarknet.gov.in
- Karnataka market fee: https://www.thehindu.com/news/national/karnataka/karnataka-cuts-apmc-user-cess/article33439432.ece · https://krama.karnataka.gov.in/HTML/department/marketfee.htm
- Bengaluru yard commission practice: https://citizenmatters.in/how-bengaluru-apmc-system-works-farm-laws-yeshwanthpur-yard-commission-agents-farmers-cartelisation/
- Maharashtra market fee: https://www.angelone.in/news/economy/maharashtra-waives-apmc-fees-to-boost-onion-procurement
- Kharif MSP 2026-27: https://www.newsonair.gov.in/cabinet-approves-msp-for-kharif-crops-for-2026-27-season/
- Agriculture Census 2015-16 (86 % small and marginal; snippet): https://www.business-standard.com/article/news-ians/operated-farm-area-declines-shows-agri-census-2015-16-118100101221_1.html
- RBI working paper on farmers' share (snippet): https://website.rbi.org.in/documents/87730/30842423/WPS+No.+8%2C+2024+-+Vegetables+Inflation+in+India.pdf
- 2G in India (snippet): https://telecomtalk.info/2g-is-still-important-to-india-heres-why/979150/
- Truck hire rates: https://shiftcompare.in/mini-truck-shifting-charges-per-km/
- CEDA Agmarknet archive: https://agmarknet.ceda.ashoka.edu.in/

**Hosting and tools**
- Supabase pricing and compute: https://supabase.com/pricing
- Neon pricing and extensions: https://neon.com/pricing · https://neon.com/docs/extensions/pg-extensions
- Upstash Redis pricing: https://upstash.com/pricing/redis
- Redis licences: https://redis.io/legal/licenses
- Render free tier: https://render.com/docs/free
- ngrok free limits: https://ngrok.com/docs/pricing-limits/free-plan-limits
- OpenStreetMap tile policy: https://operations.osmfoundation.org/policies/tiles

**Regulation and context**
- Seva First Innovation Challenge portal: https://sevafirst.mic.gov.in · deadline report: https://articles.findmycollege.com/news/seva-first-innovation-challenge-2026-registration-extended-apply-by-6-november/
- TRAI 2025 amendment summaries: https://www.fonearena.com/blog/446114/trai-tcccpr-2025-tougher-rules-spam-calls-sms.html · TRAI press release on the 1600 series: https://trai.gov.in/sites/default/files/2025-11/PR_No.135of2025.pdf
- DLT registration fee: https://www.infobip.com/docs/essentials/asia-registration/dlt-registration
- DPDP Rules 2025 timeline: https://www.azbpartners.com/bank/update-indias-digital-personal-data-protection-framework-comes-into-effect/ · https://www.scconline.com/blog/post/2025/12/26/digital-personal-data-protection-rules-2025-key-highlights/
- RBI Payment Aggregator Directions 2025 (analysis): https://indiacorplaw.in/2025/10/09/decoding-rbis-overhaul-of-the-payment-aggregator-directions/
- e-RUPI FAQ: https://npci.org.in/what-we-do/e-rupi/e-rupi-faqs
- Karnataka 2025 APMC amendment (report): https://www.medianama.com/2025/03/223-karnataka-regulates-e-commerce-in-agriculture-with-apmc-amendment/
- Maharashtra 2016 ordinance: https://prsindia.org/files/bills_acts/bills_states/maharashtra/2016/Ord20of2016MH.pdf
- eNAM FPO figures: https://static.pib.gov.in/WriteReadData/specificdocs/documents/2026/apr/doc2026413845801.pdf
- FPO counts and membership: https://www.theweek.in/wire-updates/business/2025/02/28/dcm43-biz-agri-fpo.html · https://www.indiancooperative.com/co-op-news-snippets/women-account-for-nearly-22-lakh-members-in-fpo-scheme/amp
- Kisan e-Mitra: https://apolitical.co/en/navigator/case-studies/kisan-e-mitra-indias-voice-enabled-ai-support-for-farmers
- Farmer ID count: https://pib.gov.in/PressReleasePage.aspx?PRID=2225978
- Call recording (vendor explainer): https://exotel.com/glossary/call-recording-compliance-in-india/

Not fetched from a primary source: the TRAI regulation text, the DPDP Rules text, the Karnataka gazette notification and 3GPP specification bodies (connection refused or snippets only). Claims resting on them are tagged [Likely].

---

## 16. Open risks and unknowns

| # | Unknown | Why it matters | How to close it |
|---|---|---|---|
| 1 | **Exotel applet wiring** (dynamic Gather, Passthru branching, looping, digits format) | The whole real-phone path depends on it and the two official documents disagree | One-hour spike on Day 10; fallback is the simulator |
| 2 | **Exotel trial window vs finale date** | 7 days only; the finale date is not final | Start the trial late; ask support for an extension; Twilio trial as a documented contingency (outbound only, no Indian missed-call number) |
| 3 | **State market law** (Karnataka e-commerce licence, Maharashtra direct-marketing licence) | A commercial launch may be unlawful without licences | Legal advice and a partner FPO before any real trade; not needed for the demo |
| 4 | **TRAI treatment of automated service calls** from a private non-BFSI sender | Determines numbering (1600 series) and registration for production | Ask the telephony provider's compliance team |
| 5 | **DPDP consent by keypress** | Untested whether audio notice plus a keypress is valid consent | Legal review before May 2027 |
| 6 | **Bhashini limits and language coverage** | Rate limits are undocumented; kn/mr/hi TTS availability is expected but must be confirmed from the config response | First real call on Day 1; Parler-TTS and edge-tts fallbacks |
| 7 | **Farm-gate deduction values and the 5 km radius** | Both are assumptions that drive the guardrail and clustering | One conversation with a real FPO |
| 8 | **Per-minute call rates** | Unit economics use ₹0.40–1.20/min, assumed | Quote from a provider |
| 9 | **Whether a missed call is ever billed** | The "₹0 for the farmer" claim | Prepaid-balance test on at least two operators |
| 10 | **Buyer demand and willingness to pay 1.5 %** | The buyer's saving in our worked example is about ₹45 a quintal | Interviews with 3 traders before the finale |
| 11 | **Disintermediation** | No technical fix | Accept and price accordingly |
| 12 | **The "20–35 % loss to middlemen" and "35–40 million" figures** | Unverified; a jury member may challenge them | Use "our estimate" wording and the RBI farmer's-share figures instead |
| 13 | **Prompt quality in Kannada, Hindi and Marathi** | Machine-drafted prompts may be wrong or unnatural | Native-speaker review on Day 2; no review, no launch in that language |
| 14 | **Entry status** | Submissions closed on 6 Nov 2026 and are institution-led | Confirm with the institution's coordinator today |
