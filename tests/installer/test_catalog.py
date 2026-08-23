"""Tests du catalogue declaratif des MCPs."""
import re

import pytest

from installer.core.catalog import (CatalogError, load_catalog,
                                    resolve_placeholders)


@pytest.fixture(scope="module")
def catalog():
    return load_catalog()


def test_chargement_et_ids_uniques(catalog):
    ids = [m.id for m in catalog]
    assert len(ids) == len(set(ids))
    assert {"fedora", "hue", "tv", "denon", "catt", "tracking"} <= set(ids)


def test_repos_ssh_marouabah(catalog):
    for m in catalog:
        if m.repo:
            assert m.repo.startswith("git@github.com:marouabah/"), m.id


def test_aucune_ip_en_dur(catalog):
    ip_re = re.compile(r"192\.168\.\d+\.\d+")
    for m in catalog:
        blob = repr((m.long_desc, m.notes, m.config, m.server, m.check,
                     m.fields, m.examples))
        # 127.0.0.1 (tracking local) est legitime ; les IP LAN non.
        assert not ip_re.search(blob), f"IP en dur dans '{m.id}'"


def test_exemples_vocaux_presents(catalog):
    for m in catalog:
        assert len(m.examples) >= 4, f"'{m.id}' : exemples vocaux manquants"


def test_champs_secrets_coherents(catalog):
    tv = next(m for m in catalog if m.id == "tv")
    secrets = {f.key for f in tv.fields if f.secret}
    assert secrets == {"user", "pass"}
    # Les cles secretes doivent rester null dans le bloc config
    assert tv.config["tv"]["user"] is None
    assert tv.config["tv"]["pass"] is None


def test_installable(catalog):
    tracking = next(m for m in catalog if m.id == "tracking")
    assert not tracking.installable
    assert sum(1 for m in catalog if m.installable) == 5


def test_resolve_placeholders_strict():
    assert resolve_placeholders({"a": "{x}/b"}, {"x": "1"}) == {"a": "1/b"}
    with pytest.raises(KeyError):
        resolve_placeholders("{manquant}", {})


def test_catalogue_invalide(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("mcps:\n  - id: a\n    name: a\n    short_desc: x\n"
                   "    long_desc: y\n    runtime: cobol\n")
    with pytest.raises(CatalogError):
        load_catalog(bad)
