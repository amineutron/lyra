"""Regression : stt.compute_type de config.yaml doit atteindre Whisper.

Avant le fix, VoiceInterface ignorait la cle et imposait float16 : le STT sur
CPU echouait ("float16 compute type not supported") et le mode vocal
basculait en standalone.
"""

import pytest

import modules.audio as audio


class _FakeSTT:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


@pytest.mark.parametrize("kwargs,expected", [
    ({}, "float16"),
    ({"compute_type": "int8"}, "int8"),
    ({"device": "cpu", "compute_type": "int8_float16"}, "int8_float16"),
])
def test_compute_type_reaches_stt(monkeypatch, kwargs, expected):
    monkeypatch.setattr(audio, "STT", _FakeSTT)
    monkeypatch.setattr(audio, "TTS", lambda **kw: object())
    monkeypatch.setattr(audio, "AudioRecorder", lambda **kw: object())
    voice = audio.VoiceInterface(**kwargs)
    assert voice.stt.kwargs["compute_type"] == expected
