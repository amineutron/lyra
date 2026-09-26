"""Boucle locale hors proxy pour Lyra (roadmap #44)."""
import pytest

from lyra.utils.netenv import a_un_proxy, no_proxy_complete, proteger_services_locaux


@pytest.mark.parametrize("env,attendu", [
    ({}, None),                                                     # pas de proxy : on ne touche a rien
    ({"NO_PROXY": "x"}, None),
    ({"HTTPS_PROXY": "http://p:3128"}, "localhost,127.0.0.1,::1"),
    ({"http_proxy": "http://p:3128", "no_proxy": "corp.lan"}, "corp.lan,localhost,127.0.0.1,::1"),
    ({"HTTP_PROXY": "http://p", "NO_PROXY": "localhost,127.0.0.1,::1"}, None),
])
def test_no_proxy_complete(env, attendu):
    assert no_proxy_complete(env) == attendu


def test_regression_ollama_local_hors_proxy():
    # HTTP_PROXY seul envoyait les appels a 127.0.0.1:11434 vers le proxy d'entreprise
    env = {"HTTP_PROXY": "http://proxy.corp:3128"}
    proteger_services_locaux(env)
    assert env["NO_PROXY"] == env["no_proxy"] == "localhost,127.0.0.1,::1"


def test_httpx_contourne_le_proxy_pour_la_boucle(monkeypatch):
    httpx = pytest.importorskip("httpx")
    # fonction interne de httpx (celle que Client(trust_env=True) utilise) : si elle
    # change de place, on saute plutot que de tester autre chose
    get_environment_proxies = getattr(pytest.importorskip("httpx._utils"), "get_environment_proxies", None)
    if get_environment_proxies is None:
        pytest.skip("httpx._utils.get_environment_proxies absent de cette version")

    monkeypatch.setenv("HTTP_PROXY", "http://proxy.corp:3128")
    monkeypatch.delenv("NO_PROXY", raising=False)
    monkeypatch.delenv("no_proxy", raising=False)
    import os
    proteger_services_locaux(os.environ)
    mounts = get_environment_proxies()
    assert mounts.get("all://127.0.0.1") is None and "all://127.0.0.1" in mounts
    assert httpx is not None


def test_a_un_proxy():
    assert a_un_proxy({"all_proxy": "socks5://p"}) and not a_un_proxy({"PIP_INDEX_URL": "x"})
