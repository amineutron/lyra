"""Le generateur de sons (scripts/gen_sounds.py) est deterministe : les WAV
commites dans lyra/client/assets/sounds/ doivent etre exactement ceux qu'il
produit, et respecter le format promis (16 bits mono 44100 Hz, 80 a 950 ms,
pic a -6 dBFS)."""
import sys
import wave
from array import array
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import gen_sounds  # noqa: E402

COMMITTED = ROOT / "lyra" / "client" / "assets" / "sounds"
PEAK_LIMIT = int(round(10 ** (gen_sounds.PEAK_DBFS / 20) * 32767))


def test_regeneration_identique_aux_fichiers_commites(tmp_path):
    for pack in gen_sounds.PACKS:
        written = gen_sounds.generate_pack(pack, tmp_path / pack)
        assert {p.name for p in written} == {p.name for p in (COMMITTED / pack).glob("*.wav")}
        for path in written:
            assert path.read_bytes() == (COMMITTED / pack / path.name).read_bytes(), path.name


def test_deux_generations_donnent_les_memes_octets(tmp_path):
    first = gen_sounds.generate_pack("soft", tmp_path / "a")
    second = gen_sounds.generate_pack("soft", tmp_path / "b")
    for a, b in zip(first, second):
        assert a.read_bytes() == b.read_bytes()


def test_jeu_soft_couvre_les_12_evenements():
    assert len(gen_sounds.PACKS["soft"]) == 12


@pytest.mark.parametrize("event_id", sorted(gen_sounds.SOFT_EVENTS))
def test_format_duree_et_pic(event_id):
    with wave.open(str(COMMITTED / "soft" / f"{event_id}.wav")) as wf:
        assert (wf.getnchannels(), wf.getsampwidth(), wf.getframerate()) == (1, 2, 44100)
        duration_ms = wf.getnframes() / wf.getframerate() * 1000
        pcm = array("h")
        pcm.frombytes(wf.readframes(wf.getnframes()))
    assert 80 <= duration_ms <= 950
    assert abs(max(pcm, key=abs)) == pytest.approx(PEAK_LIMIT, abs=2)
    assert abs(pcm[-1]) < 50  # fondu final : pas de clic


def test_midi_to_hz():
    assert gen_sounds.midi_to_hz(69) == pytest.approx(440.0)
    assert gen_sounds.midi_to_hz(81) == pytest.approx(880.0)


def test_jeu_inconnu_refuse(tmp_path):
    with pytest.raises(ValueError):
        gen_sounds.generate_pack("crystal", tmp_path)
