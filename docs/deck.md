# Annadata Dhwani — Pitch Deck (6 Slides)

---

## Slide 1: The Problem — The Smallholder Poverty Trap
### Subtitle: Why 30 Million Farmers Cannot Sell Outside Local Village Middlemen

* **86% of Indian landholdings are small or marginal** (Operational holdings < 2 ha, Agriculture Census 2015-16).
* **Estimated ~30 Million farmers rely solely on 2G button phones** without internet access, apps, or touchscreens (*estimate based on 126M smallholders × 20–25% 2G penetration*).
* **The Minimum Order Quantity (MOQ) Trap:** Typical farmer harvests are 150–400 kg. Commercial buyers and distant mandis require 2–5 tonne truckloads; individual farmers cannot hire a truck.
* **Information Asymmetry & Price Blindness:** Local village traders offer distress rates. On 12 Nov 2026, Mandya market modal was ₹3,565/qtl against a government MSP of ₹5,205/qtl.
* **The Digital Divide:** Existing Agri-Tech platforms require Android smartphones, mobile data, and English/formal reading literacy.

**Suggested Visual:** Split screen: Left side shows a smallholder holding 3 bags of ragi with a ₹1,000 keypad phone; right side shows an empty 3-tonne commercial truck.  
**Speaker Notes (Anirudh):** "86% of India's farmers hold under two hectares. If you harvest 3 quintals of ragi, you cannot hire a truck to Mandya mandi. You sell to the village middleman at whatever cash price he dictates. Apps didn't fix this because 30 million of these farmers own basic button phones. Annadata Dhwani brings the market directly to their phone keypad without internet."

---

## Slide 2: How It Works — Voice & Keypad Marketplace
### Subtitle: From Missed Call to Pooled Truckload in 6 Steps

```
[Farmer Button Phone]  ---> Gives Missed Call (Free)
         |
[FastAPI Engine]       ---> Automated Call-Back with Recorded Kannada/Hindi Audio
         |
[Keypad DTMF]          ---> Farmer enters Crop (1=Ragi), Quantity (qtl), Ask Price (₹)
         |
[FPO Collection Point] ---> Listings pooled into 2–5 Tonne Verified Clusters
         |
[FPO Field Agent]      ---> Inspects grain, logs moisture & live geotagged photo on PWA
         |
[Web Buyer Portal]     ---> Verified cluster auctioned; winning bid accepted by farmer via Keypad
```

* **Zero-Cost Access:** Farmer spends ₹0 (missed-call trigger and toll-free callback).
* **Narrowband Audio (8 kHz):** Clear recorded prompts in native Kannada and Hindi.
* **Physical Aggregation:** Hyperlocal FPO collection points aggregate micro-lots into 2–5 tonne commercial clusters.
* **Dual Consent:** Farmers retain full sovereignty; winning bids must be confirmed on the phone keypad.

**Suggested Visual:** Clean 6-step flow diagram with icons for button phone, audio wave, collection yard, and buyer dashboard.  
**Speaker Notes (Anirudh):** "A farmer dials our number and hangs up. The platform rings back immediately. A recorded voice in Kannada asks for the crop, quantity in quintals, and expected price. As neighbors call in, our engine pools them at the local FPO yard. Once 20 quintals accumulate, the FPO field agent inspects the grain and takes a geotagged photo. Buyers bid in an auction, and the farmer accepts or rejects the top bid with key 1 or 2."

---

## Slide 3: Live Demonstration Cue
### Subtitle: Real-Time End-to-End Transaction & Failure Resiliency

* **Scene 1 (Farmer Call):** Live missed call from button phone → callback received → Kannada IVR guidance.
* **Scene 2 (Fair Pricing Guardrail):** Farmer keys in ₹3,200/qtl → System warns against mandi floor of ₹3,430/qtl → Farmer presses 1 to raise price.
* **Scene 3 (Reliability / Drop Recovery):** Battery pulled mid-call → Call dropped → Re-dial acknowledges: *"Welcome back, continuing where you stopped"*.
* **Scene 4 (FPO Verification):** Cluster reaches 2 tonnes → FPO agent uploads live photograph and GPS coordinates from mobile PWA.
* **Scene 5 (Auction & Confirmation):** Institutional buyers outbid each other live on WebSocket dashboard → Winning bid triggers automated confirmation call to farmers.

**Suggested Visual:** Live demonstration setup diagram showing the dual button phone on speaker, projector showing the Operations Monitor, and buyer laptop.  
**Speaker Notes (Anirudh):** "We will now demonstrate this live. Watch the Ops screen on the projector. Hitesh will give a missed call on a standard button phone, trigger an intentional key-bounce, simulate a network drop, and we will verify the pooled lot live on stage."

