# Annadata Dhwani: End-to-End Technical Architecture & Operational Specification

**Project:** Annadata Dhwani (अन्नदाता ध्वनि)  
**Team:** Debug4X  
**Challenge Context:** Seva First Innovation Challenge 2026 (*Theme: Samriddh Annadata, Samriddh Bharat*)  
**Target Evaluation Standard:** Production-grade distributed systems, telecom signaling, Indian vernacular voice AI, and rural unit economics.

---

## 1. Core Architectural Thesis & Problem Boundaries

### 1.1 The Ground Reality
* **Digital Exclusion:** 35% to 40% of India’s small and marginal farmers (~35–40 million households owning <2 hectares) rely exclusively on basic 2G feature phones ("button phones") with no mobile internet, no camera, and limited digital literacy. Existing digital B2B platforms require smartphone UIs, locking these cultivators out entirely.
* **The Minimum Order Quantity (MOQ) Trap:** Marginal farmers harvest fragmented micro-lots of **150 kg to 400 kg** (1.5–4 Quintals). Wholesale distributors require **2 to 5 Tons** (20–50 Quintals) to justify dispatching a truck, causing institutional buyers to ignore individual smallholders.
* **Information Asymmetry:** Unaware of live APMC Mandi rates, button-phone farmers are forced into farm-gate distress sales via local middlemen (*village touts*), losing **20% to 35% below fair market value**.

### 1.2 Why Pure Conversational Voice Bots Fail (First-Principles Constraint)
* **8 kHz GSM Narrowband Physics:** 2G cellular voice channels compress audio using the AMR-NB codec at an 8 kHz sample rate, stripping high-frequency acoustic formants. Over a noisy field connection, open-ended Speech-to-Text (STT) suffers a **~28% Word Error Rate (WER)** on numerical quantities and prices in Indic dialects.
* **Asymmetric Hybrid Design:** Annadata Dhwani strictly separates downlink and uplink modalities:
  1. **Downlink (System → Farmer):** Dynamic neural speech via **Bhashini ULCA TTS** communicates variable market prices and buyer bids in the farmer's native dialect.
  2. **Uplink (Farmer → System):** Deterministic **RFC-2833 DTMF keypad tones** (`0–9`, `*`, `#`) handle all commercial numbers, achieving **100% numeric capture accuracy** immune to background acoustic noise.

---

## 2. End-to-End System Architecture Diagram

```text
========================================================================================================
 1. TELEPHONY & 2G GSM EDGE PLANE (EXOTEL CLOUD PBX + SIP/PRI TRUNKS)
========================================================================================================
  [Farmer 2G Phone] ──(1. Missed Call: 0 Cost)──────────────┐
       ▲  │                                                 ▼
       │  └──(3. RFC-2833 Out-of-Band DTMF Tones)──▶ [Exotel Cloud PBX] ◀──(Masked SIP Bridge)──┐
       │                                              │     ▲                                   │
       └──────(2. Outbound Callback / 8kHz Audio)─────┘     │                                   │
       └──────(4. DLT Transactional SMS Receipts)───────────┘                                   │
                                                            │ HTTPS Webhooks (<40ms Indian DC)  │
============================================================▼===================================│=======
 2. ASYNCHRONOUS ORCHESTRATION & STATE PLANE (AWS MUMBAI / ap-south-1)                           │
================================================================================================│=======
  [FastAPI Async Event Engine] ◀──▶ [Redis In-Memory Cluster]                                   │
       │   ├── DTMF Debounce (250ms)   ├── Active Call State (30-min TTL drop-recovery)         │
       │   ├── Idempotency Keys        ├── Persistent Language Profile (Skip menu on Call #2+)  │
       │   └── Atomic Lua Locks        └── Agmarknet Daily District Floor Cache                 │
       │                                                                                        │
       ├─────────────────────────────┬──────────────────────────────┐                           │
       ▼                             ▼                              ▼                           │
================================================================================================│=======
 3. VERNACULAR VOICE AI PLANE   4. SPATIAL & MARKET DATA PLANE  5. HUMAN-IN-THE-LOOP & WEB PLANE│
================================================================================================│=======
 [Bhashini ULCA TTS]            [PostgreSQL 15 + PostGIS]      [Single Responsive React Web App]│
  └─▶ FFmpeg 8kHz / -16 LUFS     ├─ Geography(Point,4326)+GIST  ├─ Desktop: Distributor Portal  │
      Transcoder & Hash Cache    ├─ ST_DWithin(5km) / H3 Pool   │   └─ Live WebSocket Cluster   │
                                 ├─ Geo-DID + FPO CSV + LGD     │   └─ 2-Way Counter-Bid Loop   │
 [AI4Bharat IndicWhisper ASR]    └─ Agmarknet API Engine        └─ Mobile PWA: FPO Field Agent  │
  └─▶ Key '9' Single-Word           └─ Adjusted Farm-Gate           ├─ ₹50 Gate Photo/Moisture  │
      District Crop Lexicon            Parity Price (AFPP)          └─ Masked Triage Queue ─────┘
========================================================================================================
```

