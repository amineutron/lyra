"""Tests unitaires pour les helpers de disambiguation (pipeline.py)."""

import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from lyra.core.pipeline import _extract_disambiguation_candidates, _build_disambiguation_question


# ---------------------------------------------------------------------------
# Stub FusedResult pour eviter les imports lourds
# ---------------------------------------------------------------------------

@dataclass
class _FusedResult:
    document: str
    metadata: dict


def _make_result(name: str, server: str = "", description: str = "") -> _FusedResult:
    srv = server or (name.split(".")[0] if "." in name else "unknown")
    return _FusedResult(
        document=f"spec for {name}",
        metadata={"name": name, "server_name": srv, "description": description},
    )


# ---------------------------------------------------------------------------
# Tests _extract_disambiguation_candidates
# ---------------------------------------------------------------------------

class TestExtractCandidates:
    def test_deux_serveurs_differents(self):
        fused = [
            _make_result("screen-manager.open_app", "screen-manager", "Ouvrir une app sur un ecran"),
            _make_result("fedora.vm_start", "fedora", "Demarrer une VM"),
        ]
        candidates = _extract_disambiguation_candidates(fused)
        assert len(candidates) == 2
        servers = {c["server"] for c in candidates}
        assert servers == {"screen-manager", "fedora"}

    def test_un_seul_serveur_un_seul_candidat(self):
        fused = [
            _make_result("fedora.vm_start", "fedora"),
            _make_result("fedora.vm_stop", "fedora"),
        ]
        candidates = _extract_disambiguation_candidates(fused)
        assert len(candidates) == 1
        assert candidates[0]["server"] == "fedora"

    def test_max_4_candidats(self):
        fused = [
            _make_result("a.tool1", "a"),
            _make_result("b.tool2", "b"),
            _make_result("c.tool3", "c"),
            _make_result("d.tool4", "d"),
            _make_result("e.tool5", "e"),
        ]
        candidates = _extract_disambiguation_candidates(fused)
        assert len(candidates) <= 4

    def test_description_tronquee(self):
        long_desc = "A" * 100
        fused = [_make_result("srv.tool", "srv", long_desc)]
        candidates = _extract_disambiguation_candidates(fused)
        assert len(candidates[0]["description"]) <= 70

    def test_metadata_vide(self):
        result = _FusedResult(document="doc", metadata={})
        candidates = _extract_disambiguation_candidates([result])
        # Pas de name => ignore
        assert len(candidates) == 0

    def test_nom_sans_point(self):
        """Tool sans prefixe serveur."""
        result = _FusedResult(document="doc", metadata={"name": "my_tool", "server_name": "mysrv"})
        candidates = _extract_disambiguation_candidates([result])
        assert len(candidates) == 1
        assert candidates[0]["server"] == "mysrv"

    def test_server_deduit_du_nom(self):
        """server_name absent: deduit du name."""
        result = _FusedResult(document="doc", metadata={"name": "hue.turn_on"})
        candidates = _extract_disambiguation_candidates([result])
        assert candidates[0]["server"] == "hue"


# ---------------------------------------------------------------------------
# Tests _build_disambiguation_question
# ---------------------------------------------------------------------------

class TestBuildDisambiguationQuestion:
    def _make_candidates(self) -> list[dict]:
        return [
            {"tool": "screen-manager.open_app", "server": "screen-manager",
             "description": "Ouvrir une application sur un ecran"},
            {"tool": "fedora.vm_start", "server": "fedora",
             "description": "Demarrer une machine virtuelle"},
        ]

    def test_contient_les_deux_outils(self):
        q = _build_disambiguation_question(self._make_candidates())
        assert "open_app" in q
        assert "vm_start" in q

    def test_contient_les_serveurs(self):
        q = _build_disambiguation_question(self._make_candidates())
        assert "screen-manager" in q
        assert "fedora" in q

    def test_contient_les_numeros(self):
        q = _build_disambiguation_question(self._make_candidates())
        assert "1." in q
        assert "2." in q

    def test_contient_option_annuler(self):
        q = _build_disambiguation_question(self._make_candidates())
        assert "n" in q
        assert "annuler" in q.lower()

    def test_options_format_1_2_n(self):
        q = _build_disambiguation_question(self._make_candidates())
        assert "[1/2/n]" in q

    def test_quatre_candidats(self):
        candidates = [
            {"tool": f"srv{i}.tool{i}", "server": f"srv{i}", "description": f"Desc {i}"}
            for i in range(1, 5)
        ]
        q = _build_disambiguation_question(candidates)
        assert "[1/2/3/4/n]" in q
        assert "4." in q

    def test_description_incluse(self):
        q = _build_disambiguation_question(self._make_candidates())
        assert "Ouvrir" in q
        assert "Demarrer" in q
