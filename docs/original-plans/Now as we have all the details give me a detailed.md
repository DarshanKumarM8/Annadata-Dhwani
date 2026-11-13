# **Annadata Dhwani: Master Product, Technical, Security, and Implementation Document**

**Annadata Dhwani** is a zero-internet, AI-assisted Dual-Tone Multi-Frequency (DTMF) keypad and voice brokerage platform designed to connect small and marginal feature-phone farmers directly with wholesale buyers. This master document consolidates the domain context, Product Requirements Document (PRD), Technical Requirements Document (TRD), zero-cost architectural strategy, vulnerability remediation matrix, and phase-wise build plan from initial setup to a deployable product.

## **1\. Domain Context & Problem Analysis**

India’s digital agricultural ecosystem—spanning platforms such as eNAM, ONDC, DeHaat, and Ninjacart—has expanded digital market linkage for smartphone-owning cultivators. However, approximately **35% to 40% of Indian small and marginal farmers** (\~35 to 40 million households owning less than 2 hectares of land) rely on basic 2G feature phones ("button phones") and lack touchscreen or internet literacy.

### **1.1 The Four Structural Barriers Locking Out Button-Phone Farmers**

* **The Smartphone & Data Barrier:** Modern B2B agricultural marketplaces require mobile internet, visual UI navigation, text entry, and smartphone cameras to upload crop photos, locking out ₹1,000 keypad-phone users.  
* **The Village Tout (*Kaccha Arhatiya*) & Information Asymmetry:** Blind to real-time APMC Mandi floor prices at the farm gate, farmers depend on unregistered local middlemen who use rigged scales and arbitrary moisture deductions to buy crops at **20% to 35% below fair market value**.  
* **The Minimum Order Quantity (MOQ) Trap:** Marginal farmers harvest **150 kg to 400 kg** (1.5 to 4 Quintals) per cycle, whereas wholesale distributors require **2 to 5 Tons** (20 to 50 Quintals) to justify dispatching a transport truck.  
* **Failure of Pure Voice Bots on 2G Lines:** Traditional helplines (such as Kisan Call Centres) are informational rather than transactional, while open-ended Speech-to-Text (STT) bots suffer from \~28% numeric transcription error rates over noisy 8kHz cellular lines.

### **1.2 The Core Innovation: Hybrid Deterministic DTMF \+ Vernacular AI \+ Geospatial Pooling**

Annadata Dhwani bridges these gaps by splitting communication roles according to channel reliability:

* **AI Speaks Dynamic Context:** Regional Text-to-Speech (TTS) reads out predicted local crops, live government Mandi floor rates, and custom buyer counter-offers in Kannada, Marathi, Hindi, and English.  
* **Keypad Commits Financial Data:** All legally binding commercial figures—crop choice, harvest weight in Quintals, asking price in INR, and bid confirmations—are captured via **DTMF acoustic keypad tones**, avoiding background noise transcription errors.  
* **PostGIS Pools Micro-Harvests:** A spatial database engine automatically bundles fragmented 150–400 kg listings within a **5 km Panchayat radius** into a single **2-to-5 Ton Cluster Lot**, paired with a ₹50 micro-commission quality check by a local FPO agent.

## **2\. Product Requirements Document (PRD)**

### **2.1 Target User Personas**

* **Primary Persona — The 2G Feature-Phone Farmer:** Smallholder or elderly cultivator (e.g., Ramesh in Mysuru, Karnataka, or Tukaram in Nashik, Maharashtra) using a basic keypad phone without mobile data, harvesting 2 to 15 Quintals of seasonal produce.  
* **Secondary Persona — The Wholesale Distributor / Institutional Buyer:** Regional food processor, APMC trader, or retail aggregator seeking pre-verified 2-to-5 Ton village cluster lots to save **12% to 18% in multi-layer middleman commissions**.  
* **Tertiary Persona — The Local FPO Quality Verifier:** Smartphone-owning rural youth or Farmer Producer Organization (FPO) coordinator who earns **₹50 to ₹100 per pooled cluster lot** by verifying crop moisture and uploading a geo-tagged photo.

### **2.2 Functional Requirements (Core Product Features)**

