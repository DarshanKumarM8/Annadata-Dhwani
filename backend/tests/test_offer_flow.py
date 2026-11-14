"""D6 engine tests: the BID_OFFER states (OFFER, OFFER_CONFIRM, DONE_OFFER) against fake dependencies."""
from app.engine.actions import Event
from app.engine.engine import handle_event
from test_engine import FakeDeps

JOB = {"id": "j1", "kind": "BID_OFFER", "payload": {"bid_id": "b1", "listing_id": "l1"}}
OFFER = {"price": 3580.0, "qty": 17.0, "crop": "ragi", "ask": 3600.0, "farmer_id": "f1", "lang": "kn",
         "district_code": "KA-MANDYA"}


class OfferDeps(FakeDeps):
    def __init__(self, offer=OFFER, **kw):
        super().__init__(**kw)
        self.offer, self.answers = offer, []

    async def get_offer(self, bid_id, listing_id): return self.offer

    async def record_offer_response(self, bid_id, listing_id, response):
        self.answers.append((bid_id, listing_id, response))


async def start(deps):
    return await handle_event(deps, None, Event(kind="start", call_id="o1", phone="+919800000001", job=JOB))


async def key(deps, s, k):
    return await handle_event(deps, s, Event(kind="timeout" if k is None else "digits", digits=k or "", call_id="o1",
                                             phone="+919800000001"))


async def test_offer_reads_price_quantity_crop_and_own_ask():
    a, s = await start(OfferDeps())
    assert a.state == "OFFER" and s["kind"] == "BID_OFFER" and a.max_digits == 1
    assert a.clips == ["offer_intro", "d_3", "d_5", "d_8", "d_0", "rupees_per_qtl", "for_your", "qty_17", "crop_ragi",
                       "your_ask_was", "d_3", "d_6", "d_0", "d_0", "rupees_per_qtl", "offer_options"]


async def test_accept_needs_two_explicit_ones_and_records_once():
    d = OfferDeps()
    a, s = await start(d)
    a, s = await key(d, s, "1")
    assert a.state == "OFFER_CONFIRM" and d.answers == []                 # one key press binds nothing
    a, s = await key(d, s, "1")
    assert a.state == "DONE_OFFER" and a.hangup and a.clips == ["offer_done"]
    assert d.answers == [("b1", "l1", "ACCEPT")]


async def test_reject_is_recorded_and_says_crop_stays_listed():
    d = OfferDeps()
    a, s = await start(d)
    a, s = await key(d, s, "2")
    assert a.state == "BYE" and a.hangup and a.clips == ["offer_rejected"] and d.answers == [("b1", "l1", "REJECT")]


async def test_going_back_from_confirm_records_nothing_and_repeat_works():
    d = OfferDeps()
    a, s = await start(d)
    a, s = await key(d, s, "1")
    a, s = await key(d, s, "2")
    assert a.state == "OFFER" and d.answers == []
    a, s = await key(d, s, "9")
    assert a.state == "OFFER" and a.clips[0] == "offer_intro"


async def test_invalid_keys_never_record_and_three_misses_hang_up_without_helper_ticket():
    d = OfferDeps()
    a, s = await start(d)
    for k in ("5", None, "7"):
        a, s = await key(d, s, k)
    assert a.state == "BYE" and a.hangup and d.answers == [] and d.failures == 0
    assert s["data"]["failed_input"] is True


async def test_settled_or_already_answered_offer_hangs_up_immediately():
    a, s = await start(OfferDeps(offer=None))
    assert a.hangup_now and s is None


async def test_failed_store_does_not_claim_acceptance():
    class Broken(OfferDeps):
        async def record_offer_response(self, *a): raise RuntimeError("db down")
    d = Broken()
    a, s = await start(d)
    a, s = await key(d, s, "1")
    a, s = await key(d, s, "1")
    assert a.state == "BYE" and a.clips == ["bye"]                        # never plays "Accepted"


class LateDeps(OfferDeps):
    """The round settled while the farmer was on the call: the answer is not stored."""
    async def record_offer_response(self, bid_id, listing_id, response):
        self.answers.append((bid_id, listing_id, response))
        return False


async def test_a_late_accept_never_plays_accepted():
    d = LateDeps()
    a, s = await start(d)
    a, s = await key(d, s, "1")
    a, s = await key(d, s, "1")
    assert a.state == "BYE" and a.hangup and a.clips == ["offer_closed"]


async def test_a_late_reject_also_says_the_offer_closed():
    d = LateDeps()
    a, s = await start(d)
    a, s = await key(d, s, "2")
    assert a.state == "BYE" and a.clips == ["offer_closed"]
