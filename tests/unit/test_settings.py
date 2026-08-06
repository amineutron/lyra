"""Tests unitaires pour lyra/core/settings.py et settings_menu.py."""

import json
from pathlib import Path

import pytest

from lyra.core.settings import (
    UserSettings,
    find_voice,
    list_available_voices,
)
from lyra.core.settings_menu import SettingsCallbacks, SettingsMenu

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_settings(tmp_path: Path) -> UserSettings:
    return UserSettings(path=tmp_path / "settings.json")


def make_voice_model(models_dir: Path, name: str, speakers: dict | None,
                     quality: str = "medium") -> None:
    """Cree un faux couple .onnx / .onnx.json."""
    models_dir.mkdir(parents=True, exist_ok=True)
    (models_dir / f"{name}.onnx").write_bytes(b"fake")
    meta = {"audio": {"sample_rate": 22050, "quality": quality}}
    if speakers is not None:
        meta["speaker_id_map"] = speakers
        meta["num_speakers"] = len(speakers)
    (models_dir / f"{name}.onnx.json").write_text(json.dumps(meta))


# ---------------------------------------------------------------------------
# UserSettings
# ---------------------------------------------------------------------------

class TestUserSettings:
    def test_get_default_sans_fichier(self, tmp_path):
        settings = make_settings(tmp_path)
        assert settings.get("tts.model") is None
        assert settings.get("tts.model", "fallback") == "fallback"

    def test_set_puis_get(self, tmp_path):
        settings = make_settings(tmp_path)
        settings.set("tts.model", "fr_FR-siwis-medium")
        assert settings.get("tts.model") == "fr_FR-siwis-medium"

    def test_persistance_entre_instances(self, tmp_path):
        make_settings(tmp_path).set("tts.speaker_id", 1)
        assert make_settings(tmp_path).get("tts.speaker_id") == 1

    def test_cle_inconnue_rejetee(self, tmp_path):
        settings = make_settings(tmp_path)
        with pytest.raises(ValueError):
            settings.set("hack.injection", "x")

    def test_fichier_corrompu_ignore(self, tmp_path):
        path = tmp_path / "settings.json"
        path.write_text("{invalid json")
        settings = UserSettings(path=path)
        assert settings.get("tts.model") is None
        # set() doit reparer le fichier
        settings.set("tts.model", "fr_FR-tom-medium")
        assert json.loads(path.read_text())["tts"]["model"] == "fr_FR-tom-medium"

    def test_ecriture_atomique_pas_de_tmp_restant(self, tmp_path):
        settings = make_settings(tmp_path)
        settings.set("active_mode", "performance")
        leftovers = list(tmp_path.glob("*.tmp"))
        assert leftovers == []

    def test_merged_tts_override_partiel(self, tmp_path):
        settings = make_settings(tmp_path)
        settings.set("tts.model", "fr_FR-siwis-medium")
        yaml_tts = {"engine": "piper", "model": "fr_FR-upmc-medium",
                    "speaker_id": 0, "length_scale": 1.0}
        merged = settings.merged_tts(yaml_tts)
        assert merged["model"] == "fr_FR-siwis-medium"   # override
        assert merged["speaker_id"] == 0                  # yaml conserve
        assert merged["engine"] == "piper"                # cle inconnue conservee
        # immutabilite : le dict source n'est pas modifie
        assert yaml_tts["model"] == "fr_FR-upmc-medium"

    @pytest.mark.parametrize("stored,expected", [
        (None, "default"),
        ("performance", "performance"),
        ("default", "default"),
        ("n_importe_quoi", "default"),
    ])
    def test_active_mode(self, tmp_path, stored, expected):
        settings = make_settings(tmp_path)
        if stored is not None:
            # ecrire directement pour tester aussi les valeurs invalides
            (tmp_path / "settings.json").write_text(
                json.dumps({"active_mode": stored}))
            settings = make_settings(tmp_path)
        assert settings.active_mode() == expected


# ---------------------------------------------------------------------------
# list_available_voices
# ---------------------------------------------------------------------------

class TestListAvailableVoices:
    def test_mono_speaker(self, tmp_path):
        make_voice_model(tmp_path, "fr_FR-siwis-medium", None)
        voices = list_available_voices(tmp_path)
        assert len(voices) == 1
        assert voices[0].speaker_name == "siwis"
        assert voices[0].speaker_id == 0

    def test_multi_speaker(self, tmp_path):
        make_voice_model(tmp_path, "fr_FR-upmc-medium",
                         {"jessica": 0, "pierre": 1})
        voices = list_available_voices(tmp_path)
        assert [(v.speaker_name, v.speaker_id) for v in voices] == [
            ("jessica", 0), ("pierre", 1)]

    def test_corpus_massif_plafonne(self, tmp_path):
        speakers = {str(i): i for i in range(125)}
        make_voice_model(tmp_path, "fr_FR-mls-medium", speakers)
        voices = list_available_voices(tmp_path)
        assert len(voices) == 2  # MAX_SPEAKERS_SHOWN

    def test_onnx_manquant_ignore(self, tmp_path):
        make_voice_model(tmp_path, "fr_FR-tom-medium", None)
        (tmp_path / "fr_FR-tom-medium.onnx").unlink()
        assert list_available_voices(tmp_path) == []

    def test_json_corrompu_ignore(self, tmp_path):
        make_voice_model(tmp_path, "fr_FR-tom-medium", None)
        (tmp_path / "fr_FR-tom-medium.onnx.json").write_text("{broken")
        assert list_available_voices(tmp_path) == []

    def test_find_voice(self, tmp_path):
        make_voice_model(tmp_path, "fr_FR-upmc-medium",
                         {"jessica": 0, "pierre": 1})
        voices = list_available_voices(tmp_path)
        found = find_voice(voices, "fr_FR-upmc-medium", 1)
        assert found is not None and found.speaker_name == "pierre"
        assert find_voice(voices, "fr_FR-absent", 0) is None


