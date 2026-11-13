# Annadata Dhwani 2.0: Master 24-Hour Hackathon Execution Plan
**Theme:** Samriddh Annadata, Samriddh Bharat (Agri-Tech Innovation)
**Core Tech:** Exotel DTMF + AI Spatial Pooling + Multilingual TTS

This document serves as your team's battle plan for a 24-hour hackathon. It replaces Twilio with Exotel for native Indian telecom compliance, outlines a 100% free-tier stack, eliminates hardcoding through smart API caching, and divides tasks optimally across a 3-to-4 person team.

---

## 1. The Zero-Cost Tech Stack & Necessary APIs

To build this in 24 hours without spending money, register for these free tiers immediately:

*   **Telephony:** **Exotel Trial Account** (₹1000 free credits, KYC with Aadhaar/PAN). Gets you an ExoPhone (Virtual Number) and API access.
*   **Backend & APIs:** **Python FastAPI** (Fastest for handling audio/webhooks). Host locally via **Ngrok** (Free tier) so Exotel can reach your `localhost`.
*   **Database & Real-time:** **Supabase Free Tier** (500MB DB). Enables PostgreSQL, the PostGIS extension (for 5km spatial pooling), and Real-time WebSockets.
*   **Session Management:** **Upstash Serverless Redis** (Free tier). Crucial for tracking the farmer's keypad presses mid-call and call-drop recovery.
*   **Text-to-Speech (TTS):** **edge-tts** (Python library, 100% free) or **Bhashini API**. Generates Kannada/Marathi/Hindi prompts dynamically.
*   **Mandi Price API:** **data.gov.in (Agmarknet)** (Free API key). Fetches live crop floor prices to prevent hardcoding.
*   **Frontend Dashboard:** **Next.js (App Router) + Tailwind CSS** + `shadcn/ui`. Hosted locally or on Vercel.

---

## 2. Team Roles & Parallel Task Distribution

For a 24-hour sprint, strict division of labor is critical. Do not overlap on code; agree on API JSON contracts at hour 1.