---

## 3. Cloud Telephony Selection: Why Exotel & Required Capabilities

### 3.1 Engineering Justification: Exotel vs. Twilio
We evaluated Twilio and Exotel and selected **Exotel** based on three strict network and regulatory constraints:
1. **Sub-40ms Indian Signaling Latency (Preventing Double-Press State Corruption):** Exotel is hosted natively in Indian data centers (Mumbai/Bengaluru). SIP-to-webhook round trips execute in **<40ms**, preventing rural users from double-pressing keys due to lag, which corrupts state transitions.
2. **Hardware-Level "Disconnect on Ring" (True ₹0.00 Farmer Cost):** Exotel connects directly to Indian PRI lines and local SIP trunks, executing a hardware-level termination before a `200 OK` answered state is ever initiated. It is structurally impossible for the farmer to be charged.
3. **Native TRAI & DLT Regulatory Compliance:** Exotel has built-in DLT scrubbing, avoiding the multi-week compliance blocks common with international gateways for programmatic SMS and automated calls in India.

### 3.2 Core Exotel Functions
1. **Zero-Billing Missed-Call Ingress:** Detect incoming calls on Geo-DID virtual numbers, terminate on Ring 1.
2. **Automated Outbound Callback:** Programmatically originate outbound voice calls to the farmer’s 2G handset within 2–3 seconds.
3. **Out-of-Band RFC-2833 DTMF Tone Extraction:** Capture keypad presses as RTP `telephone-event` signaling packets.
4. **`nXML` Dynamic Audio & Barge-In Termination:** Execute `<Play>` tags and immediately interrupt audio playback when a digit is pressed.
5. **Click-to-Call Masked SIP Bridging:** Bridge outbound legs (FPO Agent ↔ Exotel ↔ Farmer).
6. **DLT-Scrubbed Transactional SMS Dispatch:** Trigger regional-language SMS receipts.

---

## 4. Zero-"API Magic" Location & Identity Resolution

### 4.1 3-Layer Location & PIN Resolution Funnel
* **Layer 1 — Geo-DID Virtual Numbers (Zero Keypresses):** Provision dedicated Exotel virtual numbers per APMC Mandi / Taluk catchment area. Inside the call, a single keypress narrows the 5–10 km sub-cluster.
* **Layer 2 — FPO & Input-Shop CSV Pre-Seeding:** Ingest member ledgers (Name, Mobile, Village) from partner FPOs and seed retailers, running a one-time fuzzy join against the open **Local Government Directory (LGD)** village master dataset to bind mobile numbers to exact Latitude, Longitude, and PIN code.
* **Layer 3 — Telecom Circle Prefix + Spoken Village Name:** For walk-in callers, use the mobile number's HLR series prefix to load the state's LGD village lexicon, record a 3-second voice response, and fuzzy-match via IndicWhisper.

### 4.2 Progressive Trust & Identity Model
* **Primary Key:** The 10-digit **Caller ID** is the farmer's primary account UUID (`AD-{STATE}-{PHONE}`).
* **3-Tier Verification Progression:**
  1. *Tier 1 (Unverified Intent):* Listing enters the cluster as *"Pending FPO Verification"*.
  2. *Tier 2 (Whitelisted Member):* Automatic match against FPO/retailer CSVs upgrades status to *"Verified FPO Member"*.
  3. *Tier 3 (Physical Gate Audit & Optional AgriStack Link):* FPO agent verifies grain at the village gate and optionally links the **AgriStack Farmer ID** via UFSI consent flow (farmer reads aloud a 6-digit SMS OTP).

