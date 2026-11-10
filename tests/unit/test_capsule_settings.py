"""Tests des reglages capsule.* (mascotte, sons) : defauts, invalides, bornes."""

import json
from pathlib import Path

import pytest

from lyra.core.capsule_settings import (
    CAPSULE_KEYS,
    DEFAULT_MASCOT,
    DEFAULT_SOUNDS_PACK,
    DEFAULT_SOUNDS_VOLUME,
    MASCOT_NAMES,
    SOUND_EVENT_IDS,
    CapsuleSettings,
    capsule_settings,
    event_key,
    validate_capsule_value,
)
from lyra.core.settings import ALLOWED_KEYS, UserSettings
from lyra.core.settings_menu import SettingsMenu

REPO = Path(__file__).resolve().parents[2]


def make_settings(tmp_path) -> UserSettings:
    return UserSettings(path=tmp_path / "settings.json")


def test_catalogue_mascottes_synchro_avec_installeur():
    catalogue = json.loads((REPO / "installer/assets/mascots.json").read_text())
    names = [m["n"] for group in catalogue.values() for m in group]
    assert sorted(MASCOT_NAMES) == sorted(names)
    assert len(MASCOT_NAMES) == 30


def test_cles_exposees_dans_allowed_keys():
    assert CAPSULE_KEYS <= ALLOWED_KEYS
    assert len(SOUND_EVENT_IDS) == 12
    assert all(event_key(e) in ALLOWED_KEYS for e in SOUND_EVENT_IDS)


def test_defauts_sans_reglages():
    cfg = capsule_settings(None)
    assert isinstance(cfg, CapsuleSettings)
    assert cfg.mascot == DEFAULT_MASCOT == "random"
    assert cfg.sounds_enabled is True
    assert cfg.sounds_volume == DEFAULT_SOUNDS_VOLUME == 0.35
    assert cfg.sounds_pack == DEFAULT_SOUNDS_PACK == "soft"
    assert cfg.sounds_events["thinking"] is False
    assert all(v for k, v in cfg.sounds_events.items() if k != "thinking")
    assert set(cfg.sounds_events) == set(SOUND_EVENT_IDS)


def test_dataclass_gelee():
    cfg = capsule_settings({})
    with pytest.raises(AttributeError):
        cfg.mascot = "owl"
    with pytest.raises(TypeError):
        cfg.sounds_events["ask"] = False


@pytest.mark.parametrize(("data", "field", "expected"), [
    ({"capsule": {"mascot": "owl"}}, "mascot", "owl"),
    ({"capsule": {"mascot": "ascii"}}, "mascot", "ascii"),
    ({"capsule": {"mascot": "dragon"}}, "mascot", "random"),       # inconnu
    ({"capsule": {"mascot": 3}}, "mascot", "random"),              # mauvais type
    ({"capsule": {"mascot": None}}, "mascot", "random"),
    ({"capsule": "oops"}, "mascot", "random"),                     # section corrompue
    ({"capsule": {"sounds": {"enabled": False}}}, "sounds_enabled", False),
    ({"capsule": {"sounds": {"enabled": "false"}}}, "sounds_enabled", True),
    ({"capsule": {"sounds": {"enabled": 0}}}, "sounds_enabled", True),
    ({"capsule": {"sounds": {"volume": 0.0}}}, "sounds_volume", 0.0),
    ({"capsule": {"sounds": {"volume": 1}}}, "sounds_volume", 1.0),
    ({"capsule": {"sounds": {"volume": 0.8}}}, "sounds_volume", 0.8),
    ({"capsule": {"sounds": {"volume": 1.01}}}, "sounds_volume", 0.35),
    ({"capsule": {"sounds": {"volume": -0.1}}}, "sounds_volume", 0.35),
    ({"capsule": {"sounds": {"volume": True}}}, "sounds_volume", 0.35),
    ({"capsule": {"sounds": {"volume": "0.5"}}}, "sounds_volume", 0.35),
    ({"capsule": {"sounds": {"volume": float("nan")}}}, "sounds_volume", 0.35),
    ({"capsule": {"sounds": {"pack": "retro"}}}, "sounds_pack", "retro"),
    ({"capsule": {"sounds": {"pack": "crystal"}}}, "sounds_pack", "crystal"),
    ({"capsule": {"sounds": {"pack": "Retro"}}}, "sounds_pack", "soft"),
    ({"capsule": {"sounds": {"pack": ["soft"]}}}, "sounds_pack", "soft"),
])
def test_fusion_valeurs_et_replis(data, field, expected):
    assert getattr(capsule_settings(data), field) == expected


