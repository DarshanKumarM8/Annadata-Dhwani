"""Telephony provider interface. Owner: Darshan.

A provider turns a queued call job into a real (or simulated) call to a farmer. Inbound adapters (missed calls,
digits) live in their own modules; this is only the outbound side used by services/jobs.py:

    async def place_call(phone: str, job: dict) -> bool
        job = {"id", "kind", "payload"}. Return True if the phone is being rung; the adapter later calls
        jobs.mark_in_call(job_id) when answered and jobs.on_call_end(job_id, answered) when the call is over.
        Return False if the call cannot be placed right now (the job is retried with backoff).

Selected per phone by provider_for(): a farmer whose browser simulator phone is connected is rung there; every other
number goes to the provider named by TELEPHONY_PROVIDER ("sim" = nobody else can be rung, "exotel" = the real network).
"""
import importlib

from ..config import settings

_override = None


def set_provider(p) -> None:
    """Tests (and the Exotel spike) can replace the provider."""
    global _override
    _override = p


def get_provider(phone: str | None = None):
    if _override is not None:
        return _override
    sim = importlib.import_module(f"{__package__}.sim")
    if settings.provider == "sim" or (phone is not None and phone in sim.LINES):
        return sim
    return importlib.import_module(f"{__package__}.{settings.provider}")
