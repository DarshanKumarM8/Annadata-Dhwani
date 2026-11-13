"""State-table tests for the call engine, run against in-memory fake dependencies (no DB, no Redis)."""
import pytest

from app.engine.actions import Event
from app.engine.debounce import Debouncer
from app.engine.engine import ListingExists, handle_event

CROPS = {"ragi": {"code": "ragi", "max_listing_qtl": 50.0, "min_price": 1500.0, "max_price": 9000.0},
         "maize": {"code": "maize", "max_listing_qtl": 50.0, "min_price": 1000.0, "max_price": 5000.0}}
FLOOR = {"modal_price": 3565.0, "afpp": 3430, "basis": "DISTRICT_FRESH", "price_date": "2026-11-12"}


class FakeDeps:
    provider = "sim"
    call_cap_s = 240

    def __init__(self, lang="kn", consented=True, registered=True, floor=FLOOR, live=()):
        self.t = 1000.0
        self.farmer = {"id": "f1", "lang": lang, "district_code": "KA-MANDYA", "consented": consented}
        self.registered, self.floor, self.live = registered, floor, set(live)
        self.committed, self.failures, self.consents, self.langs = [], 0, [], []

    def now(self): return self.t
    async def get_farmer(self, phone): return self.farmer if self.registered else None
    async def set_lang(self, fid, lang): self.langs.append(lang)
    async def record_consent(self, fid, sid, lang, digit): self.consents.append(digit)
    async def crop_menu(self, district, month): return ["ragi", "maize"]
    async def get_crop(self, code): return CROPS[code]
    async def has_live_listing(self, fid, crop): return crop in self.live
    async def has_any_live_listing(self, fid): return bool(self.live)
    async def get_floor(self, district, crop): return self.floor
    async def open_ticket(self, phone, fid, reason): return "07"
    async def record_failure(self, phone):
        self.failures += 1
        return self.failures

    async def commit_listing(self, s):
        if s["data"]["crop"] in self.live:
            raise ListingExists()
        self.committed.append(dict(s["data"]))
        return 4321


async def call(deps, s, kind, digits=""):
    a, s = await handle_event(deps, s, Event(kind=kind, digits=digits, call_id="c1", phone="+919800000001"))
    return a, s


async def walk(deps, keys, s=None):
    """Start a call, then feed `keys` (strings are digit entries, None is a timeout). Returns (actions, session)."""
    a, s = await call(deps, s, "start")
    out = [a]
    for k in keys:
        a, s = await call(deps, s, "timeout" if k is None else "digits", k or "")
        out.append(a)
    return out, s


async def test_happy_path_first_call():
    d = FakeDeps(lang=None, consented=False)
    acts, s = await walk(d, ["1", "1", "1", "17", "1", "3600", "1"])
    assert [a.state for a in acts] == ["LANG", "CONSENT", "CROP", "QTY", "QTY_CONFIRM", "PRICE", "FINAL", "DONE"]
    assert d.langs == ["kn"] and d.consents == ["1"]
    assert d.committed == [{**d.committed[0], "crop": "ragi", "qty": 17, "price": 3600, "guardrail": "NONE"}]
    done = acts[-1]
    assert done.hangup and done.clips[:2] == ["listed_ok", "your_number_is"] and done.clips[2:6] == ["d_4", "d_3", "d_2", "d_1"]


async def test_returning_farmer_skips_lang_and_consent():
    acts, _ = await walk(FakeDeps(), [])
    assert acts[0].state == "CROP"
    assert acts[0].clips == ["crop_menu_intro", "cropkey_ragi_1", "cropkey_maize_2", "helper_key_0"]


async def test_hindi_choice_sets_language():
    d = FakeDeps(lang=None, consented=True)
    acts, s = await walk(d, ["2"])
    assert s["lang"] == "hi" and acts[-1].lang == "hi" and d.langs == ["hi"]


async def test_consent_refused_ends_call():
    acts, s = await walk(FakeDeps(consented=False), ["2"])
    assert acts[-1].state == "BYE" and acts[-1].hangup and s["data"]["consented"] is False


