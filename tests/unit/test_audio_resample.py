"""Rééchantillonnage et amorce de silence (STT 48k -> 16k, TTS 22k -> 48k)."""

import numpy as np
import pytest

try:
    from modules.audio import resample_audio, with_lead_silence
except OSError:  # PortAudio absent (CI runners): nothing to test here
    pytest.skip("PortAudio library not available", allow_module_level=True)


def _tone(freq, sr, seconds=0.5):
    t = np.arange(int(sr * seconds)) / sr
    return np.sin(2 * np.pi * freq * t).astype(np.float32)


@pytest.mark.parametrize("src,dst", [(48000, 16000), (22050, 48000), (44100, 16000)])
def test_resample_length_and_dtype(src, dst):
    out = resample_audio(_tone(440, src), src, dst)
    assert out.dtype == np.float32
    assert abs(len(out) - int(0.5 * dst)) <= 2


def test_resample_same_rate_is_identity():
    audio = _tone(440, 16000)
    assert np.array_equal(resample_audio(audio, 16000, 16000), audio)


def test_resample_empty_audio():
    assert len(resample_audio(np.array([], dtype=np.float32), 48000, 16000)) == 0


def test_resample_attenuates_frequencies_above_target_nyquist():
    """Regression : 12 kHz a 48 kHz se repliait a 4 kHz avec l'interpolation
    lineaire (amplitude ~ pleine) ; le filtre anti-repliement l'attenue."""
    out = resample_audio(_tone(12000, 48000), 48000, 16000)
    assert np.abs(out[200:-200]).max() < 0.1


def test_resample_keeps_in_band_tone():
    out = resample_audio(_tone(1000, 48000), 48000, 16000)
    assert np.abs(out[200:-200]).max() > 0.9


def test_lead_silence_prepends_without_mutating_input():
    audio = np.ones(100, dtype=np.float32)
    out = with_lead_silence(audio, 48000, 0.25)
    assert len(out) == 12000 + 100
    assert not out[:12000].any()
    assert out[12000:].all()
    assert audio.sum() == 100


def test_lead_silence_negative_means_none():
    audio = np.ones(10, dtype=np.float32)
    assert len(with_lead_silence(audio, 48000, -1.0)) == 10