### Hacker 1: The Telecom Engineer (Backend & Exotel)
*   **Goal:** Make the phone ring, parse keypad presses, and manage call states.
*   **Tasks:**
    *   Set up FastAPI server and Ngrok tunnel.
    *   Configure Exotel AppBuilder: *Passthru Applet* (missed call) -> FastAPI Webhook.
    *   Write the state machine in Python: `/trigger-call`, `/menu-crop`, `/menu-qty`, `/menu-price`.
    *   Integrate Upstash Redis to remember the caller's state between keypad presses.
    *   Generate the dynamic Exotel `nXML` (Exotel's XML format for `<Play>` and `<Gather>`).

### Hacker 2: The Data & Spatial Architect (DB & Integrations)
*   **Goal:** Build the "brain" that prevents hardcoding and groups the farmers.
*   **Tasks:**
    *   Set up Supabase tables (`farmers`, `cluster_lots`, `crop_listings`).
    *   Enable PostGIS and write the `ST_DWithin` query to cluster harvests within 5km.
    *   Write the Python script (`prewarm_audio.py`) using `edge-tts` to generate the regional audio prompts at startup.
    *   Integrate the Agmarknet API to fetch real prices based on the farmer's district.
    *   **Hackathon Cheat:** Write a seed script to populate the DB with 50 fake farmers and active cluster lots so the map and dashboard look alive during the demo.

### Hacker 3: The Dashboard Developer (Frontend Next.js)
*   **Goal:** Build the "Wow Factor" UI for the judges/distributors.
*   **Tasks:**
    *   Scaffold Next.js with Tailwind and `shadcn/ui` for rapid, beautiful components.
    *   Build a 3-column layout: Active Clusters, Live Incoming Calls, and FPO Verification Tasks.
    *   Integrate `@supabase/supabase-js` Real-time subscriptions. When Hacker 1's backend inserts a new DTMF listing, the UI must update instantly with a green "New" badge.
    *   Build the FPO "Verify Lot" modal (simulating a photo upload).

### Hacker 4 (If available): Pitch, QA, & "Chaos" Tester
*   **Goal:** Ensure the demo is bulletproof and the presentation aligns with the *Samriddh Annadata* theme.
*   **Tasks:**
    *   Test Exotel flows on real feature phones (find edge cases like dropped calls).
    *   Design the presentation focusing on Track A (Tech) and Track B (Business Model).
    *   Ensure the narrative flows: *Missed Call -> AI Prediction -> Keypad Entry -> PostGIS Pooling -> Dashboard Sync*.

---

## 3. The 24-Hour Execution Timeline

**T-24:00 to T-22:00 | Foundation & Infrastructure**
*   Create GitHub repo. Add all team members.
*   Set up Supabase, Upstash Redis, Exotel trial, and Ngrok.
*   Agree on the JSON schema for DB tables and API endpoints.

**T-22:00 to T-14:00 | Core Building (The Heavy Lift)**
*   *H1:* Wires Exotel to FastAPI. Successfully logs a Missed Call and triggers an Outbound Call back to the user.
*   *H2:* Writes SQL schema in Supabase. Builds the Agmarknet fetcher and TTS audio generator. Creates the 50 mocked users.
*   *H3:* Finishes static UI layout in Next.js. Connects to Supabase to display the mocked data.

**T-14:00 to T-08:00 | Integration & "No Hardcoding" Logic**
*   *H1 & H2:* Merge backend logic. When a user presses a DTMF key, it correctly updates Redis, checks the live Agmarknet floor price, and finally inserts into Supabase.
*   *H3:* Implements Supabase Real-time. When a row hits the DB, the Next.js UI flashes and updates.

**T-08:00 to T-04:00 | The Spatial Clustering & Error Handling**
*   *H2:* Implements the PostGIS 5km radius grouping logic.
*   *H1:* Adds call-drop recovery (if a call hangs up at step 2, Redis resumes at step 2 on redial) and rate limiting (max 3 calls).

**T-04:00 to T-00:00 | Demo Hardening, Pitch Deck, & Sleep**
*   Do an end-to-end dry run: Make a missed call from a physical keypad phone -> Enter DTMF -> Watch the UI update.
*   Handle the "Demo Gods": Pre-record a video of the system working flawlessly just in case Ngrok or cellular networks fail on stage.
*   Finalize the pitch deck.

---

## 4. Step-by-Step Exotel Implementation (Without Twilio)

Exotel works slightly differently than Twilio. Here is how you configure it to avoid costs for the farmer.

**Step 1: The Zero-Cost Missed Call (Exotel AppBuilder)**
1. Go to Exotel AppBuilder -> Create New App ("Annadata Inbound").
2. Drag and drop a **Passthru Applet**.
3. Set the URL to your Ngrok tunnel: `https://[YOUR-NGROK]/api/trigger-missed-call`.
4. Exotel will hit your server and immediately hang up. The farmer pays ₹0.

**Step 2: The FastAPI Callback Logic**
Your Python backend receives the missed call webhook, looks up the user, and uses Exotel's Outbound Call API to call them back.

```python
# HACKATHON CHEAT: Use Exotel's Outbound Call API
import requests

def trigger_outbound(farmer_phone):
    exotel_url = f"https://api.exotel.com/v1/Accounts/{EXOTEL_SID}/Calls/connect"
    data = {
        "From": farmer_phone, 
        "To": EXOPHONE_NUMBER,
        "CallerId": EXOPHONE_NUMBER,
        # This tells Exotel what to do when the farmer picks up
        "Url": "https://[YOUR-NGROK]/api/exotel/menu-lang" 
    }
    requests.post(exotel_url, auth=(EXOTEL_KEY, EXOTEL_TOKEN), data=data)
```

**Step 3: DTMF Capture (nXML)**
When the farmer picks up, Exotel requests `Url`. You must return **nXML**.

```xml
<!-- Response from /api/exotel/menu-lang -->
<Response>
    <!-- Gathers 1 digit, then POSTs to the next step -->
    <Gather numDigits="1" action="https://[YOUR-NGROK]/api/exotel/menu-crop" method="POST">
        <!-- Hackathon tip: Serve your edge-tts MP3s statically via FastAPI -->
        <Play>https://[YOUR-NGROK]/audio_cache/kannada_greeting.mp3</Play>
    </Gather>
</Response>
```

## 5. Hackathon "Smart Build" Hacks

1.  **Don't generate audio on the fly:** Generating AI speech takes 2-3 seconds, causing Exotel webhooks to time out. Run `edge-tts` once at the start of the hackathon to generate all combinations (e.g., `crop_menu_kn.mp3`, `price_guardrail_mr.mp3`) and serve them statically.
2.  **Fake the scale:** A marketplace with one listing looks bad. Your database person *must* seed the PostGIS database with 10-15 active "Cluster Lots" across India before the demo starts. When you do your live demo, your new listing should join one of these existing clusters visually on the map.
3.  **Localize the Pitch:** Register one team member's phone number as "Mysuru, Karnataka" (Plays Kannada) and another as "Nashik, Maharashtra" (Plays Marathi). Having the physical Nokia phone speak the local language of the hackathon venue usually secures an automatic win.