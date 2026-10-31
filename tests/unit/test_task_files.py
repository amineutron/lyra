"""Fichiers des taches de fond : dossier prive 0700, plus /tmp lisible par tous."""
import stat

import pytest

from lyra.utils.task_files import task_dir, task_file, task_file_read


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


# --- controle du dossier (proprietaire, lien symbolique, mode) ---

def test_dossier_lien_symbolique_refuse(tmp_path):
    reel = tmp_path / "reel"
    reel.mkdir(mode=0o700)
    lien = tmp_path / "lien"
    lien.symlink_to(reel)
    with pytest.raises(PermissionError):
        task_dir({"LYRA_TASK_DIR": str(lien)})


def test_dossier_d_un_autre_proprietaire_refuse(tmp_path, monkeypatch):
    d = tmp_path / "t"
    d.mkdir(mode=0o700)
    monkeypatch.setattr("lyra.utils.task_files.os.geteuid", lambda: d.stat().st_uid + 1)
    with pytest.raises(PermissionError):
        task_dir({"LYRA_TASK_DIR": str(d)})


def test_pas_de_chmod_inutile(tmp_path, monkeypatch):
    env = {"LYRA_TASK_DIR": str(tmp_path / "t")}
    task_dir(env)
    appels = []
    monkeypatch.setattr("lyra.utils.task_files.os.chmod", lambda *a, **k: appels.append(a))
    task_dir(env)
    task_dir(env)
    assert appels == []


# --- repli de lecture sur l'ancien emplacement /tmp ---

def test_lecture_repli_sur_le_dossier_du_pid_file_enregistre(tmp_path):
    ancien = tmp_path / "ancien"
    ancien.mkdir()
    (ancien / "lyra_task_t1.done").write_text("0")
    pid_file = str(ancien / "lyra_task_t1.pid")
    env = {"LYRA_TASK_DIR": str(tmp_path / "neuf")}
    assert task_file_read("t1", "done", pid_file=pid_file, env=env) == str(ancien / "lyra_task_t1.done")


def test_lecture_repli_legacy_tmp(tmp_path):
    legacy = tmp_path / "tmp"
    legacy.mkdir()
    (legacy / "lyra_task_t2.log").write_text("x")
    env = {"LYRA_TASK_DIR": str(tmp_path / "neuf")}
    assert task_file_read("t2", "log", env=env, legacy_dir=legacy) == str(legacy / "lyra_task_t2.log")


def test_lecture_prefere_le_nouvel_emplacement_et_ne_cree_rien(tmp_path):
    neuf = tmp_path / "neuf"
    env = {"LYRA_TASK_DIR": str(neuf)}
    p = task_file_read("t3", "log", env=env, legacy_dir=tmp_path / "vide")
    assert p == str(neuf / "lyra_task_t3.log")
    assert not neuf.exists()  # la lecture ne cree jamais le dossier


def test_lecture_legacy_ignore_lien_symbolique(tmp_path):
    legacy = tmp_path / "tmp"
    legacy.mkdir()
    cible = tmp_path / "secret"
    cible.write_text("0")
    (legacy / "lyra_task_t4.done").symlink_to(cible)
    env = {"LYRA_TASK_DIR": str(tmp_path / "neuf")}
    assert task_file_read("t4", "done", env=env, legacy_dir=legacy) == str(tmp_path / "neuf" / "lyra_task_t4.done")
