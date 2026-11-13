# IVR states (C8)

Flows: `LISTING` (callback after a missed call), `BID_OFFER` (outbound offer call), `UNKNOWN_CALLER`.
Terminal states: `DONE`, `DONE_OFFER`, `HELP`, `BYE`, `NOT_REGISTERED` (Action has `hangup=true`).

| State | Collect | Keys → next | Timeout |
|---|---|---|---|
| `LANG` (first call only) | 1 digit | 1 → kn, 2 → hi, 3 → en → `CONSENT` (needs `db/003_add_english_language.sql` on old databases) | 6 s |
| `CONSENT` (first call only) | 1 digit | 1 → `MAIN`/`CROP`; 2 → `BYE` | 8 s |
| `MAIN` (has a live listing) | 1 digit | 1 → `CROP`; 0 → `HELP` | 6 s |
| `CROP` | 1 digit | 1–3 → `QTY`; 0 → `HELP`; crop already live → `already_listed` → `MAIN` | 6 s |
| `QTY` | ≤2 digits, `#` or timeout ends | 1..max_listing_qtl → `QTY_CONFIRM` | 8 s |
| `QTY_CONFIRM` | 1 digit | 1 → `PRICE`; 2 → `QTY` | 6 s |
| `PRICE` | ≤5 digits, `#` or timeout ends | in [min_price,max_price]: below afpp×0.97 → `GUARD`, else `FINAL` | 10 s |
| `GUARD` | 1 digit | 1 → `FINAL` (price = afpp); 2 → `FINAL`; 3 → `PRICE` | 8 s |
| `FINAL` | 1 digit | 1 → commit → `DONE`; 2 → `CROP` | 8 s |
| `OFFER` | 1 digit | 1 → `OFFER_CONFIRM`; 2 → reject → `BYE`; 9 → `OFFER` | 8 s |
| `OFFER_CONFIRM` | 1 digit | 1 → accept → `DONE_OFFER`; 2 → `OFFER` | 8 s |
| `NOT_REGISTERED` | none | ticket opened, hang up | — |

Rules: key `8` repeats the prompt in `QTY_CONFIRM`, `PRICE`, `GUARD` and `FINAL` without using a retry (the recorded prompts say "press 8 to repeat"; not in `QTY`, where a lone 8 is a valid quantity);
invalid key or timeout replays the prompt at most 2 times; the 3rd failure → `BYE` and `fail:{phone}`+1;
3 failed calls in 24 h → triage ticket. Total call cap 240 s. A session resumes within 30 min of the last event.
Debounce (simulator only): same digit within 120 ms dropped; any digit within 40 ms dropped.
