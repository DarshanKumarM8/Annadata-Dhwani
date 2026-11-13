"""Tests must not depend on a developer's personal .env: pin the settings that change behaviour."""
import pytest

from app.config import settings


@pytest.fixture(autouse=True, scope="session")
def _standard_rules():
    saved = (settings.verify_radius_m, settings.team_phones)
    object.__setattr__(settings, "verify_radius_m", 500)          # the real rule, even if .env has a rehearsal radius
    yield
    object.__setattr__(settings, "verify_radius_m", saved[0])