@pytest.mark.parametrize(("events", "event", "expected"), [
    ({"thinking": True}, "thinking", True),
    ({"ask": False}, "ask", False),
    ({"ask": "non"}, "ask", True),            # invalide -> defaut
    ({"thinking": "oui"}, "thinking", False),  # invalide -> defaut (false)
    ({"inconnu": False}, "ask", True),         # evenement inconnu ignore
])
def test_evenements(events, event, expected):
    cfg = capsule_settings({"capsule": {"sounds": {"events": events}}})
    assert cfg.sounds_events[event] is expected
    assert "inconnu" not in cfg.sounds_events


def test_event_enabled_respecte_interrupteur_general():
    on = capsule_settings({})
    off = capsule_settings({"capsule": {"sounds": {"enabled": False}}})
    assert on.event_enabled("ask") is True
    assert on.event_enabled("thinking") is False
    assert on.event_enabled("inconnu") is False
    assert off.event_enabled("ask") is False


def test_to_dict_json_serialisable():
    out = json.loads(json.dumps(capsule_settings({}).to_dict()))
    assert out["mascot"] == "random"
    assert out["sounds"]["events"]["thinking"] is False


def test_accepte_usersettings(tmp_path):
    settings = make_settings(tmp_path)
    settings.set("capsule.mascot", "cat")
    settings.set(event_key("pin"), False)
    cfg = capsule_settings(settings)
    assert cfg.mascot == "cat"
    assert cfg.sounds_events["pin"] is False
    assert settings.capsule() == cfg


@pytest.mark.parametrize(("key", "value"), [
    ("capsule.mascot", "owl"),
    ("capsule.mascot", "random"),
    ("capsule.sounds.enabled", False),
    ("capsule.sounds.volume", 0),
    ("capsule.sounds.volume", 1.0),
    ("capsule.sounds.pack", "crystal"),
    ("capsule.sounds.events.thinking", True),
])
def test_set_valide_persiste(tmp_path, key, value):
    settings = make_settings(tmp_path)
    settings.set(key, value)
    assert make_settings(tmp_path).get(key) == value


@pytest.mark.parametrize(("key", "value"), [
    ("capsule.mascot", "dragon"),
    ("capsule.mascot", 1),
    ("capsule.sounds.enabled", "true"),
    ("capsule.sounds.volume", 1.5),
    ("capsule.sounds.volume", -0.01),
    ("capsule.sounds.volume", True),
    ("capsule.sounds.pack", "dubstep"),
    ("capsule.sounds.events.ask", 1),
    ("capsule.sounds.events.inconnu", True),   # cle inconnue
    ("capsule.inconnue", "x"),
])
def test_set_invalide_rejete(tmp_path, key, value):
    settings = make_settings(tmp_path)
    with pytest.raises(ValueError):
        settings.set(key, value)
    assert not (tmp_path / "settings.json").exists()


def test_validate_hors_capsule_inchange():
    assert validate_capsule_value("tts.model", "x") == "x"


class TestMenuCapsule:
    def test_racine_liste_mascotte_et_sons(self, tmp_path):
        out = SettingsMenu(settings=make_settings(tmp_path), models_dir=tmp_path).open()
        assert "Mascotte capsule : random" in out
        assert "Sons capsule     : actifs" in out

    def test_choix_mascotte_par_numero_et_nom(self, tmp_path):
        menu = SettingsMenu(settings=make_settings(tmp_path), models_dir=tmp_path)
        menu.open()
        menu.handle("4")
        out = menu.handle("3")           # 1 random, 2 ascii, 3 bolt
        assert menu.settings.capsule().mascot == "bolt"
        assert "Mascotte capsule : bolt" in out
        menu.handle("4")
        menu.handle("owl")
        assert menu.settings.capsule().mascot == "owl"

    def test_mascotte_invalide(self, tmp_path):
        menu = SettingsMenu(settings=make_settings(tmp_path), models_dir=tmp_path)
        menu.open()
        menu.handle("4")
        assert "Choix invalide" in menu.handle("99")
        assert menu.settings.capsule().mascot == "random"

    def test_bascule_general_et_evenement(self, tmp_path):
        menu = SettingsMenu(settings=make_settings(tmp_path), models_dir=tmp_path)
        menu.open()
        menu.handle("5")
        menu.handle("1")
        assert menu.settings.capsule().sounds_enabled is False
        menu.handle("listen_start")
        assert menu.settings.capsule().sounds_events["listen_start"] is False
        menu.handle("4")                 # 2 listen_start, 3 listen_end, 4 thinking
        assert menu.settings.capsule().sounds_events["thinking"] is True
        assert "Choix invalide" in menu.handle("99")
