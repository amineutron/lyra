"""Sudoers de l'installeur : durcissement post-audit (2026-08-26).

Regressions couvertes :
- glob NOPASSWD sur un dossier de $HOME (escalade root triviale) : les regles
  ne doivent citer que des chemins absolus, sans glob, sous la copie systeme
  root:root /usr/local/lib/lyra/scripts ;
- le fichier doit etre valide par `visudo -cf` AVANT d'etre installe ;
- (historique) 'sudo tee' sans timeout bloquait 700 s+ si le cache sudo
  n'etait pas amorce : tout passe par `sudo -n` + timeout -> RuntimeError.
"""
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from installer.core.steps.mcps import (
    SYSTEM_SCRIPTS_DIR, _install_system_scripts, _write_sudoers,
    build_sudoers_rules, sudoers_targets,
)


class _FakeBroker:
    def __init__(self, answer=True):
        self.answer = answer

    def confirm(self, prompt, default=True):
        return self.answer


class _FakeCtx:
    def __init__(self, answer=True):
        self.broker = _FakeBroker(answer)
        self.events = []
        self.step_id = "mcp_fedora"

    def emit(self, event):
        self.events.append(event)


@pytest.fixture
def scripts_tree(tmp_path):
    """Arborescence minimale a l'image de fedora-agents/scripts."""
    for sub, names in {
        "agents/vm-controller": ["common.sh", "vm-start.sh", "vm-stop.sh"],
        "agents/backup-manager": ["common.sh", "backup-create.sh"],
        "kvm": ["kvm-clone.sh", "_fix-grub-vm.sh"],
        "backup": ["borg-backup.sh"],
        "utils": ["tracking.sh"],
    }.items():
        d = tmp_path / sub
        d.mkdir(parents=True)
        for n in names:
            (d / n).write_text("#!/bin/bash\n")
    (tmp_path / "config.env.example").write_text("X=1\n")
    return tmp_path


# --- logique pure -----------------------------------------------------------

def test_cibles_sudoers_uniquement_scripts_d_entree(scripts_tree):
    targets = sudoers_targets(scripts_tree)
    names = [t.name for t in targets]
    assert names == ["vm-start.sh", "vm-stop.sh", "backup-create.sh", "kvm-clone.sh"]  # ordre SUDOERS_SUBDIRS
    assert all(str(t).startswith(str(SYSTEM_SCRIPTS_DIR)) for t in targets), \
        "les regles doivent viser la copie systeme, jamais la source dans $HOME"
    assert "common.sh" not in names and "_fix-grub-vm.sh" not in names
    assert "borg-backup.sh" not in names, "backup/ n'est pas un dossier d'entree sudoers"


def test_regles_sans_glob_ni_home(scripts_tree):
    rules = build_sudoers_rules("alice", sudoers_targets(scripts_tree))
    body = [l for l in rules.splitlines() if l and not l.startswith("#")]
    assert len(body) == 4 + 3  # scripts + virsh, virt-clone, qemu-img
    for line in body:
        assert line.startswith("alice ALL=(ALL) NOPASSWD: /")
        path = line.split("NOPASSWD: ")[1]
        assert not set("*?[]") & set(path), f"glob interdit : {line}"
        assert not path.startswith("/home/"), f"chemin sous /home interdit : {line}"


@pytest.mark.parametrize("bad", [
    Path("/usr/local/lib/lyra/scripts/kvm/*.sh"),       # glob (l'ancien bug)
    Path("relative/vm-start.sh"),                        # pas absolu
    Path("/usr/local/lib/lyra/scripts/kvm/a b.sh"),      # espace = regle ambigue
])
def test_regle_refusee(bad):
    with pytest.raises(ValueError):
        build_sudoers_rules("alice", [bad])


# --- ecriture (sudo mocke) ---------------------------------------------------

def _ok(*a, **k):
    return MagicMock(returncode=0, stdout="", stderr="")


def test_visudo_valide_avant_installation(scripts_tree):
    ctx = _FakeCtx()
    with patch("subprocess.run", side_effect=_ok) as mock_run, \
         patch("installer.core.steps.mcps.getpass.getuser", return_value="alice"):
        _write_sudoers(ctx, sudoers_targets(scripts_tree))
    cmds = [c.args[0] for c in mock_run.call_args_list]
    assert all(c[:2] == ["sudo", "-n"] for c in cmds), "toujours sudo -n (pas de prompt bloquant)"
    visudo = [c for c in cmds if c[2] == "visudo"]
    install = [c for c in cmds if c[2] == "install"]
    assert visudo and install
    assert cmds.index(visudo[0]) < cmds.index(install[0]), "visudo -cf doit preceder l'installation"
    assert visudo[0][3] == "-cf"
    assert install[0][-1] == "/etc/sudoers.d/lyra" and "0440" in install[0]


def test_visudo_invalide_n_installe_rien(scripts_tree):
    ctx = _FakeCtx()

    def fake(cmd, **kw):
        if cmd[2] == "visudo":
            return MagicMock(returncode=1, stdout="", stderr=">>> syntax error")
        return _ok()

    with patch("subprocess.run", side_effect=fake) as mock_run:
        with pytest.raises(RuntimeError, match="NON installe"):
            _write_sudoers(ctx, sudoers_targets(scripts_tree))
    assert not any(c.args[0][2] == "install" for c in mock_run.call_args_list)


def test_refus_utilisateur_n_ecrit_rien(scripts_tree):
    with patch("subprocess.run") as mock_run:
        _write_sudoers(_FakeCtx(answer=False), sudoers_targets(scripts_tree))
    assert not mock_run.called


def test_timeout_leve_erreur_claire_au_lieu_de_bloquer(scripts_tree):
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("sudo", 30)):
        with pytest.raises(RuntimeError, match="cache expire"):
            _write_sudoers(_FakeCtx(), sudoers_targets(scripts_tree))


def test_copie_systeme_root_et_modes(scripts_tree):
    ctx = _FakeCtx()
    with patch("subprocess.run", side_effect=_ok) as mock_run:
        targets = _install_system_scripts(ctx, scripts_tree)
    cmds = [c.args[0] for c in mock_run.call_args_list]
    assert all(c[:3] == ["sudo", "-n", "install"] for c in cmds)
    assert all("root" in c for c in cmds), "tout est installe en root:root"
    files = [c for c in cmds if "-d" not in c]
    sh = [c for c in files if c[-2].endswith(".sh")]
    other = [c for c in files if not c[-2].endswith(".sh")]
    assert sh and all("0755" in c for c in sh)
    assert other and all("0644" in c for c in other)
    assert all(c[-1].startswith(str(SYSTEM_SCRIPTS_DIR)) for c in files)
    assert len(targets) == 4


def test_source_absente_erreur_explicite(tmp_path):
    with pytest.raises(RuntimeError, match="introuvables"):
        _install_system_scripts(_FakeCtx(), tmp_path / "nope")
