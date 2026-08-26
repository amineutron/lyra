"""Tests du pipeline declaratif (ordre, conditions, erreurs, events)."""
from pathlib import Path

import pytest

from installer.core.catalog import load_catalog
from installer.core.events import AskBroker, Output, Result, StepChange
from installer.core.osdetect import parse_os_release
from installer.core.pipeline import StepDef, build_pipeline, run_pipeline
from installer.core.state import InstallState

FEDORA = parse_os_release('ID=fedora\nPRETTY_NAME="Fedora 43"\n')


def _state(**kw):
    defaults = dict(distro=FEDORA, lyra_dir=Path("/tmp/lyra-test"), demo=True)
    defaults.update(kw)
    return InstallState(**defaults)


@pytest.fixture(scope="module")
def catalog():
    return load_catalog()


def _auto_broker(events):
    broker = AskBroker(lambda e: events.append(e), timeout=1)
    return broker


def test_ordre_des_etapes(catalog):
    selected = tuple(m for m in catalog if m.id in ("fedora", "hue"))
    steps = build_pipeline(_state(), selected)
    ids = [s.id for s in steps]
    assert ids[:2] == ["system", "clone"]
    assert ids[-3:] == ["config", "post", "daemon"]
    assert "mcp_fedora" in ids and "mcp_hue" in ids
    assert ids.index("mcp_fedora") < ids.index("config")


def test_tracking_non_installable_exclu(catalog):
    selected = tuple(m for m in catalog if m.id == "tracking")
    ids = [s.id for s in build_pipeline(_state(), selected)]
    assert "mcp_tracking" not in ids


def test_condition_skip_models(catalog):
    events = []
    state = _state(skip_models=True)
    ok = run_pipeline(state, (), lambda e: events.append(e),
                      _auto_broker(events))
    assert ok
    skipped = [e for e in events
               if isinstance(e, StepChange) and e.status == "skip"]
    assert any(e.step_id == "models" for e in skipped)


def test_demo_complet_emet_result_ok(catalog):
    events = []
    selected = tuple(m for m in catalog if m.installable)
    ok = run_pipeline(_state(), selected, lambda e: events.append(e),
                      _auto_broker(events))
    assert ok
    results = [e for e in events if isinstance(e, Result)]
    assert len(results) == 1 and results[0].ok
    assert any(isinstance(e, Output) for e in events)


def test_erreur_arret_propre():
    def boom(_ctx):
        raise RuntimeError("explosion")
    steps = (StepDef("a", "A", lambda _c: None),
             StepDef("b", "B", boom),
             StepDef("c", "C", lambda _c: None))
    events = []
    ok = run_pipeline(_state(demo=False), (), lambda e: events.append(e),
                      _auto_broker(events), pipeline=steps)
    assert not ok
    changes = [(e.step_id, e.status) for e in events
               if isinstance(e, StepChange)]
    assert ("b", "err") in changes
    assert not any(sid == "c" for sid, _ in changes)   # c jamais lance
    result = [e for e in events if isinstance(e, Result)][0]
    assert not result.ok and "explosion" in result.error


def test_etape_optionnelle_echoue_sans_avorter_le_pipeline():
    """Regression : un MCP mal configure (IP manquante, paquet casse...)
    ne doit pas empecher le reste de l'installation (Lyra elle-meme) de
    se terminer. L'echec est note dans state.incomplete_mcps pour le
    rappel au demarrage du client (voir config.py + repl.py)."""
    def boom(_ctx):
        raise RuntimeError("IP du bridge Hue manquante")
    steps = (StepDef("a", "A", lambda _c: None),
             StepDef("mcp_hue", "MCP hue-mcp", boom, optional=True),
             StepDef("c", "C", lambda _c: None))
    events = []
    state = _state(demo=False)
    ok = run_pipeline(state, (), lambda e: events.append(e),
                      _auto_broker(events), pipeline=steps)
    assert ok
    changes = [(e.step_id, e.status) for e in events
               if isinstance(e, StepChange)]
    assert ("mcp_hue", "err") in changes
    assert ("c", "run") in changes   # l'etape suivante a bien continue
    results = [e for e in events if isinstance(e, Result)]
    assert len(results) == 1 and results[0].ok
    assert state.incomplete_mcps == [
        {"id": "mcp_hue", "label": "MCP hue-mcp",
         "reason": "IP du bridge Hue manquante"}]


def test_broker_question_reponse():
    received = []
    broker = AskBroker(lambda e: received.append(e), timeout=5)

    import threading
    answers = []

    def worker():
        answers.append(broker.confirm("ok ?", default=False))

    t = threading.Thread(target=worker)
    t.start()
    while not received:
        pass
    assert broker.answer(received[0].ask_id, True)
    t.join(timeout=5)
    assert answers == [True]
    assert not broker.answer("ask-inconnu", 1)
