"""
Fixtures pytest pour les tests de la scene Iron Man.

- Desactive la telemetrie (metriques ~/.lyra + sessions tracking
  dashboard): les tests ne doivent jamais ecrire de vraies metriques ni
  polluer le dashboard.
- Neutralise le poll hue_beat (2.5s par scene simulee sinon). La vraie
  implementation reste testable via REAL_WAIT_HUE_BEAT.
"""

import os

import pytest

os.environ.setdefault("IRONMAN_NO_TELEMETRY", "1")

from scenes.ironman.orchestrator import IronManOrchestrator  # noqa: E402

# Reference vers la vraie implementation, pour les tests dedies
REAL_WAIT_HUE_BEAT = IronManOrchestrator._wait_hue_beat


@pytest.fixture(autouse=True)
def fast_hue_beat_wait(monkeypatch):
    """Evite 2.5s de poll PID hue_beat dans chaque scene simulee."""
    monkeypatch.setattr(
        IronManOrchestrator, "_wait_hue_beat",
        lambda self, timeout=2.5: False,
    )
