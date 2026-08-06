"""Tests unitaires pour lyra/core/settings_tui.py (touches injectees)."""

import io
import json
from pathlib import Path

from lyra.core.settings import UserSettings
from lyra.core.settings_menu import SettingsCallbacks, SettingsMenu
from lyra.core.settings_tui import run_settings_tui, select_menu

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def keys(*sequence: str):
    """Retourne un get_key qui rejoue la sequence donnee."""
    iterator = iter(sequence)
    return lambda: next(iterator)


def make_menu(tmp_path: Path, **callback_overrides) -> SettingsMenu:
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    for name, speakers in (
        ("fr_FR-siwis-medium", None),
        ("fr_FR-upmc-medium", {"jessica": 0, "pierre": 1}),
    ):
        (models_dir / f"{name}.onnx").write_bytes(b"fake")
        meta = {"audio": {"sample_rate": 22050, "quality": "medium"}}
        if speakers:
            meta["speaker_id_map"] = speakers
        (models_dir / f"{name}.onnx.json").write_text(json.dumps(meta))
    return SettingsMenu(
        settings=UserSettings(path=tmp_path / "settings.json"),
        models_dir=models_dir,
        callbacks=SettingsCallbacks(**callback_overrides),
    )


# ---------------------------------------------------------------------------
# select_menu
# ---------------------------------------------------------------------------

class TestSelectMenu:
    def test_enter_retourne_index_initial(self):
        out = io.StringIO()
        assert select_menu("T", ["a", "b", "c"], get_key=keys("enter"), out=out) == 0

    def test_navigation_bas_puis_enter(self):
        out = io.StringIO()
        result = select_menu("T", ["a", "b", "c"],
                             get_key=keys("down", "down", "enter"), out=out)
        assert result == 2

    def test_wrap_around_haut(self):
        out = io.StringIO()
        result = select_menu("T", ["a", "b", "c"], get_key=keys("up", "enter"), out=out)
        assert result == 2  # up depuis 0 -> dernier

    def test_wrap_around_bas(self):
        out = io.StringIO()
        result = select_menu("T", ["a", "b"],
                             get_key=keys("down", "down", "enter"), out=out)
        assert result == 0

    def test_esc_annule(self):
        out = io.StringIO()
        assert select_menu("T", ["a", "b"], get_key=keys("esc"), out=out) is None

    def test_q_annule(self):
        out = io.StringIO()
        assert select_menu("T", ["a"], get_key=keys("q"), out=out) is None

    def test_touche_inconnue_ignoree(self):
        out = io.StringIO()
        result = select_menu("T", ["a", "b"],
                             get_key=keys("x", "z", "down", "enter"), out=out)
        assert result == 1

    def test_ctrl_c_annule(self):
        def interrupt():
            raise KeyboardInterrupt

        out = io.StringIO()
        assert select_menu("T", ["a"], get_key=interrupt, out=out) is None

    def test_liste_vide(self):
        assert select_menu("T", [], get_key=keys("enter")) is None

    def test_index_initial_preselctionne(self):
        out = io.StringIO()
        result = select_menu("T", ["a", "b", "c"], index=1,
                             get_key=keys("enter"), out=out)
        assert result == 1

    def test_ligne_selectionnee_surlignee(self):
        out = io.StringIO()
        select_menu("T", ["alpha", "beta"], get_key=keys("enter"), out=out)
        rendered = out.getvalue()
        assert "\033[44;97m > alpha" in rendered   # selectionnee
        assert "\033[44;97m > beta" not in rendered


# ---------------------------------------------------------------------------
# run_settings_tui (ecrans complets)
# ---------------------------------------------------------------------------

class TestRunSettingsTui:
    def _run(self, menu, key_sequence, monkeypatch):
        """Lance le TUI avec une sequence de touches et collecte les messages."""
        import lyra.core.settings_tui as tui
        real_select = tui.select_menu
        get_key = keys(*key_sequence)
        sink = io.StringIO()

        def fake_select(title, items, index=0, hint="", **_kwargs):
            return real_select(title, items, index=index,
                               get_key=get_key, out=sink)

        monkeypatch.setattr(tui, "select_menu", fake_select)
        messages = []
        run_settings_tui(menu, println=messages.append)
        return messages

    def test_esc_racine_ferme(self, tmp_path, monkeypatch):
        menu = make_menu(tmp_path)
        messages = self._run(menu, ["esc"], monkeypatch)
        assert messages == ["Reglages fermes."]

    def test_changement_voix(self, tmp_path, monkeypatch):
        applied = []
        menu = make_menu(tmp_path,
                         apply_voice=lambda p, sid: applied.append((p, sid)))
        # racine: enter sur "Voix" -> ecran voix preselectionne sur jessica
        # (voix actuelle) -> down (pierre), enter -> retour racine, esc
        messages = self._run(
            menu, ["enter", "down", "enter", "esc"], monkeypatch)
        assert any("Voix changee" in m and "pierre" in m for m in messages)
        assert menu.settings.get("tts.speaker_id") == 1
        assert applied and applied[0][1] == 1

    def test_changement_vitesse_preset(self, tmp_path, monkeypatch):
        menu = make_menu(tmp_path)
        # racine: down -> "Vitesse", enter -> presets: enter sur 0.8 (index 0 ?
        # index initial = preset courant 1.0 -> index 1) : up -> 0.8, enter
        messages = self._run(
            menu, ["down", "enter", "up", "enter", "esc"], monkeypatch)
        assert any("Vitesse reglee : 0.8" in m for m in messages)
        assert menu.settings.get("tts.length_scale") == 0.8

    def test_changement_mode(self, tmp_path, monkeypatch):
        modes = {"mode": "default"}
        menu = make_menu(
            tmp_path,
            get_mode=lambda: modes["mode"],
            set_mode=lambda m: modes.update(mode=m),
        )
        # racine: down down -> "Mode", enter -> down -> performance, enter, esc
        messages = self._run(
            menu, ["down", "down", "enter", "down", "enter", "esc"], monkeypatch)
        assert any("Mode performance" in m for m in messages)
        assert modes["mode"] == "performance"

    def test_esc_sous_menu_revient_racine(self, tmp_path, monkeypatch):
        menu = make_menu(tmp_path)
        # entrer dans voix, esc (retour racine sans changement), esc (fermer)
        messages = self._run(menu, ["enter", "esc", "esc"], monkeypatch)
        assert messages == ["Reglages fermes."]
        assert menu.settings.get("tts.model") is None