async def test_unregistered_number_gets_helper_code():
    acts, s = await walk(FakeDeps(registered=False), [])
    a = acts[0]
    assert a.state == "NOT_REGISTERED" and a.hangup and a.clips[-2:] == ["d_0", "d_7"] and s["kind"] == "UNKNOWN_CALLER"


async def test_help_key_from_crop():
    acts, _ = await walk(FakeDeps(), ["0"])
    assert acts[-1].state == "HELP" and acts[-1].hangup and acts[-1].clips[-2:] == ["d_0", "d_7"]


async def test_price_prompt_speaks_mandi_and_fair_price_digit_by_digit():
    acts, _ = await walk(FakeDeps(), ["1", "17", "1"])
    p = acts[-1]
    assert p.state == "PRICE" and p.max_digits == 5 and p.finish_on_key == "#"
    assert p.clips == ["mandi_price_was", "d_3", "d_5", "d_6", "d_5", "rupees_per_qtl",
                       "fair_price_is", "d_3", "d_4", "d_3", "d_0", "rupees_per_qtl", "ask_price"]


async def test_no_floor_skips_guardrail_and_records_it():
    d = FakeDeps(floor=None)
    acts, _ = await walk(d, ["1", "17", "1", "1000"])                 # 1000 is under ragi min 1500
    assert acts[-1].state == "PRICE" and acts[-1].clips == ["bad_input", "no_price_today", "ask_price"]
    acts, _ = await walk(d, ["1", "17", "1", "2000", "1"])
    assert acts[-1].state == "DONE" and d.committed[-1]["guardrail"] == "NO_PRICE_DATA"


@pytest.mark.parametrize("guard_key,price,guardrail", [("1", 3430, "RAISED"), ("2", 3000, "KEPT_BELOW")])
async def test_guardrail_options(guard_key, price, guardrail):
    d = FakeDeps()
    acts, _ = await walk(d, ["1", "17", "1", "3000"])
    assert acts[-1].state == "GUARD" and acts[-1].clips[:5] == ["guard_warn", "d_3", "d_4", "d_3", "d_0"]
    acts, _ = await walk(d, ["1", "17", "1", "3000", guard_key, "1"])
    assert acts[-2].state == "FINAL" and acts[-1].state == "DONE"
    assert d.committed[-1]["price"] == price and d.committed[-1]["guardrail"] == guardrail


async def test_guard_threshold_is_97_percent_of_floor():
    d = FakeDeps()                                   # 3430 * 0.97 = 3327.1
    acts, _ = await walk(d, ["1", "17", "1", "3328"])
    assert acts[-1].state == "FINAL"
    acts, _ = await walk(d, ["1", "17", "1", "3327"])
    assert acts[-1].state == "GUARD"


async def test_guard_3_reenters_price():
    acts, _ = await walk(FakeDeps(), ["1", "17", "1", "3000", "3"])
    assert acts[-1].state == "PRICE"


async def test_qty_out_of_range_and_reenter():
    acts, _ = await walk(FakeDeps(), ["1", "51"])
    assert acts[-1].state == "QTY" and acts[-1].clips[0] == "bad_input"
    acts, _ = await walk(FakeDeps(), ["1", "0"])
    assert acts[-1].state == "QTY" and acts[-1].clips[0] == "bad_input"
    acts, _ = await walk(FakeDeps(), ["1", "17", "2"])      # 2 at QTY_CONFIRM = enter again
    assert acts[-1].state == "QTY"
    assert acts[-2].state == "QTY_CONFIRM" and acts[-2].clips == ["you_entered", "qty_17", "confirm_1_2"]


async def test_final_2_restarts_at_crop():
    acts, _ = await walk(FakeDeps(), ["1", "17", "1", "3600", "2"])
    assert acts[-1].state == "CROP"


async def test_only_explicit_1_commits():
    d = FakeDeps()
    await walk(d, ["1", "17", "1", "3600", "5", None, "9"])   # invalid key, timeout, invalid key -> BYE
    assert d.committed == []


