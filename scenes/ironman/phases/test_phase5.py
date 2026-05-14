"""
Tests pour Phase 5 - TTS J.A.R.V.I.S.
"""

import time
from unittest.mock import Mock, patch, MagicMock
import pytest

from .phase5_tts import (
    Phase5TTS,
    PHRASES,
    PULSE_BRIGHTNESS_HIGH,
    PULSE_BRIGHTNESS_LOW,
    PULSE_DURATION,
    TTS_LENGTH_SCALE,
    rgb_to_xy,
)


class TestPhase5TTS:
    """Tests pour la classe Phase5TTS."""

    @pytest.fixture
    def phase5(self):
        """Cree une instance Phase5 avec config mockee."""
        with patch.object(Phase5TTS, '_load_config') as mock_config:
            mock_config.return_value = {
                "hue": {
                    "bridge_ip": "192.168.1.51",
                    "username": "test-user-123"
                }
            }
            return Phase5TTS()

    def test_select_phrase_random(self, phase5):
        """Selection aleatoire parmi les phrases."""
        phrase = phase5._select_phrase(None)
        assert phrase in PHRASES

    def test_select_phrase_specific(self, phase5):
        """Utilise phrase specifique si fournie."""
        custom = "Ma phrase custom"
        phrase = phase5._select_phrase(custom)
        assert phrase == custom

    def test_select_phrase_variety(self, phase5):
        """Plusieurs appels donnent des phrases differentes (probabiliste)."""
        phrases_selected = set()
        for _ in range(50):
            phrases_selected.add(phase5._select_phrase(None))

        # Avec 50 essais sur 5 phrases, tres probable d'avoir au moins 2 differentes
        assert len(phrases_selected) >= 2

    @patch('requests.put')
    def test_confirmation_pulse_up(self, mock_put, phase5):
        """Pulse monte a 200."""
        mock_put.return_value = Mock(status_code=200)

        phase5._confirmation_pulse()

        # Premier appel = montee
        first_call = mock_put.call_args_list[0]
        payload = first_call.kwargs.get('json') or first_call[1].get('json')
        assert payload["bri"] == PULSE_BRIGHTNESS_HIGH
        assert payload["transitiontime"] == 5  # 500ms

    @patch('requests.put')
    def test_confirmation_pulse_down(self, mock_put, phase5):
        """Pulse redescend a 150."""
        mock_put.return_value = Mock(status_code=200)

        phase5._confirmation_pulse()

        # Deuxieme appel = descente
        second_call = mock_put.call_args_list[1]
        payload = second_call.kwargs.get('json') or second_call[1].get('json')
        assert payload["bri"] == PULSE_BRIGHTNESS_LOW
        assert payload["transitiontime"] == 5  # 500ms

    @patch('requests.put')
    def test_execute_with_specific_phrase(self, mock_put, phase5):
        """Execute avec phrase specifique."""
        mock_put.return_value = Mock(status_code=200)
        custom_phrase = "Test phrase custom"

        with patch.object(phase5, '_speak_jarvis_style', return_value=True):
            result = phase5.execute(phrase=custom_phrase)

        assert result["phrase_used"] == custom_phrase

    @patch('requests.put')
    def test_execute_with_random_phrase(self, mock_put, phase5):
        """Execute avec phrase aleatoire."""
        mock_put.return_value = Mock(status_code=200)

        with patch.object(phase5, '_speak_jarvis_style', return_value=True):
            result = phase5.execute()

        assert result["phrase_used"] in PHRASES

    @patch('requests.put')
    def test_execute_tts_called(self, mock_put, phase5):
        """TTS est appele."""
        mock_put.return_value = Mock(status_code=200)

        with patch.object(phase5, '_speak_jarvis_style', return_value=True) as mock_tts:
            phase5.execute(phrase="Test")

        mock_tts.assert_called_once_with("Test")

    @patch('requests.put')
    def test_execute_pulse_called(self, mock_put, phase5):
        """Pulse est execute."""
        mock_put.return_value = Mock(status_code=200)

        with patch.object(phase5, '_speak_jarvis_style', return_value=True):
            result = phase5.execute()

        assert result["pulse_ok"] is True

    @patch('requests.put')
    def test_execute_success_tts_ok(self, mock_put, phase5):
        """Succes si TTS OK."""
        mock_put.return_value = Mock(status_code=200)

        with patch.object(phase5, '_speak_jarvis_style', return_value=True):
            result = phase5.execute()

        assert result["success"] is True
        assert result["tts_ok"] is True

    @patch('requests.put')
    def test_execute_success_pulse_only(self, mock_put, phase5):
        """Succes meme si TTS echoue mais pulse OK."""
        mock_put.return_value = Mock(status_code=200)

        with patch.object(phase5, '_speak_jarvis_style', return_value=False):
            result = phase5.execute()

        assert result["success"] is True  # Pulse OK suffit
        assert result["tts_ok"] is False
        assert result["pulse_ok"] is True

    @patch('requests.put')
    def test_execute_duration(self, mock_put, phase5):
        """Duree ~5-6s."""
        mock_put.return_value = Mock(status_code=200)

        with patch.object(phase5, '_speak_jarvis_style', return_value=True):
            result = phase5.execute()

        # Tolerance: 5-7s (TTS peut varier)
        assert 5.0 <= result["duration"] <= 7.0


class TestPhrases:
    """Tests pour les phrases J.A.R.V.I.S."""

    def test_5_phrases(self):
        """5 phrases disponibles."""
        assert len(PHRASES) == 5

    def test_phrases_in_french(self):
        """Phrases en francais."""
        for phrase in PHRASES:
            # Verifier mots francais courants
            assert any(word in phrase.lower() for word in
                      ["bonjour", "systeme", "pret", "comment", "armure", "jarvis"])

    def test_phrases_not_empty(self):
        """Aucune phrase vide."""
        for phrase in PHRASES:
            assert len(phrase) > 10


class TestConstants:
    """Tests pour les constantes."""

    def test_pulse_high(self):
        """Brightness pulse haut = 200."""
        assert PULSE_BRIGHTNESS_HIGH == 200

    def test_pulse_low(self):
        """Brightness pulse bas = 150."""
        assert PULSE_BRIGHTNESS_LOW == 150

    def test_pulse_duration(self):
        """Duree pulse = 500ms."""
        assert PULSE_DURATION == 0.5

    def test_tts_length_scale(self):
        """TTS plus lent (1.1 = 0.9x vitesse)."""
        assert TTS_LENGTH_SCALE == 1.1
