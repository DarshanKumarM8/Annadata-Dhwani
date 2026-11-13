# Contracts (frozen at H2)

The source of truth for every shared interface is **TASK_DIVISION.md §3 (C1–C11)**. This folder holds
the machine-readable parts:

| File | Contract |
|---|---|
| `clip_ids.txt` | C8: every audio clip id. Each must exist as `audio/kn/<id>.wav` and `audio/hi/<id>.wav` (8000 Hz, mono, 16-bit PCM) |
| `states.md` | C8: IVR state names and transitions |
| `fixtures/*.json` | C4/C5/C11: example responses served by `mock/mock_server.py` |
| `fixtures/sample.wav` | Placeholder prompt audio used by the mock simulator socket |

**Change rule:** after H2, only Darshan changes these files, and only after announcing the exact diff in the group.