# ---------------------------------------------------------------------------
# SettingsMenu
# ---------------------------------------------------------------------------

def make_menu(tmp_path: Path, **callback_overrides) -> SettingsMenu:
    models_dir = tmp_path / "models"
    make_voice_model(models_dir, "fr_FR-siwis-medium", None)
    make_voice_model(models_dir, "fr_FR-upmc-medium", {"jessica": 0, "pierre": 1})
    callbacks = SettingsCallbacks(**callback_overrides)
    return SettingsMenu(
        settings=make_settings(tmp_path),
        models_dir=models_dir,
        callbacks=callbacks,
    )


class TestSettingsMenu:
    def test_open_affiche_racine(self, tmp_path):
        menu = make_menu(tmp_path)
        out = menu.open()
        assert menu.active
        assert "1. Voix" in out and "2. Vitesse" in out and "3. Mode" in out

    def test_q_racine_ferme(self, tmp_path):
        menu = make_menu(tmp_path)
        menu.open()
        menu.handle("q")
        assert not menu.active

    def test_q_sous_menu_revient_racine(self, tmp_path):
        menu = make_menu(tmp_path)
        menu.open()
        menu.handle("1")            # sous-menu voix
        out = menu.handle("q")      # retour racine, menu toujours ouvert
        assert menu.active
        assert "Reglages Lyra" in out

    def test_choix_invalide_racine(self, tmp_path):
        menu = make_menu(tmp_path)
        menu.open()
        out = menu.handle("42")
        assert "invalide" in out.lower()
        assert menu.active

    def test_selection_voix_persiste(self, tmp_path):
        applied = []
        menu = make_menu(tmp_path,
                         apply_voice=lambda p, sid: applied.append((p, sid)))
        menu.open()
        listing = menu.handle("1")
        # ordre alphabetique des fichiers : siwis avant upmc
        assert "1. siwis" in listing
        out = menu.handle("3")      # upmc pierre (2=jessica, 3=pierre)
        assert "[+] Voix changee" in out and "pierre" in out
        assert menu.settings.get("tts.model") == "fr_FR-upmc-medium"
        assert menu.settings.get("tts.speaker_id") == 1
        assert applied and applied[0][1] == 1

    def test_selection_voix_sans_callback_note_differee(self, tmp_path):
        menu = make_menu(tmp_path)  # pas de apply_voice (mode texte)
        menu.open()
        menu.handle("1")
        out = menu.handle("1")
        assert "prochaine session vocale" in out

    @pytest.mark.parametrize("entree,attendu", [
        ("1", 0.8), ("2", 1.0), ("3", 1.2),   # presets
        ("0.9", 0.9), ("1,5", 1.5),           # saisie libre (virgule ok)
    ])
    def test_vitesse_valide(self, tmp_path, entree, attendu):
        menu = make_menu(tmp_path)
        menu.open()
        menu.handle("2")
        out = menu.handle(entree)
        assert "[+] Vitesse reglee" in out
        assert menu.settings.get("tts.length_scale") == attendu

    @pytest.mark.parametrize("entree", ["0.1", "5", "abc", "-1"])
    def test_vitesse_invalide(self, tmp_path, entree):
        menu = make_menu(tmp_path)
        menu.open()
        menu.handle("2")
        out = menu.handle(entree)
        assert "invalide" in out.lower()
        assert menu.settings.get("tts.length_scale") is None

    def test_changement_mode(self, tmp_path):
        modes = {"mode": "default"}
        menu = make_menu(
            tmp_path,
            get_mode=lambda: modes["mode"],
            set_mode=lambda m: modes.update(mode=m),
        )
        menu.open()
        menu.handle("3")
        out = menu.handle("2")
        assert "[+] Mode performance" in out
        assert modes["mode"] == "performance"
        assert menu.settings.get("active_mode") == "performance"

    def test_callback_qui_leve_ne_crashe_pas(self, tmp_path):
        def boom(*_args):
            raise RuntimeError("device busy")

        menu = make_menu(tmp_path, apply_voice=boom)
        menu.open()
        menu.handle("1")
        out = menu.handle("1")
        # le reglage est persiste malgre l'echec du hot-swap
        assert menu.settings.get("tts.model") == "fr_FR-siwis-medium"
        assert "prochaine session vocale" in out
