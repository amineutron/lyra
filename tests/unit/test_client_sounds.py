"""SoundPlayer : respect de enabled / volume / events[id], id inconnu ignore,
aucun lecteur, priorite warn/error. Aucun son n'est joue : Popen, which et
Timer sont remplaces."""
import wave
from array import array
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lyra.client import sounds
from lyra.client.sounds import SOUND_IDS, SoundConfig, SoundPlayer, clamp_volume

EXPECTED_IDS = {
    "listen_start", "listen_end", "thinking", "speak_start", "ask", "confirm",
    "warn", "success", "error", "cancel", "choice", "pin",
}


@pytest.fixture
def popen(monkeypatch):
    """Popen factice : chaque appel renvoie un process vivant distinct."""
    calls = []

    def fake_popen(cmd, **kwargs):
        proc = MagicMock(name=f"proc{len(calls)}")
        proc.poll.return_value = None
        calls.append((cmd, kwargs, proc))
        return proc

    monkeypatch.setattr(sounds.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(sounds.threading, "Timer", MagicMock())
    monkeypatch.setattr(sounds.shutil, "which", lambda name: f"/usr/bin/{name}")
    return calls


def test_table_des_12_ids_et_fichiers_presents():
    assert set(SOUND_IDS) == EXPECTED_IDS and len(SOUND_IDS) == 12
    for pack in sounds.PACKS:
        for event_id in SOUND_IDS:
            assert (sounds.SOUNDS_DIR / pack / f"{event_id}.wav").is_file()


@pytest.mark.parametrize("event_id", SOUND_IDS)
def test_chaque_id_lance_son_fichier(popen, event_id):
    player = SoundPlayer({"volume": 1.0})
    assert player.play(event_id) is True
    cmd, kwargs, _ = popen[0]
    assert cmd[0].endswith("pw-play")
    assert cmd[-1] == str(sounds.SOUNDS_DIR / "soft" / f"{event_id}.wav")
    assert kwargs["start_new_session"] is True
    assert "shell" not in kwargs


def test_config_desactivee_ne_joue_rien(popen):
    assert SoundPlayer({"enabled": False}).play("success") is False
    assert popen == []


def test_evenement_desactive_silencieux_les_autres_jouent(popen):
    player = SoundPlayer({"events": {"pin": False}})
    assert player.play("pin") is False
    assert player.play("choice") is True
    assert len(popen) == 1


def test_id_inconnu_ignore_sans_exception(popen):
    player = SoundPlayer({})
    for bad in ("nope", "", "../../etc/passwd", "soft/ask", None, 42):
        assert player.play(bad) is False
    assert popen == []


@pytest.mark.parametrize("raw,expected", [
    (5, 1.0), (1.5, 1.0), (-2, 0.0), (0.4, 0.4), ("0.5", 0.5),
    (float("nan"), sounds.DEFAULT_VOLUME), ("bruit", sounds.DEFAULT_VOLUME),
    (None, sounds.DEFAULT_VOLUME), (True, sounds.DEFAULT_VOLUME),
])
def test_clamp_volume(raw, expected):
    assert clamp_volume(raw) == expected


def test_volume_hors_bornes_plafonne_a_1_et_utilise_le_fichier_original(popen):
    assert SoundPlayer({"volume": 7}).play("ask") is True
    assert popen[0][0][-1] == str(sounds.SOUNDS_DIR / "soft" / "ask.wav")


def test_volume_zero_ou_negatif_silencieux(popen):
    assert SoundPlayer({"volume": -3}).play("ask") is False
    assert popen == []


def test_volume_inferieur_a_1_met_les_echantillons_a_l_echelle(popen):
    player = SoundPlayer({"volume": 0.5})
    assert player.play("choice") is True
    scaled = Path(popen[0][0][-1])
    assert scaled != sounds.SOUNDS_DIR / "soft" / "choice.wav"

    def peak(path):
        with wave.open(str(path)) as wf:
            pcm = array("h")
            pcm.frombytes(wf.readframes(wf.getnframes()))
        return max(abs(s) for s in pcm)

    original = peak(sounds.SOUNDS_DIR / "soft" / "choice.wav")
    assert peak(scaled) == pytest.approx(original * 0.5, abs=1)


def test_aucun_lecteur_disponible(monkeypatch):
    monkeypatch.setattr(sounds.shutil, "which", lambda name: None)
    popen = MagicMock()
    monkeypatch.setattr(sounds.subprocess, "Popen", popen)
    player = SoundPlayer({"volume": 1.0})
    assert player.play("success") is False
    assert player.play("error") is False
    popen.assert_not_called()


def test_ordre_des_lecteurs_et_cache(monkeypatch, popen):
    seen = []

    def which(name):
        seen.append(name)
        return "/usr/bin/aplay" if name == "aplay" else None

    monkeypatch.setattr(sounds.shutil, "which", which)
    player = SoundPlayer({"volume": 1.0})
    player.play("ask")
    player.play("pin")
    assert seen == ["pw-play", "paplay", "aplay"]  # detecte une seule fois
    assert popen[0][0][:2] == ["/usr/bin/aplay", "-q"]


def test_fichier_absent_ignore(monkeypatch, popen):
    monkeypatch.setattr(sounds, "SOUNDS_DIR", Path("/nonexistent-lyra-sounds"))
    assert SoundPlayer({"volume": 1.0}).play("ask") is False
    assert popen == []


def test_echec_de_lancement_ignore(monkeypatch):
    monkeypatch.setattr(sounds.shutil, "which", lambda name: f"/usr/bin/{name}")

    def boom(*a, **k):
        raise OSError("exec failed")

    monkeypatch.setattr(sounds.subprocess, "Popen", boom)
    assert SoundPlayer({"volume": 1.0}).play("ask") is False


def test_jeu_inconnu_repli_sur_soft(popen):
    assert SoundPlayer({"pack": "../evil", "volume": 1.0}).play("ask") is True
    assert "/soft/ask.wav" in popen[0][0][-1]


def test_evenement_prioritaire_coupe_le_son_en_cours(popen):
    player = SoundPlayer({"volume": 1.0})
    player.play("thinking")
    first = popen[0][2]
    player.play("error")
    first.kill.assert_called_once()
    assert len(popen) == 2


def test_evenement_normal_se_superpose(popen):
    player = SoundPlayer({"volume": 1.0})
    player.play("thinking")
    player.play("choice")
    popen[0][2].kill.assert_not_called()
    assert len(popen) == 2


def test_config_dataclass_acceptee(popen):
    cfg = SoundConfig(enabled=True, volume=1.0, events={"ask": False})
    player = SoundPlayer(cfg)
    assert player.play("ask") is False
    assert player.play("pin") is True


def test_config_dict_invalide_ne_leve_pas():
    cfg = SoundConfig.from_mapping({"events": "oups", "volume": "x", "enabled": 0})
    assert cfg.enabled is False and cfg.events == {} and cfg.volume == sounds.DEFAULT_VOLUME
    assert SoundConfig.from_mapping(None).enabled is True