---

## Slide 4: Engineering Proof — Designed for the Physics of Rural India
### Subtitle: Deterministic Signalling Over Narrowband Telephony

* **DTMF over Speech Recognition:** 0% Word Error Rate (WER) on numbers. Eliminates acoustic failures from tractor noise, wind, and regional dialects.
* **Narrowband Audio Pipeline:** Bandpass filtered (300–3,400 Hz), 8 kHz / 16-bit PCM, loudness-normalized to -16 LUFS.
* **Debounce & Key-Bounce Filtration:** Hardware switch contact bounce dropped at 120 ms; idempotency keys prevent duplicate listing creation.
* **Transactional State Integrity:** PostgreSQL row-level locks prevent race conditions during concurrent bids; Redis cache is completely disposable (`FLUSHALL` safe mid-call).
* **Data Privacy by Design:** Farmer mobile numbers are never exposed to buyers or agents; masked E.164 tokens used across all APIs.

**Suggested Visual:** Waveform comparison showing 8 kHz telephone audio vs DTMF tone filter + PostgreSQL lock diagram.  
**Speaker Notes (Anirudh):** "Rural voice AI fails when speech recognition encounters an 8 kHz phone line with a 26% error rate. We engineered around the physics: DTMF tone signalling for numbers has zero error rate. Our Redis reliability layer deduplicates key bounces, and all bid concurrency is settled with PostgreSQL row locks so no deal can be double-sold."

---

## Slide 5: Unit Economics & Financial Sustainability
### Subtitle: Healthy Contribution Margin on a 1.5% Buyer Fee Model

| Metric | Cluster Economics (24 Quintals Ragi) |
|---|---|
| **Gross Commodity Value** | **₹84,000** (24 qtl @ ₹3,500/qtl) |
| **Buyer Platform Fee (1.5%)** | **₹1,260** |
| Telephony Cost (assumed ₹0.60/min) | - ₹26.00 (Listing + Offer callbacks) |
| FPO Field Verification Incentive | - ₹50.00 |
| **Net Contribution per Closed Cluster** | **₹1,184.00 (94% margin)** |
| **Listing Callback Cost per Farmer** | **₹1.56** (vs ₹157.50 average fee share) |

* **Fixed Production Overhead:** Exotel Business Plan (~₹9,999 for 5 months) + Telecom DLT registration (~₹5,900) = **₹15,899**.
* **Breakeven Threshold:** Just **14 closed clusters** across 5 months pays for the entire fixed infrastructure.
* **Farmer Direct Benefit:** Farmers gain ₹200–₹400 more per quintal by bypassing sub-mandi village aggregates.

**Suggested Visual:** Stacked bar chart showing gross revenue ₹1,260 vs direct costs ₹76, leaving ₹1,184 net contribution.  
**Speaker Notes (Anirudh):** "The economics work because callbacks are cheap. A 2.5-minute listing call costs ₹1.56. When 8 farmers form a 24-quintal cluster sold for ₹84,000, our 1.5% buyer fee generates ₹1,260. Direct variable costs are ₹76, leaving ₹1,184 contribution per cluster. Closing just 14 clusters in 5 months covers all fixed telecom licensing and server costs."

---

## Slide 6: Production Readiness & Boundary Honesty
### Subtitle: What is Real Today vs What is Simulated

* **What is 100% Real Today:**
  * Core telephony state engine, IVR flow, and queue worker.
  * Real Agmarknet daily price feed ingestion (Mandya & Mysuru) with AFPP dynamic floor computation.
  * Pre-generated 8 kHz audio asset library in Kannada and Hindi.
  * Cluster aggregation algorithms and PostGIS geographic collection yard assignment.
  * Real-time WebSocket bidding dashboard and multi-buyer state sync.
  * Live hardware button phone call via Exotel cloud telephony trial.
* **What is Simulated in the Demo:**
  * Secondary farmers' phones and simultaneous outbidding buyers (simulated to demonstrate concurrency).
  * Bank payment settlement (buttons simulate UTR receipt; platform never takes custody of funds).
* **Production Deployment Requirements:**
  * Commercial Telecom DLT header registration and commercial SIP trunking.
  * Compliance with Karnataka APMC e-trading notification and DPDP Act provisions.

**Suggested Visual:** A two-column table: "Production-Grade Engine (Real)" vs "Demo Acceleration (Simulated)".  
**Speaker Notes (Anirudh):** "We believe in engineering honesty. The call engine, pricing math, PostGIS clustering, and live bidding are completely real and running on our server right now. Payments and secondary bidders are simulated because our platform never holds farmer money—buyers settle directly with the FPO account upon yard delivery."
