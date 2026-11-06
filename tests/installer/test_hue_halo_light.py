"""Hue : l'installeur installe halo-light et apparie le bridge en https (le http est redirige)."""
import json
import stat
from types import SimpleNamespace

import pytest

from installer.core.catalog import load_catalog, resolve_placeholders
from installer.core.steps import mcps


@pytest.fixture(scope="module")
def hue():
    return next(m for m in load_catalog() if m.id == "hue")


def test_catalogue_pointe_sur_halo_light(hue):
    assert hue.name == "halo-light"
    assert hue.repo == "git@github.com:amineutron/halo-light.git"
    assert hue.dest.endswith("/mcp-servers/halo-light")


def test_serveur_est_un_executable_absolu_du_venv(hue):
    """modules/mcp.py n'accepte un binaire que sous forme de chemin absolu."""
    server = resolve_placeholders(hue.server, {"lyra": "/opt/lyra", "dest": "/x", "bridge_ip": "192.0.2.7"})
    assert server["command"] == "/opt/lyra/.venv/bin/halo-light"
    assert server["command"].startswith("/")
    assert server["args"] == ["serve"]
    assert server["env"] == {"HUE_BRIDGE_IP": "192.0.2.7"}


def test_verification_sur_le_port_https(hue):
    assert hue.check == {"type": "tcp", "host": "{bridge_ip}", "port": 443}


def test_url_de_pairing_en_https():
    assert mcps.pairing_url("192.0.2.7") == "https://192.0.2.7/api"


# --------------------------------------------------------- config halo-light


def test_config_halo_light_ecrite_en_0600(tmp_path):
    path = mcps.write_halo_light_config("192.0.2.7", "USER", "CK", environ={"XDG_CONFIG_HOME": str(tmp_path)})
    assert path == tmp_path / "halo-light" / "config.json"
    assert json.loads(path.read_text()) == {
        "bridge_ip": "192.0.2.7", "app_key": "USER", "beat": {"username": "USER", "clientkey": "CK"},
    }
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700


def test_config_halo_light_fusionne_sans_ecraser_la_zone(tmp_path):
    env = {"XDG_CONFIG_HOME": str(tmp_path)}
    path = tmp_path / "halo-light" / "config.json"
    path.parent.mkdir(mode=0o700)
    path.write_text(json.dumps({"beat": {"area_id": "AREA"}, "ca_cert": "/x.pem"}))
    mcps.write_halo_light_config("192.0.2.7", "USER", "CK", environ=env)
    data = json.loads(path.read_text())
    assert data["beat"] == {"area_id": "AREA", "username": "USER", "clientkey": "CK"}
    assert data["ca_cert"] == "/x.pem"


def test_config_halo_light_suit_halo_light_config(tmp_path):
    target = tmp_path / "ailleurs" / "c.json"
    path = mcps.write_halo_light_config("192.0.2.7", "U", "C", environ={"HALO_LIGHT_CONFIG": str(target)})
    assert path == target and target.exists()


# ------------------------------------------------------------------- pairing


class _Broker:
    def confirm(self, *_args, **_kwargs):
        return True


def _ctx():
    state = SimpleNamespace(device_config={"hue": {"bridge_ip": "192.0.2.7"}}, secrets={})
    return SimpleNamespace(state=state, broker=_Broker(), emit=lambda *_a, **_k: None, step_id="hue")


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_pairing_utilise_https_sans_verifier_le_certificat_prive(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return _Response([{"success": {"username": "USER", "clientkey": "CK"}}])

    monkeypatch.setattr(mcps.requests, "post", fake_post)
    ctx = _ctx()
    mcps._hue_pairing(ctx, SimpleNamespace(id="hue"))

    url, kwargs = calls[0]
    assert url == "https://192.0.2.7/api"
    assert kwargs["verify"] is False
    assert kwargs["json"]["generateclientkey"] is True
    assert ctx.state.secrets["hue"] == {"username": "USER", "clientkey": "CK"}
    written = json.loads((tmp_path / "halo-light" / "config.json").read_text())
    assert written["app_key"] == "USER" and written["bridge_ip"] == "192.0.2.7"
