"""Regression : l'ecriture de /etc/sudoers.d/lyra ('sudo tee') n'avait
aucun timeout -- si le cache sudo n'etait pas amorce (voir sudoprime.py),
ca bloquait indefiniment dans le thread du pipeline (observe : 700s+ sans
sortir). 'sudo -n' echoue immediatement plutot que d'attendre un mot de
passe qu'il ne peut pas lire ; le timeout(30) reste en filet de securite."""
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from installer.core.steps.mcps import _write_sudoers


class _FakeBroker:
    def confirm(self, prompt, default=True):
        return True


class _FakeCtx:
    def __init__(self):
        self.broker = _FakeBroker()
        self.events = []
        self.step_id = "mcp_fedora"

    def emit(self, event):
        self.events.append(event)


def test_sudo_non_interactif_utilise_flag_n():
    ctx = _FakeCtx()
    with patch("subprocess.run") as mock_run, \
         patch("installer.core.steps.mcps.run") as mock_chmod:
        mock_run.return_value = MagicMock(returncode=0)
        _write_sudoers(ctx)
    cmd = mock_run.call_args[0][0]
    assert cmd[:2] == ["sudo", "-n"], \
        "sudo doit echouer immediatement (pas de prompt bloquant), pas attendre"
    assert mock_chmod.called


def test_timeout_leve_erreur_claire_au_lieu_de_bloquer():
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("sudo", 30)):
        with pytest.raises(RuntimeError, match="cache expire"):
            _write_sudoers(_FakeCtx())
