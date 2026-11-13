"""Telephony provider interface. Owner: Darshan.

A provider turns a queued call job into a real (or simulated) call to a farmer. Inbound adapters (missed calls,
digits) live in their own modules; this is only the outbound side used by services/jobs.py:

    async def place_call(phone: str, job: dict) -> bool
        job = {"id", "kind", "payload"}. Return True if the phone is being rung; the adapter later calls
        jobs.mark_in_call(job_id) when answered and jobs.on_call_end(job_id, answered) when the call is over.
        Return False if the call cannot be placed right now (the job is retried with backoff).

Selected by TELEPHONY_PROVIDER: "sim" (browser simulator) or "exotel" (D7).
"""
import importlib

from ..config import settings

_override = None


def set_provider(p) -> None:
    """Tests (and the Exotel spike) can replace the provider."""
    global _override
    _override = p


def get_provider():
    if _override is not None:
        return _override
    return importlib.import_module(f"{__package__}.{settings.provider}")
