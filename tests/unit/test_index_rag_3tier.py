"""Extraction des paraphrases pour l'index 3-tier (regression 2026-09-17).

`extract_use_cases` utilisait la classe `[^E]+?` pour s'arreter avant
"Exemples:" ; elle ne pouvait donc pas traverser un E majuscule. Toute
paraphrase contenant "LEDs" ou "TV" faisait echouer l'extraction entiere :
38 outils sur 88 n'avaient aucune paraphrase dans l'index, dont
tv.ambilight_off ("eteindre les LEDs"), jamais remonte pour "eteins l'ambilight".
"""

import sys
from pathlib import Path

import pytest

pytest.importorskip("chromadb")
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from index_rag_3tier import extract_use_cases  # noqa: E402

DOC_AMBILIGHT = ("tv.ambilight_off (TV) Signature: ambilight_off() Desactive l'Ambilight de la TV "
                 "Utilise pour: désactiver l'ambilight. éteindre les LEDs. éteins l'ambilight Catégorie: tv_ambilight")


def test_paraphrase_avec_majuscule_conservee():
    r = extract_use_cases(DOC_AMBILIGHT)
    assert "éteindre les LEDs" in r and "éteins l'ambilight" in r


def test_s_arrete_avant_la_categorie_et_les_exemples():
    assert "Catégorie" not in extract_use_cases(DOC_AMBILIGHT)
    doc = "x Utilise pour: allumer la TV. Exemples: allume la télé Catégorie: tv"
    assert extract_use_cases(doc) == "allumer la TV."


def test_sans_section():
    assert extract_use_cases("x Signature: f() rien") == ""


def test_docs_sans_serveur_ecartes(capsys):
    from index_rag_3tier import filtrer_sans_serveur
    ids, metas, docs = filtrer_sans_serveur(
        ["a", "b"], [{"server_name": "fedora"}, {"category": "scene"}], ["d1", "d2"])
    assert ids == ["a"] and metas == [{"server_name": "fedora"}] and docs == ["d1"]
    assert "1 doc(s) sans server_name" in capsys.readouterr().out
