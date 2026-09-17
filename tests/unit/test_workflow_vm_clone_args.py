"""Le workflow vm_clone doit conserver les arguments deja extraits (regression lyra#21).

"clone preprod-01 en test-clone et demarre" : la regle extrait start=True, le
workflow le garde dans la pending action (depuis 2026-08-15) mais le
tool_call rendu au moment de la question COW ne contenait que source_vm et
new_vm_name. La campagne one-shot le comptait PARTIAL, et un client qui lit
tool_call perdait le demarrage demande.
"""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from lyra.core.workflows import vm_clone as wf
from lyra.models.ephaistos import EphaistosAnalysis


@pytest.fixture
def ctx(monkeypatch):
    monkeypatch.setattr(wf, "get_existing_vm_names", lambda hestia: ["preprod-01", "sandbox-02"])
    monkeypatch.setattr(wf, "get_vm_state", lambda hestia, vm: {"running": False})
    session = Mock()
    session.get_pending_action.return_value = None
    return SimpleNamespace(hestia=Mock(), session=session,
                           prepare_execution=lambda analysis, query: SimpleNamespace(
                               tool_call={"name": analysis.tool, "arguments": analysis.arguments}))


def _analyse(**args):
    return EphaistosAnalysis(tool="fedora.vm_clone", arguments=args, missing_args=[],
                             confidence=0.95, reasoning="rule: clone SOURCE en DEST", raw_response="")


def test_start_conserve_dans_le_tool_call_a_la_question_cow(ctx):
    r = wf.handle_vm_clone_workflow("clone preprod-01 en test-clone et demarre",
                                    _analyse(source_vm="preprod-01", new_vm_name="test-clone", start=True), ctx)
    assert r.pending_args == ["_linked_choice"]
    assert r.tool_call["arguments"] == {"source_vm": "preprod-01", "new_vm_name": "test-clone", "start": True}


def test_start_conserve_quand_la_source_tourne(ctx, monkeypatch):
    monkeypatch.setattr(wf, "get_vm_state", lambda hestia, vm: {"running": True})
    r = wf.handle_vm_clone_workflow("clone preprod-01 en test-clone et demarre",
                                    _analyse(source_vm="preprod-01", new_vm_name="test-clone", start=True), ctx)
    assert r.tool_call["arguments"]["start"] is True


def test_sans_start_rien_n_est_ajoute(ctx):
    r = wf.handle_vm_clone_workflow("clone preprod-01 en test-clone",
                                    _analyse(source_vm="preprod-01", new_vm_name="test-clone"), ctx)
    assert r.tool_call["arguments"] == {"source_vm": "preprod-01", "new_vm_name": "test-clone"}
