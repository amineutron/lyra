"""lyra/utils/hf_local.py : cache local d'abord, reseau seulement si le modele manque (lyra#25)."""
import pytest

from lyra.utils.hf_local import charger_local_puis_reseau, hors_ligne_force


class _Chargeur:
    def __init__(self, en_cache: bool):
        self.en_cache = en_cache
        self.appels: list[bool] = []

    def __call__(self, local_files_only: bool):
        self.appels.append(local_files_only)
        if local_files_only and not self.en_cache:
            raise OSError("absent du cache")
        return "modele"


@pytest.fixture(autouse=True)
def _env_propre(monkeypatch):
    monkeypatch.delenv("LYRA_OFFLINE", raising=False)
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)


def test_en_cache_aucun_appel_reseau():
    c = _Chargeur(en_cache=True)
    assert charger_local_puis_reseau(c, "m") == "modele"
    assert c.appels == [True]


def test_absent_du_cache_telecharge_une_fois():
    c = _Chargeur(en_cache=False)
    assert charger_local_puis_reseau(c, "m") == "modele"
    assert c.appels == [True, False]


@pytest.mark.parametrize("var", ["LYRA_OFFLINE", "HF_HUB_OFFLINE"])
def test_hors_ligne_force_ne_telecharge_pas(monkeypatch, var):
    monkeypatch.setenv(var, "1")
    c = _Chargeur(en_cache=False)
    with pytest.raises(RuntimeError, match="hors ligne"):
        charger_local_puis_reseau(c, "m")
    assert c.appels == [True]


@pytest.mark.parametrize("valeur, attendu", [("1", True), ("true", True), ("oui", True), ("0", False), ("", False)])
def test_hors_ligne_force_valeurs(monkeypatch, valeur, attendu):
    monkeypatch.setenv("LYRA_OFFLINE", valeur)
    assert hors_ligne_force() is attendu
