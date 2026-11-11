"""Branchement des sons sur le client vocal : config tolerante, jamais bloquant.
SoundPlayer est mocke : aucun son reel, aucun lecteur lance."""
from unittest.mock import MagicMock

import pytest

from lyra.client import capsule_sounds as cs
from lyra.client.sounds import SOUND_IDS


def test_defaut_sans_bloc_capsule():
    cfg = cs.build_sound_config({})
    assert cfg.enabled is True and cfg.volume == 0.35 and cfg.pack == "soft"
    assert cfg.events["thinking"] is False
    assert all(cfg.events[i] for i in SOUND_IDS if i != "thinking")


@pytest.mark.parametrize("raw", [None, "x", {"capsule": None}, {"capsule": {"sounds": "oops"}},
                                 {"capsule": {"sounds": {"events": ["a"]}}}])
def test_config_invalide_retombe_sur_defauts(raw):
    cfg = cs.build_sound_config(raw)
    assert cfg.enabled and cfg.events["thinking"] is False and cfg.events["warn"] is True


def test_surcharges_utilisateur_et_ids_inconnus_ignores():
    cfg = cs.build_sound_config({"capsule": {"sounds": {
        "volume": 0.8, "pack": "soft",
        "events": {"thinking": True, "warn": False, "bogus": True}}}})
    assert cfg.volume == 0.8
    assert cfg.events["thinking"] is True and cfg.events["warn"] is False
    assert "bogus" not in cfg.events


def test_load_sound_config_fichier_absent_ou_invalide(tmp_path):
    assert cs.load_sound_config(tmp_path / "nope.yaml").enabled is True
    bad = tmp_path / "bad.yaml"
    bad.write_text("a: [unclosed")
    assert cs.load_sound_config(bad).volume == 0.35


def test_load_sound_config_lit_le_yaml(tmp_path):
    f = tmp_path / "c.yaml"
    f.write_text("capsule:\n  sounds:\n    volume: 0.5\n    events:\n      ask: false\n")
    cfg = cs.load_sound_config(f)
    assert cfg.volume == 0.5 and cfg.events["ask"] is False


def test_make_player_desactive_donne_none():
    assert cs.make_player({"capsule": {"sounds": {"enabled": False}}}) is None
    assert cs.make_player({}) is not None


def test_play_cue_ne_leve_jamais(caplog):
    player = MagicMock()
    player.play.side_effect = RuntimeError("boom")
    assert cs.play_cue(player, "error") is False
    assert cs.play_cue(None, "error") is False
    ok = MagicMock()
    ok.play.return_value = True
    assert cs.play_cue(ok, "success") is True
    ok.play.assert_called_once_with("success")


def test_settle_seulement_si_le_son_a_joue():
    sleep = MagicMock()
    cs.settle_after_listen_start(False, sleep=sleep)
    sleep.assert_not_called()
    cs.settle_after_listen_start(True, sleep=sleep)
    sleep.assert_called_once_with(cs.LISTEN_SETTLE_S)


def _voice(sounds):
    """VoiceInterface sans STT/TTS reels."""
    try:
        import modules.audio as audio
    except OSError:  # PortAudio absent (CI runners)
        pytest.skip("PortAudio library not available")
    v = audio.VoiceInterface.__new__(audio.VoiceInterface)
    v.sounds = sounds
    v.tts = MagicMock()
    v.stt = MagicMock()
    v.recorder = MagicMock()
    v.recorder.record_until_silence.return_value = []
    v.config = MagicMock(output_device=None)
    return v


def test_speak_joue_speak_start_puis_le_cue_demande(monkeypatch):
    player = MagicMock()
    v = _voice(player)
    v.speak("salut")
    v.speak("attention", cue="warn")
    assert [c.args[0] for c in player.play.call_args_list] == ["speak_start", "warn"]
    assert v.tts.speak.call_count == 2


def test_speak_survit_a_un_lecteur_qui_plante():
    player = MagicMock()
    player.play.side_effect = RuntimeError("boom")
    v = _voice(player)
    v.speak("salut")
    v.tts.speak.assert_called_once()


def test_listen_remplace_le_bip_par_les_sons(monkeypatch):
    player = MagicMock()
    player.play.return_value = True
    monkeypatch.setattr(cs.time, "sleep", lambda s: None)
    v = _voice(player)
    v.beep = MagicMock()
    assert v.listen() == ""
    assert [c.args[0] for c in player.play.call_args_list] == ["listen_start", "listen_end"]
    v.beep.assert_not_called()


def test_listen_sans_sons_garde_le_bip_historique():
    v = _voice(None)
    v.beep = MagicMock()
    v.listen()
    v.beep.assert_called_once()
