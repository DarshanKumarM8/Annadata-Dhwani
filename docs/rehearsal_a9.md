# Task A9: Demo Rehearsal Cue Card & Jury Q&A Guide
**Presenter:** Anirudh (FPO Agent PWA, Market Pricing, Economics & Governance)  
**Demo Duration:** 7 Minutes Total

---

## Part 1: Live Demo Cue Card

| Time | Demo Moment | Your Action / Click | What You Say (1 Sentence) | Fallback / If Blocked |
|---|---|---|---|---|
| **0:00 – 1:30** | Opening & Problem Setup | Click through **Slides 1 & 2**. Introduce the MOQ trap and 2G button phone reality. | *"Over 30 million smallholders in India cannot use Agri-Tech apps because they rely on basic keypad phones and harvest lots too small for a commercial truck."* | If projector fails, speak directly from slide notes. |
| **1:30 – 3:30** | Live Phone Call & IVR | Hand off to Hitesh for button phone call on speaker. Point out the **fair price floor** announced in Kannada. | *"Notice how the system spoke yesterday's Mandya mandi price of ₹3,565 and warned the farmer when he keyed in a price below our ₹3,430 floor."* | If real phone delays, Hitesh clicks the simulator tab. |
| **3:30 – 4:30** | Cluster Verification | Open **Agent PWA** on your phone (`http://localhost:5173/agent`). Select Cluster A (17 qtl -> 20 qtl). Tap **Verify**, capture grain photo, select **Grade A**, submit. | *"As listings accumulate at the Keregodu collection point, I act as the FPO field agent, capturing a live photo and verifying grain grade to unlock the cluster for buyer bidding."* | **Fallback:** If camera/GPS blocks, lead presenter clicks "Verify Cluster" on the Admin Ops dashboard. |
| **4:30 – 5:30** | Bidding & Deal Confirmation | Direct audience attention to Nahyan's **Buyer Dashboard**. Watch the verified cluster appear live and bids roll in. | *"The moment verification is submitted, the cluster transitions to BIDDING, where institutional buyers compete in a real-time WebSocket auction."* | If WebSocket drops, refresh page to reload state from REST. |
| **5:30 – 7:00** | Architecture, Economics & Wrap | Advance to **Slides 4, 5 & 6**. Explain unit economics and DTMF engineering design. | *"With a 94% contribution margin per closed cluster and zero speech-recognition error rate on digits, Annadata Dhwani offers a viable, production-ready path to digitizing rural farm-gate trade."* | Take questions from jury. |

---

## Part 2: Jury Q&A Preparation (Anirudh's Domain)

### Q1: "How do you calculate the fair farm-gate price (AFPP), and what happens if mandi price data is missing or delayed?"
**Answer:**  
Our system fetches daily modal mandi prices directly from the government `data.gov.in` Agmarknet feed and deducts standardized transport, handling, and shrinkage fees ($\text{AFPP} = \text{Modal} \times 0.98 - ₹60/\text{qtl}$, rounded to the nearest ten). When daily mandi data is thin or delayed, our pricing engine falls back through a 3-tier hierarchy: today's district modal $\to$ 7-day district median $\to$ 7-day state median, and speaks the basis aloud to the farmer.

---

### Q2: "Why don't you use the government Minimum Support Price (MSP) as the price floor?"
**Answer:**  
MSP is an administrative target, not a market-clearing price; on the date of our test, Mandya ragi traded in the open market at ₹3,565/qtl while the government MSP was ₹5,205/qtl. Enforcing MSP as a rigid floor would prevent transactions from occurring, leaving farmers with unsold grain; we use the real mandi median as the operational floor and display MSP solely for context.

---

### Q3: "Does the platform handle money directly, and how do farmers receive payment?"
**Answer:**  
No, Annadata Dhwani is deliberately non-custodial and never holds farmer or buyer funds, eliminating banking license burdens. When an auction closes, the buyer pays the registered FPO bank account or UPI directly upon physical pickup at the yard, and the FPO settles individual farmer shares according to our recorded weighment totals.

---

### Q4: "What happens if an FPO agent tries to verify a cluster while sitting at home instead of at the yard?"
**Answer:**  
The verification endpoint strictly requires GPS coordinates captured through the browser's high-accuracy Geolocation API and calculates the PostGIS distance to the designated collection point. If the agent is more than 500 meters away from the registered collection yard coordinates, the API rejects the request with HTTP 422 `TOO_FAR`.

---

### Q5: "What are the regulatory, telecom, and legal hurdles before this can deploy in production?"
**Answer:**  
In production, we require commercial Distributed Ledger Technology (DLT) registration under TRAI regulations for telecom headers, and compliance with state agricultural market rules (such as Karnataka's e-trading notification for notified agricultural commodities). Furthermore, we must comply with the Digital Personal Data Protection (DPDP) Act of 2023 by recording explicit IVR consent before storing farmer phone numbers.

---

### Q6: "What prevents buyers and farmers from bypassing your platform once they discover each other (disintermediation)?"
**Answer:**  
Disintermediation is naturally prevented because individual farmers produce micro-lots of 2–4 quintals which commercial institutional buyers cannot economically collect door-to-door. Buyers rely on our platform for aggregated 2–5 tonne lots, physical quality verification, and collection point consolidation, which individual smallholders cannot independently provide.