| ID | Feature Name | Priority | Target User | Core Deliverable |
| :---- | :---- | :---- | :---- | :---- |
| **FR-01** | Zero-Cost Missed Call Ingress | P0 | Farmer | Rejects inbound ring in 1 second and triggers automated outbound callback |
| **FR-02** | Caller-ID PIN & Language Memory | P0 | Farmer | Maps phone number to PIN code and remembers chosen language in Redis |
| **FR-03** | AI Top-3 Seasonal Crop Predictor | P0 | Farmer | Dynamically vocalizes top 3 district crops for the current harvest month |
| **FR-04** | Key 9 Constrained Voice ASR | P1 | Farmer | Captures a single spoken crop noun via AI4Bharat ASR when pressing 9 |
| **FR-05** | Multi-Digit DTMF Qty & Price Entry | P0 | Farmer | Captures Quintals and INR per Quintal terminated by \# key |
| **FR-06** | Live Agmarknet Price Guardrail | P0 | Farmer | Warns caller mid-call if ask price is below district Mandi floor |
| **FR-07** | 5 km PostGIS Cluster Aggregation | P0 | System / Buyer | Groups same-crop listings within 5,000 meters into a 2–5 Ton Cluster Lot |
| **FR-08** | FPO Micro-Commission Verification | P1 | FPO Verifier | Triggers ₹50 verification task to upload moisture % and grade photo |
| **FR-09** | 2-Way Outbound Bid Negotiation | P0 | Buyer & Farmer | Calls farmer with buyer bid (1 Accept, 2 Reject, 3 Counter-Bid) |
| **FR-10** | SMS Escrow & ONDC/eNAM Sync | P1 | All Users | Sends regional SMS receipt and formats Beckn-compliant JSON catalog |

Detailed operational rules for each functional requirement follow below:

* **FR-01 & FR-02 (Ingress & Memory):** First-time callers hear a localized 3-language prompt based on their PIN code (e.g., 570001 offers Kannada, Hindi, English; 422001 offers Marathi, Hindi, English). Repeat callers skip Step 1 automatically.  
* **FR-03 & FR-04 (Crop Selection):** Cuts call completion time from \~140 seconds to **under 45 seconds** by presenting 3 seasonal crops (1, 2, 3\) while reserving 9 for single-word speech recognition (\~95%+ accuracy on isolated nouns).  
* **FR-06 (Mandi Floor Protection):** If a farmer enters ₹3,200/Qtl when the district Mandi floor is ₹3,800/Qtl, the call pauses and lets the farmer press 1 to automatically raise their asking price to ₹3,800/Qtl or 2 to keep ₹3,200/Qtl.  
* **FR-09 (Asynchronous Bidding Loop):** When a distributor submits an offer on the web dashboard, the PBX dials the farmer's keypad phone so they can lock the trade (1), decline (2), or key in a counter-price followed by \# (3).

### **2.3 Non-Functional Requirements (NFRs)**

* **Voice Webhook Turnaround Latency:** State transitions between a farmer pressing \# and hearing the next audio prompt should remain under **400 milliseconds** using pre-cached neural audio and in-memory Redis sessions.  
* **Call-Drop Resiliency:** If a 2G call drops mid-flow, redialing within **30 minutes** resumes the state machine at the exact unfinished step rather than restarting from Step 1\.  
* **Zero-Cost Farmer Accessibility:** Farmers incur ₹0 in cellular voice or data charges across all listing and negotiation flows.

## **3\. Technical Requirements Document (TRD) & Free-Tier Stack**

### **3.1 Zero-Cost Engineering Stack & Resource Quotas**

The table below outlines the zero-cost stack used to build, host, and demonstrate the system without upfront infrastructure spend; actual cloud quotas can vary by account tier and regional availability.

| Layer | Technology Choice | Free-Tier Quota | Role in System |
| :---- | :---- | :---- | :---- |
| **Telephony Gateway** | Twilio Trial \+ WebAudio Simulator | \~\$15.50 USD credit | Real cellular callbacks to verified phones \+ offline browser keypad |
| **Backend API** | Python FastAPI \+ Uvicorn | Open-source (Render / Local) | Async webhook state machine, guardrail logic, and REST/SSE endpoints |
| **Voice TTS & ASR** | edge-tts \+ Bhashini / IndicWhisper | Free open-source / ULCA | Generates neural Kannada, Marathi, Hindi, and English MP3 prompts |
| **Spatial Database** | Supabase PostgreSQL \+ PostGIS | 500 MB DB, 5 GB egress | Stores farmers, listings, and runs ST\_DWithin 5 km spatial pooling |
| **Session Cache** | Upstash Serverless Redis | 250 MB RAM, 500K commands/mo | Caches active call state, call-drop recovery, and language preferences |

