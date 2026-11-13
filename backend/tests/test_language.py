"""The language menu offers Kannada, Hindi and English, and every choice is saved (needs the db/003 migration on old databases)."""
import pytest

from test_reliability import STACK_UP, ev, fetch, stack  # noqa: F401  (stack is a fixture)

pytestmark = pytest.mark.skipif(not STACK_UP, reason="docker compose stack (Postgres + Valkey) is not running")


@pytest.mark.parametrize("key,lang", [("1", "kn"), ("2", "hi"), ("3", "en")])
async def test_each_language_choice_is_saved_and_spoken_in_that_language(stack, key, lang):
    deps, phone = stack
    await fetch("UPDATE farmers SET lang = NULL, consent_at = NULL, consent_version = NULL WHERE phone = $1", phone)
    first = await ev(deps, phone, "start")
    assert first.state == "LANG" and first.clips == ["welcome", "kn:lang_option", "hi:lang_option", "en:lang_option"]
    nxt = await ev(deps, phone, "digits", key)
    assert nxt.state == "CONSENT" and nxt.lang == lang                       # the next prompt is in the chosen language
    assert (await fetch("SELECT lang FROM farmers WHERE phone = $1", phone))[0]["lang"] == lang


async def test_an_unknown_language_key_is_refused(stack):
    deps, phone = stack
    await fetch("UPDATE farmers SET lang = NULL, consent_at = NULL, consent_version = NULL WHERE phone = $1", phone)
    await ev(deps, phone, "start")
    again = await ev(deps, phone, "digits", "4")
    assert again.state == "LANG" and again.clips[0] == "bad_input"
