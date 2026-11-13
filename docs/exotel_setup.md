# Exotel Setup & Real-Phone Test Log (`N1`, `N6`, `N7`)

## 1. Trial Account & ExoPhone Configuration (Task N1)
- **Trial Start Date:** 2026-11-13
- **Trial ExoPhone Number:** `080-6929-XXXX` (Whitelisted demo ExoPhone)
- **Missed-Call Auto-Hangup Enabled:** Yes (cuts after 1–2 rings)
- **Credentials Sent to Backend Lead (Darshan via private DM):** `EXOTEL_SID`, `EXOTEL_API_KEY`, `EXOTEL_API_TOKEN`, `EXOPHONE` (Never committed to Git)

### Whitelisted Numbers (Max 10 on Trial)
| # | Role / Person | Masked Number | Verified Status |
|---|---|---|---|
| 1 | Demo Button Phone (Primary Farmer) | `+91 98••••••01` | Verified |
| 2 | Darshan (Backend Lead) | `+91 98••••••02` | Verified |
| 3 | Nahyan (Frontend/Dev Lead) | `+91 98••••••03` | Verified |
| 4 | Hitesh (Voice AI Lead) | `+91 98••••••04` | Verified |
| 5 | Anirudh (Agent/Ops Lead) | `+91 98••••••05` | Verified |

### N1 Verification Log
| Date / Time | Step | Result | Notes |
|---|---|---|---|
| 2026-11-13 14:00 | Trial Signup & Credit Check | PASS | ₹500 trial credit active |
| 2026-11-13 14:30 | Whitelist 5 Numbers | PASS | All OTPs verified successfully |
| 2026-11-13 15:00 | Inbound Missed Call Test | PASS | Disconnected after 1–2 rings, ₹0 balance deducted |

---

## 2. App Bazaar Flow `annadata-ivr` (Task N6)
- **App ID (`EXOTEL_APP_ID`):** `782910`
- **Webhook Base:** `https://api.annadata.internal/tel/exotel/<WEBHOOK_SECRET>`

### N6 App Bazaar Spike Observations
| # | Check | Expected | Observed | Status |
|---|---|---|---|---|
| a | Does Gather call `/gather?step=1` and play our JSON `audio_url`? | GET request received, WAV plays on phone | GET `/tel/exotel/.../gather?step=1` logged; Edge TTS WAV audio played clearly on keypad phone | PASS |
| b | Exact format of `digits` query param at `/digits?step=1` | Wrapped in literal quotes (e.g. `"1"`) | Received `digits="1"` (literal quotes included in query param) | PASS |
| c | Does returning HTTP `404` from `/digits` trigger the Failure → Hangup branch? | Call disconnects cleanly | Entering invalid key / reaching terminal step returned `404` and hung up cleanly | PASS |
| d | Can Passthru `200 OK` loop back to an earlier Gather applet? | Test if UI allows pointing back to Gather 1 | App Bazaar visual builder only allows dragging new downstream applets (no backward loop arrows), which is why 12 chained Gather→Passthru pairs are required | PASS |

---

## 3. Real Phone Test Protocol & Results (Task N7)

### 3.1 Test Protocol & Execution Instructions
This protocol tests the full IVR loop on a physical button phone in coordination with the backend server engineer (Darshan):

1. **Complete Listing (5 runs):**
   - *Steps:* Give a missed call to the ExoPhone from the physical phone. Wait for automated callback. Answer call. Listen to prompt in Kannada/English. Enter crop key (`1` for Ragi, `2` for Maize, `3` for Paddy), enter quantity followed by `#`, enter expected price followed by `#`, press `1` to confirm.
   - *Communication with Server Engineer:* "Starting Missed Call Run #X now; verify `call_jobs` queue picks up callback and logs state transitions."
   - *Stopwatch Timing:* Start when physical phone ends missed call; stop when incoming callback rings. (Target: ≤ 10 seconds).
   - *Pass/Fail Rule:* Callback arrives ≤ 10s; audio plays audibly through earpiece; DTMF inputs are acknowledged; listing lot recorded in database.

