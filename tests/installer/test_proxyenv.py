"""Proxy et miroirs d'entreprise dans l'installeur (roadmap #44)."""
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from installer.core import runner
from installer.core.osdetect import parse_os_release
from installer.core.pipeline import StepContext
from installer.core.proxyenv import (
    has_proxy,
    network_env,
    no_proxy_with_loopback,
    ollama_proxy_dropin,
    proxy_display,
    redact,
    with_preserved_env,
)
from installer.core.state import InstallState
from installer.core.steps import ollama

PROXY = {"HTTPS_PROXY": "http://proxy.corp:3128", "no_proxy": "intranet.corp",
         "PIP_INDEX_URL": "https://pypi.corp/simple", "HF_ENDPOINT": "https://hf.corp", "HOME": "/home/x"}


def test_variables_reseau_retenues():
    assert list(network_env(PROXY)) == ["HTTPS_PROXY", "no_proxy", "PIP_INDEX_URL", "HF_ENDPOINT"]
    assert network_env({"HTTP_PROXY": "  ", "HOME": "/h"}) == {}


@pytest.mark.parametrize("env,attendu", [
    ({}, False), ({"NO_PROXY": "x"}, False), ({"https_proxy": "http://p:1"}, True), ({"ALL_PROXY": "socks5://p"}, True),
])
def test_has_proxy(env, attendu):
    assert has_proxy(env) is attendu


def test_regression_sudo_garde_le_proxy():
    # sudo remet l'environnement a zero : 'sudo dnf install' partait sans proxy
    cmd = with_preserved_env(["sudo", "dnf", "install", "-y", "git"], PROXY)
    assert cmd == ["sudo", "--preserve-env=HTTPS_PROXY,no_proxy,PIP_INDEX_URL,HF_ENDPOINT",
                   "dnf", "install", "-y", "git"]


@pytest.mark.parametrize("cmd,env", [
    (["sudo", "dnf", "install"], {}),                      # pas de proxy : inchange
    (["pip", "install", "x"], PROXY),                      # pas sudo : herite deja
    (["sudo", "-E", "apt-get", "install"], PROXY),         # deja preserve
    (["sudo", "--preserve-env=HTTP_PROXY", "true"], PROXY),
])
def test_commande_inchangee(cmd, env):
    assert with_preserved_env(cmd, env) == cmd


def test_runner_applique_la_preservation():
    captured = {}

    class FakeProc:
        stdout = iter(())
        returncode = 0

        def wait(self):
            return 0

    def fake_popen(cmd, **kw):
        captured["cmd"] = cmd
        return FakeProc()

    with patch.dict(os.environ, {"HTTPS_PROXY": "http://proxy.corp:3128"}, clear=True), \
         patch("installer.core.runner.subprocess.Popen", side_effect=fake_popen):
        runner.run(["sudo", "apt-get", "install", "-y", "curl"], lambda e: None)
    assert captured["cmd"][:2] == ["sudo", "--preserve-env=HTTPS_PROXY"]


@pytest.mark.parametrize("valeur,attendu", [
    ("", "localhost,127.0.0.1,::1"),
    ("intranet.corp, localhost", "intranet.corp,localhost,127.0.0.1,::1"),
    ("localhost,127.0.0.1,::1", "localhost,127.0.0.1,::1"),
])
def test_no_proxy_boucle_locale(valeur, attendu):
    assert no_proxy_with_loopback(valeur) == attendu


def test_dropin_ollama():
    assert ollama_proxy_dropin({"PIP_INDEX_URL": "https://pypi.corp"}) is None
    assert ollama_proxy_dropin(PROXY) == (
        "[Service]\n"
        'Environment="HTTPS_PROXY=http://proxy.corp:3128"\n'
        'Environment="NO_PROXY=intranet.corp,localhost,127.0.0.1,::1"\n'
    )


@pytest.mark.parametrize("url,attendu", [
    ("http://alice:s3cret@proxy.corp:3128", "http://alice:***@proxy.corp:3128"),
    ("http://proxy.corp:3128", "http://proxy.corp:3128"),
    ("", ""),
])
def test_mot_de_passe_masque(url, attendu):
    assert redact(url) == attendu


def test_affichage_proxy_sans_secret():
    assert proxy_display({"http_proxy": "http://bob:pw@p:8080"}) == "http://bob:***@p:8080"


class _Broker:
    def confirm(self, prompt, default=True):
        return True


def _ctx():
    state = InstallState(distro=parse_os_release("ID=fedora\n"), lyra_dir=Path("/tmp/lyra-test"), ollama_host="")
    return StepContext(state=state, emit=lambda e: None, broker=_Broker(), mcps=(), step_id="ollama")


def test_service_ollama_recoit_le_proxy():
    with patch.dict(os.environ, {"HTTPS_PROXY": "http://proxy.corp:3128"}, clear=True), \
         patch("installer.core.steps.ollama.shutil.which", return_value="/usr/bin/ollama"), \
         patch("subprocess.run") as tee, \
         patch("installer.core.steps.ollama.run") as run:
        tee.return_value.returncode = 0
        ollama.run_ollama(_ctx())
    assert tee.call_args.args[0] == ["sudo", "-n", "tee", ollama.OLLAMA_DROPIN]
    assert 'HTTPS_PROXY=http://proxy.corp:3128' in tee.call_args.kwargs["input"]
    commandes = [c.args[0] for c in run.call_args_list]
    assert ["sudo", "systemctl", "daemon-reload"] in commandes
    assert commandes[-1] == ["sudo", "systemctl", "enable", "--now", "ollama"]


def test_sans_proxy_pas_de_dropin():
    with patch.dict(os.environ, {}, clear=True), \
         patch("installer.core.steps.ollama.shutil.which", return_value="/usr/bin/ollama"), \
         patch("subprocess.run") as tee, \
         patch("installer.core.steps.ollama.run") as run:
        ollama.run_ollama(_ctx())
    assert not tee.called
    assert [c.args[0] for c in run.call_args_list] == [["sudo", "systemctl", "enable", "--now", "ollama"]]