---

## 5. Vernacular AI, Keypad Physics & Pricing Mathematics

### 5.1 AI Seasonal Crop Predictor & Constrained Key `9` Voice Fallback
* **Deterministic `[District] × [Month]` Matrix:** Built from Ministry of Agriculture (UPAg) historical harvest statistics. The backend queries Redis to vocalize only the **Top 3 local harvest crops** covering >85% of callers in one keypress.
* **Key `9` Constrained Voice ASR:** For niche crops, pressing `9` opens a 3.5-second buffer sent to **AI4Bharat IndicWhisper**, constrained strictly to that district's ~40-crop lexicon (>96% accuracy).

### 5.2 Telephony Audio Conditioning & Keypad Debounce
* **Audio Transcoding:** Bhashini ULCA TTS is transcoded via FFmpeg to **8 kHz mono 16-bit WAV / G.711 $\mu$-law**, normalized to **-16 LUFS** with a **300 Hz high-pass filter** for tiny feature-phone speakers.
* **Hardware Debounce:** FastAPI enforces a **250ms inter-digit debounce window** and mandatory voice readback confirmation (`Press 1 to confirm, * to re-enter`).

### 5.3 Adjusted Farm-Gate Parity Price (AFPP) Guardrail
Raw Mandi prices are destination prices. Our guardrail computes the **Adjusted Farm-Gate Parity Price (AFPP)**:

$$\text{AFPP} = P_{\text{Mandi Modal}} - C_{\text{Bulk Pickup Logistics}} - C_{\text{Mandi Cess \& Commission}}$$

If a farmer enters an exploitative asking price, Bhashini TTS immediately warns them mid-call and allows them to press `1` to auto-raise their quote to the AFPP Floor.

---

## 6. Geospatial Clustering & Responsive Web Application

### 6.1 Unified Responsive Web App
A single React/Tailwind web app handles two major workflows without requiring native app store installs:
* **Desktop View:** Wholesale Buyers inspect multi-ton clusters, maps, and escrow ledgers.
* **Mobile PWA View:** FPO Field Agents access a lightweight web link to capture geo-tagged photos and moisture readings.

### 6.2 PostGIS Clustering & Race-Condition Locks
* **Spatial Indexing:** `ST_DWithin(location, target, 5000)` aggregates micro-lots into **2–5 Ton Cluster Lots** in <10ms.
* **Atomic Cluster Locking:** An atomic **Redis Lua lock** prevents two buyers from simultaneously locking the same cluster.
* **Over-Subscription Buffer:** Clusters over-subscribe by 15–20% (~3.5 tons) to prevent falling below truck MOQ if one farmer rejects a counter-bid.
* **2-Way Counter-Bid Loop:** Buyer bids trigger an outbound Exotel call to each farmer (`1: Accept`, `2: Reject`, `3: Enter Counter-Price + #`), syncing live via WebSockets.

---

## 7. Human-in-the-Loop: FPO Audit & The Masked Triage Bridge

### 7.1 Workflow A: Physical Quality Verification
When a cluster reaches ≥2.0 Tons, the assigned FPO coordinator visits the collection point, checks grain moisture, captures an **HTML5 Geolocation + Timestamped Camera Photo** via the PWA, and earns a **₹50 micro-commission** upon settlement.

### 7.2 Workflow B: "No Farmer Left Behind" (Masked Triage Bridge)
To prevent agents from wasting fuel on accidental calls:
1. **Automated Triage Flagging:** If a Caller ID disconnects 3 consecutive times, Redis places them in the **"Assistance Triage Queue"**.
2. **Click-to-Call Masked SIP Bridge:** The FPO agent clicks "Verify Farmer" on the PWA. Exotel dials the agent and bridges them to the farmer. Both screens show only `1800-ANNADATA`, preventing platform disintermediation.
3. **Reverse Verbal OTP ("Secret Code 5-5"):** The agent schedules a visit and states a system-generated 2-digit passcode verbally over the phone to establish trust with zero literacy required.
4. **Proxy Entry + Mandatory Farmer Voice Lock:** At the farm, the agent enters the crop details into the PWA. Exotel automatically calls the farmer to approve the entry (`Press 1`), preventing agent price tampering.