async def test_three_failures_end_with_bye_and_count():
    d = FakeDeps()
    acts, _ = await walk(d, ["x", "x", "x"])                  # CROP: 3 invalid keys
    assert [a.state for a in acts[1:]] == ["CROP", "CROP", "BYE"] and acts[-1].hangup
    assert acts[1].clips[0] == "bad_input" and d.failures == 1


async def test_third_failed_call_opens_helper_ticket():
    d = FakeDeps()
    d.failures = 2                                            # two earlier failed calls today
    acts, s = await walk(d, ["x", "x", "x"])
    assert acts[-1].state == "HELP" and acts[-1].hangup and acts[-1].clips[-2:] == ["d_0", "d_7"]
    assert s["data"]["help_reason"] == "IVR_FAIL_3"


async def test_timeout_replays_without_bad_input_clip():
    acts, _ = await walk(FakeDeps(), [None])
    assert acts[-1].state == "CROP" and acts[-1].clips[0] == "crop_menu_intro"


async def test_retry_counter_resets_on_valid_input():
    acts, _ = await walk(FakeDeps(), ["x", "x", "1", "x", "x", "17"])
    assert acts[-1].state == "QTY_CONFIRM"


async def test_live_listing_blocks_same_crop_and_main_menu_offered():
    d = FakeDeps(live=["ragi"])
    acts, _ = await walk(d, ["1"])                            # MAIN -> 1 -> CROP
    assert acts[0].state == "MAIN" and acts[1].state == "CROP"
    acts, _ = await walk(d, ["1", "1"])                       # pick ragi again
    assert acts[-1].state == "MAIN" and acts[-1].clips[0] == "already_listed"


async def test_commit_conflict_is_reported_not_crashed():
    d = FakeDeps()
    acts, s = await walk(d, ["1", "17", "1", "3600"])
    d.live.add("ragi")                                        # someone listed it meanwhile
    a, s = await call(d, s, "digits", "1")
    assert a.state == "MAIN" and a.clips[0] == "already_listed"


async def test_events_after_terminal_hang_up_now():
    _, s = await walk(FakeDeps(), ["0"])                      # HELP
    a, _ = await call(FakeDeps(), s, "digits", "1")
    assert a.hangup_now


async def test_resume_after_drop():
    d = FakeDeps()
    _, s = await walk(d, ["1", "17"])                         # drop while at QTY_CONFIRM
    d.t += 120
    a, s = await call(d, s, "start")
    assert a.state == "QTY_CONFIRM" and a.clips[0] == "welcome_back" and s["data"]["qty"] == 17
    a, s = await call(d, s, "digits", "1")
    assert a.state == "PRICE"


async def test_no_resume_before_qty():
    d = FakeDeps()
    _, s = await walk(d, [])                                  # dropped at the CROP menu: nothing to resume
    a, s = await call(d, s, "start")
    assert a.state == "CROP" and a.clips[0] == "crop_menu_intro"


async def test_call_cap_240s_hangs_up_but_keeps_session():
    d = FakeDeps()
    _, s = await walk(d, ["1", "17"])
    d.t += 241
    a, s2 = await call(d, s, "digits", "1")
    assert a.hangup and a.clips == ["bye"] and s2["state"] == "QTY_CONFIRM"


async def test_multi_digit_prompts_use_hash_terminator():
    acts, _ = await walk(FakeDeps(), ["1"])
    assert (acts[-1].max_digits, acts[-1].finish_on_key) == (2, "#")


def test_debounce_rules():
    deb = Debouncer()
    assert not deb.is_bounce("3", 1000)
    assert deb.is_bounce("3", 1100)        # same digit within 120 ms
    assert not deb.is_bounce("3", 1250)    # a real double press 150 ms after the bounce
    assert deb.is_bounce("5", 1260)        # any digit within 40 ms
    assert not deb.is_bounce("5", 1400)
    d2 = Debouncer()
    assert not d2.is_bounce("0", 1000) and not d2.is_bounce("0", 1200)   # 3800: a human double 0 survives
