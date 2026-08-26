"""Regression : run_ollama doit installer le client 'ollama' meme en mode
--ollama-host distant. Avant le fix, un retour anticipe sautait cette
installation et 'ollama pull' echouait ensuite avec
FileNotFoundError('ollama') sur une machine sans le binaire local."""
from pathlib import Path
from unittest.mock import patch

from installer.core.events import Output
from installer.core.osdetect import parse_os_release
from installer.core.pipeline import StepContext
from installer.core.state import InstallState
from installer.core.steps import ollama

FEDORA = parse_os_release('ID=fedora\nPRETTY_NAME="Fedora 43"\n')


class _FakeBroker:
    def __init__(self, answer=True):
        self.answer = answer
        self.prompts = []

    def confirm(self, prompt, default=True):
        self.prompts.append(prompt)
        return self.answer


def _ctx(host, broker):
    events = []
    state = InstallState(distro=FEDORA, lyra_dir=Path("/tmp/lyra-test"),
                         ollama_host=host)
    ctx = StepContext(state=state, emit=events.append, broker=broker,
                      mcps=(), step_id="ollama")
    return ctx, events


def test_remote_host_installe_le_client_si_absent():
    broker = _FakeBroker(answer=True)
    ctx, _events = _ctx("192.168.122.1", broker)

    with patch("installer.core.steps.ollama.shutil.which", return_value=None), \
         patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = ""
        mock_run.return_value.stderr = ""
        ollama.run_ollama(ctx)

    assert mock_run.called, "le script d'installation du client aurait du etre lance"
    assert broker.prompts, "une confirmation d'installation aurait du etre demandee"


def test_remote_host_skip_install_si_deja_present():
    broker = _FakeBroker(answer=True)
    ctx, events = _ctx("192.168.122.1", broker)

    with patch("installer.core.steps.ollama.shutil.which",
              return_value="/usr/bin/ollama"), \
         patch("subprocess.run") as mock_run:
        ollama.run_ollama(ctx)

    assert not mock_run.called
    assert not broker.prompts
    outputs = [e.line for e in events if isinstance(e, Output)]
    assert any("Ollama distant" in line for line in outputs)


def test_local_sans_host_installe_et_active_service():
    broker = _FakeBroker(answer=True)
    ctx, _events = _ctx("", broker)

    with patch("installer.core.steps.ollama.shutil.which", return_value=None), \
         patch("subprocess.run") as mock_run, \
         patch("installer.core.steps.ollama.run") as mock_systemctl:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = ""
        mock_run.return_value.stderr = ""
        ollama.run_ollama(ctx)

    assert mock_run.called
    assert mock_systemctl.called
