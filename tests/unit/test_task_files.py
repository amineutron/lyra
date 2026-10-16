"""Fichiers des taches de fond : dossier prive 0700, plus /tmp lisible par tous."""
import stat

import pytest

from lyra.utils.task_files import task_dir, task_file


def test_dossier_d_execution_de_l_utilisateur(tmp_path):
    d = task_dir({"XDG_RUNTIME_DIR": str(tmp_path)})
    assert d == tmp_path / "lyra" / "tasks"
    assert stat.S_IMODE(d.stat().st_mode) == 0o700


def test_dossier_existant_trop_ouvert_resserre(tmp_path):
    d = tmp_path / "lyra" / "tasks"
    d.mkdir(parents=True, mode=0o755)
    d.chmod(0o755)
    task_dir({"XDG_RUNTIME_DIR": str(tmp_path)})
    assert stat.S_IMODE(d.stat().st_mode) == 0o700


def test_dossier_impose(tmp_path):
    assert task_dir({"LYRA_TASK_DIR": str(tmp_path / "t"), "XDG_RUNTIME_DIR": "/ailleurs"}) == tmp_path / "t"


def test_repli_sans_dossier_d_execution(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert task_dir({}) == tmp_path / ".lyra" / "tasks"


def test_chemin_d_un_fichier(tmp_path):
    p = task_file("task_20261016_001", "log", {"XDG_RUNTIME_DIR": str(tmp_path)})
    assert p == str(tmp_path / "lyra" / "tasks" / "lyra_task_task_20261016_001.log")
    assert not p.startswith("/tmp/lyra_task_")


@pytest.mark.parametrize("ident", ["", "../x", "a/b", ".cache"])
def test_identifiant_refuse(ident, tmp_path):
    with pytest.raises(ValueError):
        task_file(ident, "log", {"XDG_RUNTIME_DIR": str(tmp_path)})