### **3.2 System Data Flow & State Machine Architecture**

\[Farmer 2G Phone\] \--(1. Missed Call)--\> \[Twilio Cloud PBX / Dual-Mode Gateway\]  
                                                \|  
                                       (2. HTTP POST Webhook)  
                                                v  
\[Upstash Redis Cache\] \<---\> \[FastAPI Call State Machine & Guardrail Engine\]  
  (Session \+ Lang)                   \|                  \|                \|  
                                     \|                  \|                \+--(3. Generate MP3)--\> \[edge-tts / Bhashini Cache\]  
                            (4. Check Floor)   (5. Spatial Pool)  
                                     v                  v  
                          \[Agmarknet API Cache\]  \[Supabase PostGIS DB\]  
                                                        \|  
                                             (6. Live SSE / WebSocket)  
                                                        v  
                                        \[React Wholesale & FPO Portal\]

### **3.3 PostgreSQL \+ PostGIS Database Schema (Supabase SQL)**

Run this schema inside the Supabase SQL Editor to enable geospatial clustering and relational tracking:

SQL  
\-- Enable PostGIS extension for 5km radius clustering  
CREATE EXTENSION IF NOT EXISTS postgis;

\-- 1\. Verified Farmers Table (Synced with AgriStack / FRUITS mock registry)  
CREATE TABLE farmers (  
    farmer\_id VARCHAR(32) PRIMARY KEY,  
    phone\_number VARCHAR(20) UNIQUE NOT NULL,  
    full\_name VARCHAR(100) NOT NULL,  
    district VARCHAR(60) NOT NULL,  
    pincode VARCHAR(10) NOT NULL,  
    preferred\_lang VARCHAR(5) DEFAULT NULL,  
    location GEOGRAPHY(POINT, 4326) NOT NULL,  
    created\_at TIMESTAMPTZ DEFAULT NOW()  
);

\-- 2\. Pooled Cluster Lots Table (2 to 5 Ton Virtual Mandi Lots)  
CREATE TABLE cluster\_lots (  
    cluster\_id UUID DEFAULT gen\_random\_uuid() PRIMARY KEY,  
    crop\_name VARCHAR(80) NOT NULL,  
    district VARCHAR(60) NOT NULL,  
    pincode VARCHAR(10) NOT NULL,  
    center\_location GEOGRAPHY(POINT, 4326) NOT NULL,  
    total\_qty\_qtl NUMERIC(8,2) DEFAULT 0,  
    weighted\_avg\_price NUMERIC(10,2) DEFAULT 0,  
    fpo\_verified BOOLEAN DEFAULT FALSE,  
    moisture\_pct NUMERIC(4,1) DEFAULT NULL,  
    quality\_grade VARCHAR(20) DEFAULT 'PENDING',  
    status VARCHAR(30) DEFAULT 'POOLING', \-- POOLING, READY\_FOR\_BIDS, UNDER\_NEGOTIATION, SETTLED  
    created\_at TIMESTAMPTZ DEFAULT NOW()  
);

\-- 3\. Individual Farmer Keypad Listings  
CREATE TABLE crop\_listings (  
    listing\_id UUID DEFAULT gen\_random\_uuid() PRIMARY KEY,  
    farmer\_id VARCHAR(32) REFERENCES farmers(farmer\_id),  
    cluster\_id UUID REFERENCES cluster\_lots(cluster\_id),  
    crop\_name VARCHAR(80) NOT NULL,  
    qty\_qtl NUMERIC(8,2) NOT NULL,  
    initial\_ask\_price NUMERIC(10,2) NOT NULL,  
    final\_ask\_price NUMERIC(10,2) NOT NULL,  
    mandi\_floor\_at\_listing NUMERIC(10,2) NOT NULL,  
    guardrail\_triggered BOOLEAN DEFAULT FALSE,  
    status VARCHAR(30) DEFAULT 'ACTIVE', \-- ACTIVE, BID\_RECEIVED, COUNTERED, SOLD  
    location GEOGRAPHY(POINT, 4326) NOT NULL,  
    created\_at TIMESTAMPTZ DEFAULT NOW()  
);

