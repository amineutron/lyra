"""Tests generation config.yaml/secrets.yaml — jamais de secret dans config."""
from pathlib import Path

import pytest
import yaml

from installer.core.catalog import load_catalog
from installer.core.configpatch import (assert_no_secrets, backup_if_exists,
                                        build_config, build_secrets)

EXAMPLE = Path("/home/amineutron/dev/lyra/config.yaml.example").read_text()
MAPPING = {"lyra": "/opt/lyra", "home": "/home/test"}


@pytest.fixture(scope="module")
def catalog():
    return load_catalog()


def _selected(catalog, *ids):
    return tuple(m for m in catalog if m.id in ids)


def test_injection_mcp_servers(catalog):
    mcps = _selected(catalog, "tv", "denon")
    device = {"tv": {"host": "10.0.0.5", "user": "u", "pass": "p", "mac": ""},
              "denon": {"host": "10.0.0.6"}}
    config = build_config(EXAMPLE, mcps, device, MAPPING)

    servers = config["mcp"]["servers"]
    assert servers["tv"]["args"] == ["/opt/lyra/mcp-servers/pylips-mcp/server.py"]
    assert servers["denon"]["timeout"] == 10
    assert config["tv"]["host"] == "10.0.0.5"
    assert config["denon"]["host"] == "10.0.0.6"


def test_aucun_secret_dans_config(catalog):
    mcps = _selected(catalog, "tv")
    device = {"tv": {"host": "10.0.0.5", "user": "moi", "pass": "hyper-secret",
                     "mac": ""}}
    config = build_config(EXAMPLE, mcps, device, MAPPING)
    assert_no_secrets(config, mcps)   # ne doit pas lever
    assert "hyper-secret" not in yaml.safe_dump(config)
    assert config["tv"]["user"] is None
    assert config["tv"]["pass"] is None


def test_secrets_vont_dans_secrets_yaml(catalog):
    mcps = _selected(catalog, "tv")
    device = {"tv": {"host": "10.0.0.5", "user": "moi", "pass": "s3cret", "mac": ""}}
    secrets = build_secrets("", mcps, device,
                            {"hue": {"username": "hueuser", "clientkey": "ck"}})
    assert secrets["tv"] == {"user": "moi", "pass": "s3cret"}
    assert secrets["hue"]["clientkey"] == "ck"


def test_secrets_existants_preserves(catalog):
    existing = "discord:\n  webhook_url: garde\n"
    secrets = build_secrets(existing, (), {}, {"hue": {"username": "x"}})
    assert secrets["discord"]["webhook_url"] == "garde"


def test_idempotence(catalog):
    mcps = _selected(catalog, "denon")
    device = {"denon": {"host": "10.0.0.6"}}
    once = build_config(EXAMPLE, mcps, device, MAPPING)
    twice = build_config(yaml.safe_dump(once), mcps, device, MAPPING)
    assert once["denon"] == twice["denon"]
    assert once["mcp"]["servers"]["denon"] == twice["mcp"]["servers"]["denon"]


def test_ollama_host(catalog):
    config = build_config(EXAMPLE, (), {}, MAPPING, ollama_host="192.168.122.1")
    assert config["llm"]["base_url"] == "http://192.168.122.1:11434"


def test_placeholder_manquant_leve(catalog):
    mcps = _selected(catalog, "denon")
    with pytest.raises(KeyError):
        build_config(EXAMPLE, mcps, {"denon": {}}, MAPPING)


def test_backup(tmp_path):
    assert backup_if_exists(tmp_path / "absent.yaml") is None
    target = tmp_path / "config.yaml"
    target.write_text("a: 1\n")
    backup = backup_if_exists(target)
    assert backup is not None and backup.exists()
    assert backup.read_text() == "a: 1\n"
