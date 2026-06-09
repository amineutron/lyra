"""Tests unitaires pour lyra/rules/ironman.py."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from lyra.rules.ironman import detect


def tool(q):
    r = detect(q)
    return r.tool if r else None


def confidence(q):
    r = detect(q)
    return r.confidence if r else 0.0


# ------------------------------------------------------------------ #
# Triggers exacts                                                     #
# ------------------------------------------------------------------ #

class TestExactTriggers:
    def test_je_suis_iron_man(self):
        assert tool("je suis iron man") == "ironman.run_scene"

    def test_je_suis_ironman(self):
        assert tool("je suis ironman") == "ironman.run_scene"

    def test_je_suis_tony_stark(self):
        assert tool("je suis tony stark") == "ironman.run_scene"

    def test_je_suis_tony(self):
        assert tool("je suis tony") == "ironman.run_scene"

    def test_mode_iron_man(self):
        assert tool("mode iron man") == "ironman.run_scene"

    def test_scene_iron_man(self):
        assert tool("scene iron man") == "ironman.run_scene"

    def test_lance_iron_man(self):
        assert tool("lance iron man") == "ironman.run_scene"

    def test_demarre_iron_man(self):
        assert tool("demarre iron man") == "ironman.run_scene"

    def test_active_iron_man(self):
        assert tool("active iron man") == "ironman.run_scene"

    def test_high_confidence(self):
        assert confidence("je suis iron man") >= 0.98

    def test_case_insensitive(self):
        assert tool("JE SUIS IRON MAN") == "ironman.run_scene"

    def test_with_accent(self):
        assert tool("je suis Iron Man") == "ironman.run_scene"


# ------------------------------------------------------------------ #
# Triggers flexibles                                                  #
# ------------------------------------------------------------------ #

class TestFlexibleTriggers:
    def test_lance_la_scene_iron_man(self):
        assert tool("lance la scene iron man") == "ironman.run_scene"

    def test_active_mode_iron(self):
        assert tool("active le mode iron man") == "ironman.run_scene"

    def test_execute_iron_man(self):
        assert tool("execute iron man") == "ironman.run_scene"

    def test_demarrer_iron_scene(self):
        assert tool("demarre la scene iron") == "ironman.run_scene"


# ------------------------------------------------------------------ #
# Pas de match                                                        #
# ------------------------------------------------------------------ #

class TestNoMatch:
    def test_iron_seul(self):
        # "iron" seul sans "man" -> pas de match
        assert tool("la touche iron est cassee") is None

    def test_tony_seul_sans_stark(self):
        # "tony" seul match (trigger exact "je suis tony")
        # mais "tony" dans un autre contexte ne devrait pas match
        assert tool("appelle tony") is None

    def test_vm_query(self):
        assert tool("demarre preprod-01") is None

    def test_empty(self):
        assert tool("") is None

    def test_parle_de_iron_man(self):
        # Mentionner iron man sans trigger -> pas de scene
        assert tool("c'est quoi iron man") is None