\-- Spatial Index for sub-10ms 5km radius lookups  
CREATE INDEX idx\_cluster\_lots\_location ON cluster\_lots USING GIST (center\_location);  
CREATE INDEX idx\_crop\_listings\_location ON crop\_listings USING GIST (location);

### **3.4 Automated 5 km PostGIS Clustering Query (ST\_DWithin)**

Whenever a farmer completes Step 4 (Price Confirmation), the backend executes this spatial query to join an existing active cluster within **5,000 meters** (5 km) or initialize a new cluster lot:

SQL  
\-- Find an active cluster lot for the same crop within a 5,000-meter (5 km) radius  
SELECT cluster\_id, total\_qty\_qtl, weighted\_avg\_price  
FROM cluster\_lots  
WHERE crop\_name \= :crop\_name  
  AND status IN ('POOLING', 'READY\_FOR\_BIDS')  
  AND ST\_DWithin(  
        center\_location,  
        ST\_SetSRID(ST\_MakePoint(:longitude, :latitude), 4326)::geography,  
        5000  
      )  
ORDER BY created\_at DESC  
LIMIT 1;

### **3.5 Redis Call-State & Drop-Recovery Schema**

Each active call stores a lightweight hash in Redis keyed by the normalized E.164 phone number (call\_state:+919845012345) with a **1,800-second (30-minute) TTL**:

JSON  
{  
  "call\_sid": "CA890123456789abcdef",  
  "phone": "+919845012345",  
  "farmer\_id": "KA-MYS-408",  
  "region": "KA",  
  "pincode": "570001",  
  "lang": "KN",  
  "current\_step": "WAIT\_PRICE\_DTMF",  
  "selected\_crop": "Ragi (Finger Millet)",  
  "mandi\_floor": 3800,  
  "qty\_qtl": 15,  
  "entered\_price": null,  
  "updated\_at": 1794501960  
}

## **4\. Architectural Approaches & Why We Use a Dual-Mode Free Engine**

Building a live telecom project for ₹0 requires navigating trial account rules and Indian telecom regulations (TRAI DLT). Below is a comparison of the three viable implementation approaches:

| Criterion | Approach A: Pure Cloud PBX Trial | Approach B: Pure Browser Simulator | Approach C: Dual-Mode Hybrid (Selected) |
| :---- | :---- | :---- | :---- |
| **Real 2G Phone Ringing** | Yes (Verified numbers) | No (Screen only) | Yes (Verified phones) \+ On-screen handset |
| **Cost to Build & Demo** | ₹0 (Uses \~\$15.50 trial credit) | ₹0 | ₹0 |
| **Cellular Drop Fallback** | Fails if auditorium has weak signal | Works offline | Instant switch between Real GSM and Simulator |
| **Judge Experience** | Audio on speakerphone | Visual UI only | Physical phone rings \+ Live UI dashboard sync |

### **Why Approach C (Dual-Mode Hybrid Architecture) is the Recommended Strategy**

* **Physical Cellular Impact:** Using a **Twilio Free Trial** (or Exotel trial), you verify 2 to 3 personal SIM cards and place one inside a real ₹1,000 Nokia keypad phone. During the pitch, the physical phone rings on speakerphone and accepts real button presses.  
* **Zero-Dependency Failover:** Conference halls often have poor cellular reception or strict firewall rules that block ngrok webhooks. Approach C connects **both** the physical Twilio webhook pipeline and the browser-based Nokia keypad to the exact same FastAPI state machine, allowing you to switch modes with one click if cellular reception drops.

## **5\. Comprehensive Vulnerability Analysis & Engineering Fixes**

To transition Annadata Dhwani from a hackathon prototype to a hardened rural commerce system, we must address **9 critical technical and operational vulnerabilities**.

### **5.1 Vulnerability & Remediation Matrix**