---

## 8. Financial Settlement, Unit Economics & Scaling Roadmap

### 8.1 RBI-Compliant Escrow Settlement
Wholesale buyers deposit funds into an **FPO-Linked Nodal Escrow Account**. Funds are released directly to farmers' bank accounts via **IMPS/NEFT** (or NPCI **e-RUPI SMS vouchers**) only after the FPO agent submits the geo-tagged loading sign-off.

### 8.2 Unit Economics (INR)
* **One-Time 3-Month Pilot Setup: ₹18,500**
* **Variable Cost per Listing:** ~₹1.40–₹1.75 + ₹50 FPO verification fee per bundled cluster.
* **Revenue Model:** **₹0 cost to farmers.** A **1.5% facilitation fee** is charged to the Wholesale Buyer on settled cluster value.

### 8.3 3-Phase Rollout
1. **Phase 1 (Months 1–3):** Pilot with 2 FPOs and 5 Gram Panchayats in Mandya/Kolar (Karnataka).
2. **Phase 2 (Months 4–9):** State-wide rollout via Common Service Centres (CSCs) and state FRUITS/AgriStack registries.
3. **Phase 3 (Months 10–18):** National deployment as a Beckn-compliant Voice & Keypad Seller Node plugged directly into **ONDC Agri** and **eNAM**.

---

## 9. Terms, Conditions & Operational Guardrails Matrix

| Subsystem / Role | Mandatory Terms, Conditions & Engineering Guardrails | Enforcement Mechanism |
| :--- | :--- | :--- |
| **Farmer (2G Caller)** | • **Zero Cost:** Must never incur call or SMS charges.<br>• **Binding Consent:** No listing or bid acceptance is valid without an explicit DTMF `1` confirmation.<br>• **Anti-Spam Rate Limit:** Maximum 5 missed-call triggers per Caller ID per 24 hours. | Exotel PRI `486/603` Disconnect-on-Ring; Redis rate-limiter; mandatory voice readback before final `#`. |
| **Exotel Telephony & AI Pipeline** | • **Latency SLA:** Webhook-to-prompt response must execute in **<500ms**.<br>• **Numeric Isolation:** ASR (speech recognition) is strictly forbidden for prices and weights; only RFC-2833 DTMF tones are accepted.<br>• **Drop Recovery:** Interrupted sessions must persist for 30 minutes. | Indian data center hosting (`ap-south-1`); 250ms DTMF debounce; Redis TTL session state machine. |
| **Pricing & Guardrail Engine** | • **No Raw Mandi Quotes:** Guardrails must always deduct standardized transport/cess (AFPP).<br>• **Override Right:** Farmers can override an AFPP warning only after hearing the explicit warning and pressing `2`. | Automated daily 7:00 AM Agmarknet ingestion; district-specific logistics deduction table. |
| **FPO Field Agent** | • **No Direct Number Exposure:** Agents are prohibited from contacting farmers outside the Exotel Masked SIP Bridge.<br>• **Anti-Spoofing Audit:** Photos captured live via PWA camera with GPS coordinates inside the 5 km cluster polygon.<br>• **Commission Condition:** ₹50 payout triggers *only* upon verified cluster loading. | Exotel number masking; PWA `capture="environment"` restriction + PostGIS geofence validation. |
| **Wholesale Buyer (Distributor)** | • **Escrow Pre-Funding:** Buyers cannot dispatch trucks or lock a cluster without depositing 100% of bid value.<br>• **MOQ Commitment:** Buyer cancellation forfeits a 2% logistics penalty distributed to the affected farmers. | Automated escrow webhook lock; binding digital purchase order on WebSocket bid acceptance. |
| **Financial & Data Governance** | • **Custodial Compliance:** Platform never holds farmer/buyer principal in corporate operating accounts.<br>• **Data Privacy:** Farmer phone numbers and AgriStack consent tokens are encrypted at rest (AES-256) and masked in all buyer-facing APIs. | Partner Bank / FPO Nodal Escrow split-settlement; role-based access control (RBAC) in FastAPI. |