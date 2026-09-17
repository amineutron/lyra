"""Resolution du nom d'outil renvoye par EPHAISTOS (regression issue #20).

Deux defauts se cumulaient :

1. Le post-traitement ne lisait que la cle `name` des metadonnees. L'index v2
   l'emploie, mais le RAG 3-tier -- celui du mode enhanced, qui est le mode par
   defaut de run.sh -- ecrit `tool_name`. Le prefixe serveur n'etait donc
   jamais complete en usage reel.
2. Un nom qu'aucune spec ne portait traversait quand meme. EPHAISTOS renvoyant
   parfois "stop_cast" au lieu de "cast_stop", ou simplement le premier mot de
   la requete ("baisse"), Lyra proposait "Je vais executer . Tu confirmes ?"
   avec un nom vide.
"""

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from lyra.core.pipeline import _noms_outils_disponibles, _resoudre_nom_outil  # noqa: E402


@dataclass
class _FusedResult:
    document: str
    metadata: dict


def _spec_v2(nom: str) -> _FusedResult:
    """Spec telle que l'index v2 la renvoie : la cle est `name`."""
    return _FusedResult(document=f"spec for {nom}",
                        metadata={"name": nom, "server_name": nom.split(".")[0],
                                  "description": ""})


def _spec_3tier(nom: str) -> _FusedResult:
    """Spec telle que le RAG 3-tier la renvoie : la cle est `tool_name`."""
    return _FusedResult(document=f"spec for {nom}",
                        metadata={"tool_name": nom, "server_name": nom.split(".")[0],
                                  "capabilities": ""})


class TestNomsDisponibles:
    def test_lit_la_cle_name(self):
        assert _noms_outils_disponibles([_spec_v2("fedora.vm_stop")]) == ["fedora.vm_stop"]

    def test_lit_aussi_la_cle_tool_name(self):
        """Le coeur du bug : le mode par defaut n'etait pas lu du tout."""
        assert _noms_outils_disponibles([_spec_3tier("catt.cast_stop")]) == ["catt.cast_stop"]

    def test_melange_des_deux_formats(self):
        noms = _noms_outils_disponibles([_spec_v2("fedora.vm_stop"), _spec_3tier("catt.cast_stop")])
        assert noms == ["fedora.vm_stop", "catt.cast_stop"]

    def test_liste_vide_ou_none(self):
        assert _noms_outils_disponibles([]) == []
        assert _noms_outils_disponibles(None) == []

    def test_dictionnaires_bruts(self):
        """Le 3-tier peut renvoyer des dicts plutot que des objets."""
        assert _noms_outils_disponibles(
            [{"metadata": {"tool_name": "hue.turn_on_light"}}]) == ["hue.turn_on_light"]


class TestResolution:
    def test_nom_court_prefixe_depuis_l_index_v2(self):
        fused = [_spec_v2("fedora.vm_clone")]
        assert _resoudre_nom_outil("vm_clone", fused) == "fedora.vm_clone"

    def test_nom_court_prefixe_depuis_le_3tier(self):
        """Ce cas echouait : la cle tool_name n'etait jamais lue."""
        fused = [_spec_3tier("catt.cast_stop")]
        assert _resoudre_nom_outil("cast_stop", fused) == "catt.cast_stop"

    def test_nom_complet_conserve(self):
        fused = [_spec_3tier("catt.cast_stop")]
        assert _resoudre_nom_outil("catt.cast_stop", fused) == "catt.cast_stop"

    def test_nom_invente_refuse(self):
        """"stop_cast" (mots inverses) ne correspond a aucun outil reel."""
        fused = [_spec_3tier("catt.cast_stop"), _spec_3tier("catt.cast_resume")]
        assert _resoudre_nom_outil("stop_cast", fused) is None

    def test_premier_mot_de_la_requete_refuse(self):
        """EPHAISTOS renvoyait "baisse" pour "baisse le volume de la diffusion"."""
        fused = [_spec_3tier("denon.volume_down")]
        assert _resoudre_nom_outil("baisse", fused) is None

    def test_tool_vide(self):
        assert _resoudre_nom_outil("", [_spec_3tier("catt.cast_stop")]) is None
        assert _resoudre_nom_outil(None, []) is None

    def test_sans_candidats_on_ne_conclut_pas(self):
        """Sans specs exploitables (RAG mocke), on ne peut rien affirmer.

        Rejeter ici cassait quatre tests d'integration : le pipeline recoit
        parfois des specs precalculees, et `fused` ne reflete alors rien.
        """
        assert _resoudre_nom_outil("vm_start", []) is None
        assert _noms_outils_disponibles([]) == []

    def test_ne_confond_pas_un_suffixe_partiel(self):
        """"stop" ne doit pas resoudre vers "catt.cast_stop"."""
        fused = [_spec_3tier("catt.cast_stop")]
        assert _resoudre_nom_outil("stop", fused) is None


class TestContratNoMatch:
    """Le rejet repose sur une propriete derivee : on verrouille le contrat.

    Premiere tentative de correctif : `analysis.no_match = True`, qui levait
    `AttributeError: property 'no_match' has no setter` et faisait tomber le
    pipeline en pleine requete. C'est en annulant l'outil qu'on signifie
    l'absence de correspondance.
    """

    def _analyse(self, tool):
        from lyra.models._analysis import EphaistosAnalysis
        return EphaistosAnalysis(tool=tool, arguments={}, missing_args=[],
                                 confidence=0.9, reasoning="", raw_response="")

    def test_outil_absent_vaut_no_match(self):
        assert self._analyse(None).no_match is True

    def test_outil_present_ne_vaut_pas_no_match(self):
        assert self._analyse("catt.cast_stop").no_match is False

    def test_no_match_reste_en_lecture_seule(self):
        import pytest
        analyse = self._analyse("catt.cast_stop")
        with pytest.raises(AttributeError):
            analyse.no_match = True
