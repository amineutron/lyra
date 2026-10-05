"""Alerte ntfy quand le smoke MCP echoue (scripts/smoke_alert.py).

Regression du 2026-09-30 : le serveur hue est reste mort 2 jours, le smoke
l'affichait en [FAIL] dans le journal mais personne n'etait prevenu.
"""
import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "smoke_alert", Path(__file__).resolve().parents[2] / "scripts" / "smoke_alert.py")
smoke_alert = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(smoke_alert)

SORTIE_KO = [
    "[OK]   fedora    19 outils | init 0.26s | tools/list 0.01s",
    "[FAIL] hue      stdout ferme (le serveur a probablement crashe)",
    "[OK]   denon     10 outils | init 0.56s | tools/list 0.0s",
    "",
    "Serveurs KO: hue",
]


def test_echec_liste_les_serveurs_ko():
    alerte = smoke_alert.build_alert(SORTIE_KO)
    assert alerte is not None
    assert "hue" in alerte["title"]
    assert "stdout ferme" in alerte["message"]
    assert "fedora" not in alerte["message"]
    assert alerte["priority"] == 4


def test_plusieurs_serveurs_ko():
    lignes = ["[FAIL] hue      crash", "[FAIL] catt     timeout", "Serveurs KO: hue, catt"]
    alerte = smoke_alert.build_alert(lignes)
    assert "hue, catt" in alerte["title"]
    assert alerte["message"].count("\n") == 1


def test_echec_sans_ligne_fail_reste_signale():
    # Crash du script lui-meme (traceback) : on alerte quand meme, avec la fin du log.
    lignes = ["Traceback (most recent call last):", "ModuleNotFoundError: No module named 'yaml'"]
    alerte = smoke_alert.build_alert(lignes)
    assert alerte is not None
    assert "ModuleNotFoundError" in alerte["message"]


@pytest.mark.parametrize("lignes", [[], ["", "  "]])
def test_journal_vide(lignes):
    alerte = smoke_alert.build_alert(lignes)
    assert alerte is not None
    assert alerte["message"]


def test_message_borne():
    lignes = [f"[FAIL] srv{i}   " + "x" * 500 for i in range(40)]
    assert len(smoke_alert.build_alert(lignes)["message"]) <= smoke_alert.MAX_MESSAGE


def test_sans_ntfy_url_pas_d_envoi(monkeypatch):
    monkeypatch.delenv("NTFY_URL", raising=False)
    envois = []
    monkeypatch.setattr(smoke_alert, "publish", lambda *a, **k: envois.append(a))
    monkeypatch.setattr(smoke_alert, "read_journal", lambda: SORTIE_KO)
    assert smoke_alert.main() == 0
    assert envois == []