| \# | Vulnerability Category | Threat Vector | Severity | Engineered Fix |
| :---- | :---- | :---- | :---- | :---- |
| **V-01** | Unauthenticated Webhook Spoofing | Attacker sends fake HTTP POSTs to /voice/\* to inject bogus crop listings | High | Validate X-Twilio-Signature HMAC-SHA1 header on every webhook request |
| **V-02** | Missed-Call Flooding (DoS) | Botnet or repeated calls drain outbound telephony credits | High | Redis sliding-window rate limiter (max 3 callbacks per 10 mins per phone) |
| **V-03** | Ghost Listings & Cluster Poisoning | Malicious user keys in 9,999 Quintals to corrupt cluster volume | High | Landholding-based sanity cap (max Qty checked against AgriStack acreage) |
| **V-04** | Mid-Call Drop State Loss | Rural 2G signal drops after Step 3, forcing farmer to restart | Medium | Redis checkpointing by Caller ID (current\_step) with 30-min auto-resume |
| **V-05** | FPO Quality Verifier Collusion | Agent uploads a fake stock photo without visiting the village lot | Medium | EXIF GPS \+ timestamp check enforcing upload within 500m of village centroid |
| **V-06** | TTS Synthesis Latency Timeout | Generating neural audio live takes \~2.5s, causing PBX webhook timeout | High | Pre-warm MD5-hashed static prompts at startup \+ local audio\_cache serving |
| **V-07** | Key 9 ASR Noise Hallucination | Tractor noise causes speech-to-text to misidentify niche crop | Medium | Confidence threshold (0.80) \+ phonetic fuzzy match \+ Press 1 to confirm loop |
| **V-08** | Free-Tier Cloud Pausing | Supabase pauses free DB after 7 days of inactivity before demo day | Medium | Automated GitHub Actions cron job pinging /api/health every 48 hours |
| **V-09** | Twilio Trial Prompt Confusion | Trial account plays English message before executing TwiML | Low | Pre-briefed Press 1 on speakerphone flow \+ synchronous UI status banner |

### **5.2 Deep-Dive Code & Architecture Fixes for Core Vulnerabilities**

#### **Fix for V-01: Cryptographic Webhook Signature Verification**

Without signature verification, anyone who discovers your public webhook URL can send fake POST requests with arbitrary Digits and From parameters. Add this FastAPI dependency to verify cryptographic signatures on real telephony webhooks:

Python  
from fastapi import Request, HTTPException  
from twilio.request\_validator import RequestValidator

validator \= RequestValidator(TWILIO\_AUTH\_TOKEN)

async def verify\_twilio\_signature(request: Request):  
    \# Allow local simulator requests from localhost during testing  
    if request.client.host in ("127.0.0.1", "localhost"):  
        return True  
    signature \= request.headers.get("X-Twilio-Signature", "")  
    url \= str(request.url)  
    form\_data \= await request.form()  
    params \= {k: v for k, v in form\_data.items()}  
    if not validator.validate(url, params, signature):  
        raise HTTPException(status\_code=403, detail="Invalid webhook signature")  
    return True

#### **Fix for V-02: Redis Rate Limiting Against Missed-Call Credit Drain**

Because the platform pays for the outbound callback, a single phone number redialing 100 times could exhaust your telephony balance. Implement a Redis token bucket per Caller ID:

Python  
def allow\_outbound\_callback(redis\_client, phone: str) \-\> bool:  
    """Limits each phone number to at most 3 outbound callbacks per 10-minute window."""  
    key \= f"ratelimit:callback:{phone}"  
    current\_count \= redis\_client.incr(key)  
    if current\_count \== 1:  
        redis\_client.expire(key, 600)  \# 600 seconds \= 10 minutes  
    return current\_count \<= 3

#### **Fix for V-03: Landholding Sanity Bounds Against Ghost Listings**

If a marginal farmer registered with 1.5 hectares of land accidentally or maliciously keys in 5000\# Quintals (500 Tons), it distorts the cluster lot. Enforce a deterministic upper bound based on their AgriStack landholding profile plus a mandatory keypad confirmation step:

* **Quantity Ceiling Check:** Maximum allowable single listing is capped at registered\_hectares \* max\_yield\_per\_hectare \* 1.2 (typically **50 Quintals** for marginal profiles). Inputs above 50 Quintals trigger a voice prompt asking the farmer to re-enter a valid quantity.  
* **Price Ceiling Check:** Asking prices exceeding **200% of the live Agmarknet Mandi modal rate** require explicit double-confirmation (Press 1 to confirm) to prevent fat-finger typos (such as typing 38000\# instead of 3800\#).

#### **Fix for V-04: Redis Mid-Call Drop Auto-Resume Engine**

When /voice/start-callback is invoked, the server checks if an incomplete session (current\_step in \["WAIT\_CROP", "WAIT\_QTY", "WAIT\_PRICE"\]) exists for that phone number within the last 30 minutes. If found, it greets the farmer with: *"Welcome back\! You already selected Ragi. Please enter your quantity in Quintals followed by hash,"* bypassing Steps 1 and 2\.

## **6\. Phase-Wise Implementation Plan (From Scratch to Complete Product)**

> **1.Phase 1: Provision Free Infrastructure & Local Repo Setup:**Day 1 — Zero-Cost Cloud & Telecom Provisioning.

> 1. Create a project directory annadata-dhwani/ with subdirectories backend/, frontend/, and audio\_cache/.  
> 2. Sign up for a **Supabase Free Tier** project, open the SQL Editor, and execute the PostGIS schema from Section 3.3.  
> 3. Sign up for an **Upstash Free Tier** Redis instance (or run local Redis / Python memory dict for offline testing) and copy the connection URL.  
> 4. Sign up for a **Twilio Free Trial** account, claim 1 free trial phone number, and verify 2 personal mobile numbers under **Verified Caller IDs** (one to represent the Mysuru Karnataka farmer, one for the Nashik Maharashtra farmer).

> **2.Phase 2: Build the Multilingual TTS Pre-Cacher & Price Engine:**Day 2 — Pre-Warming Neural Regional Voices & Agmarknet Cache.

> 1. Install edge-tts and run a startup script (prewarm\_audio.py) that pre-generates the static greeting, crop menu, and confirmation prompts in **Kannada (kn-IN-SapnaNeural)**, **Marathi (mr-IN-AarohiNeural)**, **Hindi (hi-IN-SwaraNeural)**, and **English (en-IN-NeerjaNeural)** into audio\_cache/.  
> 2. Build the **Agmarknet Mandi Price Service** (mandi\_service.py) that fetches daily district modal/floor prices from the Government of India Open Government Data (data.gov.in) API once every 6 hours and caches them in Redis with an offline fallback dictionary so your demo never fails if government servers are slow.

> **3.Phase 3: Implement the Hardened DTMF Webhook State Machine:**Day 3–4 — FastAPI State Machine, Guardrail & Drop Recovery.

> 1. Implement the FastAPI endpoints (/voice/incoming, /voice/start-callback, /voice/select-lang, /voice/select-crop, /voice/enter-qty, /voice/enter-price, /voice/guardrail-resolve) with **HMAC signature verification** and **Redis rate limiting**.  
> 2. Add the **Landholding Sanity Bound** (rejecting quantities above 50 Quintals for marginal farmers) and **Call-Drop Resume logic** (checking Redis for unfinished sessions before playing Step 1).  
> 3. Integrate the **PostGIS ST\_DWithin 5 km clustering query** on listing completion so every validated farmer listing automatically joins or creates a village Cluster Lot.

> **4.Phase 4: Build the Real-Time Distributor & FPO Web Portal:**Day 5 — Distributor Web Portal, FPO Verification & Dual-Mode Sync.

> 1. Connect your 3-column HTML/React dashboard (annadata\_dhwani\_multilang.html) to the FastAPI backend via /api/live-state polling or Server-Sent Events (SSE).  
> 2. Wire the **"Verify Quality (₹50 FPO Agent)"** modal so uploading a sample crop photo updates fpo\_verified \= TRUE and moisture\_pct \= 11.8% on the active Cluster Lot.  
> 3. Wire the **"Call Farmer with Counter-Offer"** button to /api/send-counter-offer, triggering an outbound call to your physical phone where pressing 1, 2, or 3 updates the web dashboard status to SOLD, REJECTED, or COUNTERED.

> **5.Phase 5: End-to-End Chaos Testing & Demo Hardening:**Day 6–7 — Chaos Testing, Keep-Alive Cron & Pitch Rehearsal.

> 1. Test all 4 failure scenarios: (a) Hang up mid-call at Step 3 and redial to verify Redis auto-resume; (b) Enter ₹3,200/Qtl for Ragi to trigger the ₹3,800/Qtl Agmarknet Guardrail; (c) Enter 9999\# Quintals to verify the sanity-bound rejection; (d) Trigger a counter-bid (3 \-\> 3920\#) from the physical phone keypad.  
> 2. Configure a free **GitHub Actions Cron Workflow** (running every 48 hours) to ping your Supabase database so it does not enter the 7-day inactivity pause before your competition finals.

## **7\. Pre-Warming Script for Zero-Latency Regional Audio (prewarm\_audio.py)**

Running this script once before starting your server pre-generates the core Kannada, Marathi, Hindi, and English audio prompts into audio\_cache/, reducing live webhook turnaround time from \~2.5 seconds to **less than 50 milliseconds**:

Python  
import os  
import hashlib  
import asyncio  
import edge\_tts

os.makedirs("audio\_cache", exist\_ok=True)

VOICE\_MAP \= {  
    "KN": "kn-IN-SapnaNeural",  
    "MR": "mr-IN-AarohiNeural",  
    "HI": "hi-IN-SwaraNeural",  
    "EN": "en-IN-NeerjaNeural",  
}

CORE\_PROMPTS \= \[  
    ("KN", "ಅನ್ನದಾತ ಧ್ವನಿಗೆ ಸ್ವಾಗತ. ಕನ್ನಡಕ್ಕಾಗಿ 1 ಒತ್ತಿರಿ. हिंदी के लिए 2 दबाएं. Press 3 for English."),  
    ("MR", "अन्नदाता ध्वनीमध्ये आपले स्वागत आहे. मराठीसाठी 1 दाबा. हिंदी के लिए 2 दबाएं. Press 3 for English."),  
    ("KN", "ಕನ್ನಡ ಆಯ್ಕೆ ಮಾಡಲಾಗಿದೆ. ನಮಸ್ಕಾರ ರಮೇಶ್ ಗೌಡರೇ\! ಮೈಸೂರು ಅಕ್ಟೋಬರ್ ಸುಗ್ಗಿಗೆ: ರಾಗಿಗಾಗಿ 1 ಒತ್ತಿರಿ, ಭತ್ತಕ್ಕಾಗಿ 2 ಒತ್ತಿರಿ, ಮೆಕ್ಕೆಜೋಳಕ್ಕಾಗಿ 3 ಒತ್ತಿರಿ, ಅಥವಾ ಇತರ ಬೆಳೆ ಹೆಸರನ್ನು ಹೇಳಲು 9 ಒತ್ತಿರಿ."),  
    ("MR", "मराठी भाषा निवडली आहे. नमस्कार तुकाराम पाटील\! नाशिक हंगामासाठी: लाल कांद्यासाठी 1 दाबा, सोयाबीनसाठी 2 दाबा, टोमॅटोसाठी 3 दाबा, किंवा इतर पिकाचे नाव सांगण्यासाठी 9 दाबा."),  
    ("KN", "ಅಭಿನಂದನೆಗಳು\! ನಿಮ್ಮ ವ್ಯಾಪಾರ ಖಚಿತವಾಗಿದೆ ಮತ್ತು ಎಸ್‌ಎಂಎಸ್ ರಸೀದಿ ಕಳುಹಿಸಲಾಗಿದೆ."),  
    ("EN", "Congratulations\! Deal locked and SMS escrow receipt dispatched."),  
\]

async def prewarm():  
    for lang, text in CORE\_PROMPTS:  
        voice \= VOICE\_MAP\[lang\]  
        file\_hash \= hashlib.md5(f"{voice}:{text}".encode("utf-8")).hexdigest()  
        filepath \= os.path.join("audio\_cache", f"{file\_hash}.mp3")  
        if not os.path.exists(filepath):  
            print(f"Generating \[{lang}\] \-\> {filepath}...")  
            communicate \= edge\_tts.Communicate(text=text, voice=voice, rate="-5%")  
            await communicate.save(filepath)  
    print("All core regional audio prompts cached locally\!")

if \_\_name\_\_ \== "\_\_main\_\_":  
    asyncio.run(prewarm())  
