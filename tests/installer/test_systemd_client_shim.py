"""Regression : l'executable ~/.local/bin/lyra et l'alias .bashrc plantaient
avec 'No module named lyra.client' quand lances depuis un repertoire autre
que le clone Lyra -- 'python -m lyra.client' resout le paquet via
sys.path[0] = cwd de l'appelant, jamais garanti egal au clone. Le fix fixe
PYTHONPATH explicitement, independamment du cwd de l'appelant."""
from pathlib import Path
from unittest.mock import patch

import pytest

from installer.core.events import AskBroker
from installer.core.osdetect import parse_os_release
from installer.core.pipeline import StepContext
from installer.core.state import InstallState
from installer.core.steps import systemd

FEDORA = parse_os_release('ID=fedora\nPRETTY_NAME="Fedora 43"\n')
REAL_TEMPLATE = Path(
    "/home/amineutron/dev/lyra/install/lyra-daemon.service").read_text()


@pytest.fixture
def lyra_dir(tmp_path):
    root = tmp_path / "lyra"
    (root / "install").mkdir(parents=True)
    (root / "install" / "lyra-daemon.service").write_text(REAL_TEMPLATE)
    return root


def _ctx(lyra_dir):
    state = InstallState(distro=FEDORA, lyra_dir=lyra_dir)
    return StepContext(state=state, emit=lambda e: None,
                       broker=AskBroker(lambda e: None, timeout=1),
                       mcps=(), step_id="daemon")


def test_shim_fixe_pythonpath_independamment_du_cwd(lyra_dir, tmp_path):
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    with patch("installer.core.steps.systemd.Path.home", return_value=fake_home), \
         patch("installer.core.steps.systemd.run"):
        systemd.run_step(_ctx(lyra_dir))

    shim = fake_home / ".local" / "bin" / "lyra"
    assert shim.exists()
    content = shim.read_text()
    assert f'PYTHONPATH="{lyra_dir}"' in content
    assert "-m lyra.client" in content


def test_alias_bashrc_fixe_pythonpath_aussi(lyra_dir, tmp_path):
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    with patch("installer.core.steps.systemd.Path.home", return_value=fake_home), \
         patch("installer.core.steps.systemd.run"):
        systemd.run_step(_ctx(lyra_dir))

    bashrc = (fake_home / ".bashrc").read_text()
    assert "alias lyra=" in bashrc
    assert f'PYTHONPATH="{lyra_dir}"' in bashrc
