"""Jugement de la campagne one-shot : un cas « aucune action attendue » (logique pure)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from test_campaign_oneshot import FAIL, PASS, eval_result  # noqa: E402


def test_rien_propose_passe():
    assert eval_result(None, {}, [], None, {}, {}) == PASS


def test_outil_en_attente_d_argument_vaut_clarification():
    """"cree un snapshot" -> vm_snapshot avec vm_name en attente : le pipeline demande la VM."""
    assert eval_result("fedora.vm_snapshot", {}, ["vm_name"], None, {}, {}) == PASS


def test_outil_propose_sans_attente_echoue():
    """Un outil pret a s'executer la ou rien n'etait attendu reste un echec."""
    assert eval_result("fedora.vm_snapshot", {"vm_name": "preprod-01"}, [], None, {}, {}) == FAIL
