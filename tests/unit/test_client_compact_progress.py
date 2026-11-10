"""Sortie non-verbose compacte du REPL client (M1)."""
import pytest

from lyra.client.render import compact_progress_line, render_progress


@pytest.mark.parametrize("message,attendu", [
    ({"step": "rule_matched", "data": {"server": "TV", "tool_short": "power on"}},
     "TV: power on"),
    ({"step": "rule_matched", "data": {"server": "HUE", "tool": "hue.turn_off"}},
     "HUE: turn_off"),
    ({"step": "before_llm", "data": {"tool": "fedora.vm_start", "score": 0.9}},
     "EPHAISTOS analyse vm start..."),
    ({"step": "acknowledgement", "data": {"message": "Je regarde"}}, "Je regarde"),
    ({"step": "acknowledgement", "data": {}}, None),
    ({"step": "registry_done", "data": {"server": "FEDORA", "score": 0.9}}, None),
    ({"step": "capabilities_done", "data": {"tool": "x"}}, None),
])
def test_ligne_compacte(message, attendu):
    assert compact_progress_line(message) == attendu


def test_compact_n_affiche_aucun_score(capsys):
    render_progress({"step": "before_llm", "data": {"tool": "a.b", "score": 0.91}},
                    verbose=False, compact=True)
    sortie = capsys.readouterr().out
    assert "EPHAISTOS analyse b" in sortie and "0.91" not in sortie


def test_silencieux_par_defaut(capsys):
    render_progress({"step": "rule_matched", "data": {"server": "TV", "tool": "t.x"}})
    assert capsys.readouterr().out == ""


def test_verbose_garde_le_detail(capsys):
    render_progress({"step": "before_llm",
                     "data": {"tool": "a.b", "score": 0.91, "confidence_level": "high"}},
                    verbose=True, compact=True)
    assert "score=0.91" in capsys.readouterr().out
