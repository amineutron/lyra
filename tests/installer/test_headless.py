"""Installeur sans interface (roadmap #44)."""
import pytest

from installer.core.catalog import load_catalog
from installer.core.events import AskBroker, Output, StepChange
from installer.headless import main, make_emit, select_mcps


def test_question_recoit_sa_valeur_par_defaut():
    lines, ref = [], []
    emit = make_emit(lines.append, ref)
    ref.append(AskBroker(emit=emit, timeout=2))
    assert ref[0].ask("confirm", "Installer Ollama ?", default=True) is True
    assert ref[0].ask("input", "Hote ?", default="") == ""
    assert lines == ["[auto] Installer Ollama ? -> True", "[auto] Hote ? -> ''"]


def test_sortie_texte():
    lines = []
    emit = make_emit(lines.append, [None])
    emit(StepChange("venv", "err", detail="pip a echoue"))
    emit(Output("Collecting rich"))
    assert lines == ["[err] venv : pip a echoue", "    Collecting rich"]


def test_selection_des_mcps():
    catalog = load_catalog()
    assert select_mcps(catalog, "") == ()
    premier = catalog[0].id
    assert [m.id for m in select_mcps(catalog, f" {premier} ")] == [premier]
    with pytest.raises(SystemExit, match="inconnu"):
        select_mcps(catalog, "nexistepas")


def test_demo_de_bout_en_bout(tmp_path, capsys):
    assert main(["--demo", "--lyra-dir", str(tmp_path / "lyra")]) == 0
    out = capsys.readouterr().out
    assert "INSTALLATION OK" in out and "[ok] daemon" in out
