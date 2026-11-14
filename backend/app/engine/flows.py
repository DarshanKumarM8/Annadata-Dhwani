"""Prompt table for the LISTING flow (contract C8, plan section 5.4). Owner: Darshan.

SPEC gives the input collection rule per state. build() turns a session into the clips for that state.
BID_OFFER (D6): OFFER, OFFER_CONFIRM, DONE_OFFER.
"""
from .actions import Action
from .audio_shim import digit_clips

TERMINAL = {"DONE", "DONE_OFFER", "HELP", "BYE", "NOT_REGISTERED"}
RESUMABLE = {"QTY", "QTY_CONFIRM", "PRICE", "GUARD", "FINAL"}
GUARD_FACTOR = 0.97   # below afpp * 0.97 the guardrail fires

# state -> (max_digits, finish_on_key, timeout_s)
SPEC: dict[str, tuple[int, str, int]] = {
    "LANG": (1, "", 6),
    "CONSENT": (1, "", 8),
    "MAIN": (1, "", 6),
    "CROP": (1, "", 6),
    "QTY": (2, "#", 8),
    "QTY_CONFIRM": (1, "", 6),
    "PRICE": (5, "#", 10),
    "GUARD": (1, "", 8),
    "FINAL": (1, "", 8),
    "OFFER": (1, "", 8),
    "OFFER_CONFIRM": (1, "", 8),
}


def _num(n) -> list[str]:
    return digit_clips(int(round(float(n))))


def clips_for(state: str, s: dict) -> list[str]:
    d = s["data"]
    floor = d.get("floor")
    if state == "LANG":
        return ["welcome", "kn:lang_option", "hi:lang_option", "en:lang_option"]
    if state == "CONSENT":
        return ["consent"]
    if state == "MAIN":
        return ["main_menu"]
    if state == "CROP":
        out = ["crop_menu_intro"]
        for i, crop in enumerate(d.get("menu", []), start=1):
            out.append(f"cropkey_{crop}_{i}")
        return out + ["helper_key_0"]
    if state == "QTY":
        return ["ask_qty"]
    if state == "QTY_CONFIRM":
        return ["you_entered", f"qty_{d['qty']}", "confirm_1_2"]
    if state == "PRICE":
        if floor:
            return (["mandi_price_was", *_num(floor["modal_price"]), "rupees_per_qtl",
                     "fair_price_is", *_num(floor["afpp"]), "rupees_per_qtl", "ask_price"])
        return ["no_price_today", "ask_price"]
    if state == "GUARD":
        return ["guard_warn", *_num(floor["afpp"]), "rupees_per_qtl", "guard_options"]
    if state == "FINAL":
        return ["final_intro", f"qty_{d['qty']}", f"crop_{d['crop']}", "at_price",
                *_num(d["price"]), "rupees_per_qtl", "final_confirm"]
    if state == "DONE":
        return ["listed_ok", "your_number_is", *digit_clips(d["code"]), "will_call"]
    if state in ("HELP", "NOT_REGISTERED"):
        head = ["not_registered"] if state == "NOT_REGISTERED" else []
        return head + ["helper_will_call", "helper_code_is", *[f"d_{c}" for c in d["verbal_code"]]]
    if state == "OFFER":
        o = d["offer"]
        return ["offer_intro", *_num(o["price"]), "rupees_per_qtl", "for_your", f"qty_{int(o['qty'])}",
                f"crop_{o['crop']}", "your_ask_was", *_num(o["ask"]), "rupees_per_qtl", "offer_options"]
    if state == "OFFER_CONFIRM":
        return ["offer_confirm"]
    if state == "DONE_OFFER":
        return ["offer_done"]
    if state == "BYE":
        if d.get("offer_closed"):
            return ["offer_closed"]
        return ["offer_rejected"] if d.get("offer_rejected") else ["bye"]
    raise ValueError(f"no prompt for state {state}")


def build(state: str, s: dict, prefix: list[str] | None = None) -> Action:
    clips = (prefix or []) + clips_for(state, s)
    if state in TERMINAL:
        return Action(clips=clips, lang=s["lang"], state=state, hangup=True)
    maxd, fin, to = SPEC[state]
    return Action(clips=clips, lang=s["lang"], max_digits=maxd, finish_on_key=fin, timeout_s=to, state=state)