2. **Dropped Call Battery-Pull & Resume (1 run):**
   - *Steps:* Initiate listing. Enter crop and quantity. While the prompt asks for price, physically yank the battery out of the handset. Wait 30 seconds. Replace battery and power on. Give a missed call to the ExoPhone again.
   - *Communication with Server Engineer:* "Battery yanked at quantity state; confirm Redis/Postgres checkpoint saved session state; sending reconnect missed call."
   - *Stopwatch Timing:* Time to callback.
   - *Pass/Fail Rule:* Server recognizes returning caller, announces *"Welcome back"*, and resumes prompt directly at the price entry step without restarting the entire survey.

3. **Bid Acceptance Offer Call (1 run):**
   - *Steps:* Teammate triggers offer call from backend / demo board for an active cluster with an accepted buyer bid. Physical phone rings. Answer call. Listen to offer details (quintals and winning bid price). Press `1` to proceed, press `1` to finalize acceptance.
   - *Pass/Fail Rule:* Phone rings within 5s of auction close; clear offer summary audio; DTMF `1` then `1` confirmed; deal created with 1.5% fee.

4. **Prepaid Balance Deduction Verification (2 operators):**
   - *Steps:* Check prepaid balance via USSD code (`*123#` on Airtel, MyJio app / SMS on Jio) before giving missed call. Dial ExoPhone until auto-disconnect. Check prepaid balance immediately after.
   - *Pass/Fail Rule:* Exactly ₹0.00 deducted on both operators (guaranteeing 100% free access for marginal farmers).

---

### 3.2 Real Phone Test Results Log
| Run # | Time | Operator | Callback Latency (s) | Scenario | Result | Notes |
|---|---|---|---|---|---|---|
| 1 | 16:35:10 | Airtel (Keypad) | 4.8s | Full Listing #1 (Ragi 25qtl @ ₹3200) | **PASS** | Crisp audio, prompt response instantaneous |
| 2 | 16:42:25 | Airtel (Keypad) | 5.1s | Full Listing #2 (Maize 40qtl @ ₹2150) | **PASS** | DTMF tone detection clean without debounce glitch |
| 3 | 16:50:00 | Jio (Feature) | 6.2s | Full Listing #3 (Paddy 30qtl @ ₹2400) | **PASS** | Clear Kannada audio prompt played |
| 4 | 16:58:15 | Jio (Feature) | 5.5s | Full Listing #4 (Ragi 15qtl @ ₹3300) | **PASS** | Verified cluster threshold accumulation |
| 5 | 17:05:40 | Airtel (Keypad) | 4.9s | Full Listing #5 (Ragi 20qtl @ ₹3250) | **PASS** | Cluster moved to `READY` status automatically |
| 6 | 17:15:20 | Airtel (Keypad) | 5.3s | Dropped Call (Battery yanked at QTY) | **PASS** | Checkpoint rehydrated; prompt resumed at price step |
| 7 | 17:30:00 | Airtel (Keypad) | 3.9s | Outbound Offer Call (Bid Acceptance) | **PASS** | Pressed `1` then `1`; deal closed and SMS triggered |
| 8 | 17:40:10 | Airtel (Prepaid)| N/A | Balance check before: ₹42.50, after: ₹42.50 | **PASS** | ₹0.00 deducted on missed call disconnect |
| 9 | 17:45:00 | Jio (Prepaid) | N/A | Balance check before: ₹10.00, after: ₹10.00 | **PASS** | ₹0.00 deducted on missed call disconnect |

**Summary:** 9/9 tests passed. Real handset tests verify that Exotel missed-call triggering, IVR callback latency (avg 5.1s), DTMF processing, session rehydration, and zero-cost accessibility operate reliably under real-world cellular conditions.
