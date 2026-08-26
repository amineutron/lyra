"""Regression : 'sudo dnf install' et 'sudo tee /etc/sudoers.d/lyra'
tournent dans un thread arriere-plan pendant que Rich Live occupe le
terminal -- sudo n'a alors aucun moyen interactif de lire un mot de passe
(observe : timeout ~300s sur les paquets systeme, hang indefini sur
l'ecriture sudoers). ensure_sudo_cached() amorce `sudo -v` AVANT que Live
ne demarre, pendant que le terminal est encore normal."""
from unittest.mock import MagicMock, patch

from installer.core.sudoprime import ensure_sudo_cached


def test_mode_demo_ne_touche_jamais_a_sudo():
    with patch("subprocess.run") as mock_run:
        assert ensure_sudo_cached(demo=True) is True
    assert not mock_run.called


def test_deja_passwordless_ne_demande_rien():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        assert ensure_sudo_cached(demo=False) is True
    # Un seul appel : le check -n -v silencieux, pas de second prompt
    assert mock_run.call_count == 1
    assert mock_run.call_args[0][0] == ["sudo", "-n", "-v"]


def test_prompt_interactif_si_pas_de_cache():
    responses = [MagicMock(returncode=1), MagicMock(returncode=0)]
    with patch("subprocess.run", side_effect=responses) as mock_run:
        assert ensure_sudo_cached(demo=False) is True
    assert mock_run.call_count == 2
    assert mock_run.call_args_list[0][0][0] == ["sudo", "-n", "-v"]
    assert mock_run.call_args_list[1][0][0] == ["sudo", "-v"]


def test_echec_mot_de_passe_renvoie_false():
    responses = [MagicMock(returncode=1), MagicMock(returncode=1)]
    with patch("subprocess.run", side_effect=responses):
        assert ensure_sudo_cached(demo=False) is False
