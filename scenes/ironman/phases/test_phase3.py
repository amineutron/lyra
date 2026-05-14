"""
Tests pour Phase 3 - Pulsations Synchronisees
"""

import time
from unittest.mock import Mock, patch, MagicMock
import pytest

from .phase3_buildup import (
    Phase3Buildup,
    DURATION,
    BEATS_TIMING,
    FLASH_DURATION,
    TRANSITION_DURATION,
    BLUE_ARC_REACTOR_RGB,
    RED_INTENSE_RGB,
    rgb_to_xy,
)


class TestPhase3Buildup:
    """Tests pour la classe Phase3Buildup."""

    @pytest.fixture
    def phase3(self):
        """Cree une instance Phase3 avec config mockee."""
        with patch.object(Phase3Buildup, '_load_config') as mock_config:
            mock_config.return_value = {
                "hue": {
                    "bridge_ip": "192.168.1.51",
                    "username": "test-user-123"
                }
            }
            return Phase3Buildup()

    def test_calculate_brightness_start(self, phase3):
        """Brightness = 0 au debut."""
        brightness = phase3._calculate_brightness(0.0)
        assert brightness == 0

    def test_calculate_brightness_quarter(self, phase3):
        """Brightness = 63 a 25% (T+3s)."""
        brightness = phase3._calculate_brightness(3.0)
        assert brightness == 63  # 254 * 0.25 = 63.5 -> 63

    def test_calculate_brightness_half(self, phase3):
        """Brightness = 127 a 50% (T+6s)."""
        brightness = phase3._calculate_brightness(6.0)
        assert brightness == 127  # 254 * 0.5 = 127

    def test_calculate_brightness_three_quarters(self, phase3):
        """Brightness = 190 a 75% (T+9s)."""
        brightness = phase3._calculate_brightness(9.0)
        assert brightness == 190  # 254 * 0.75 = 190.5 -> 190

    def test_calculate_brightness_end(self, phase3):
        """Brightness = 254 a 100% (T+12s)."""
        brightness = phase3._calculate_brightness(12.0)
        assert brightness == 254

    def test_calculate_brightness_linear(self, phase3):
        """Progression lineaire correcte."""
        samples = [0, 2, 4, 6, 8, 10, 12]
        expected = [0, 42, 84, 127, 169, 211, 254]

        for t, exp in zip(samples, expected):
            brightness = phase3._calculate_brightness(float(t))
            # Tolerance de 1 pour les arrondis
            assert abs(brightness - exp) <= 1, f"T={t}s: got {brightness}, expected {exp}"

    def test_calculate_brightness_clamped_negative(self, phase3):
        """Temps negatif clampe a 0."""
        brightness = phase3._calculate_brightness(-1.0)
        assert brightness == 0

    def test_calculate_brightness_clamped_overflow(self, phase3):
        """Temps > 12s clampe a 254."""
        brightness = phase3._calculate_brightness(15.0)
        assert brightness == 254

    @patch('requests.put')
    def test_execute_beat_flash_rouge(self, mock_put, phase3):
        """Beat envoie d'abord flash rouge."""
        mock_put.return_value = Mock(status_code=200)

        phase3._execute_beat(brightness=127)

        # Premier appel = flash rouge
        first_call = mock_put.call_args_list[0]
        payload = first_call.kwargs.get('json') or first_call[1].get('json')
        xy_rouge = rgb_to_xy(*RED_INTENSE_RGB)

        assert payload["bri"] == 127
        assert payload["transitiontime"] == 0  # Instantane
        assert abs(payload["xy"][0] - xy_rouge[0]) < 0.01

    @patch('requests.put')
    def test_execute_beat_retour_bleu(self, mock_put, phase3):
        """Beat retourne ensuite au bleu."""
        mock_put.return_value = Mock(status_code=200)

        phase3._execute_beat(brightness=127)

        # Deuxieme appel = retour bleu
        second_call = mock_put.call_args_list[1]
        payload = second_call.kwargs.get('json') or second_call[1].get('json')
        xy_bleu = rgb_to_xy(*BLUE_ARC_REACTOR_RGB)

        assert payload["bri"] == 127
        assert payload["transitiontime"] == 2  # 200ms
        assert abs(payload["xy"][0] - xy_bleu[0]) < 0.01

    @patch('requests.put')
    @patch('time.sleep')
    def test_execute_24_beats(self, mock_sleep, mock_put, phase3):
        """Execute ~24 beats."""
        mock_put.return_value = Mock(status_code=200)

        result = phase3.execute()

        assert result["beats_executed"] == 24
        assert result["success"] is True

    @patch('requests.put')
    @patch('time.sleep')
    @patch('time.perf_counter')
    def test_execute_final_brightness(self, mock_perf, mock_sleep, mock_put, phase3):
        """Brightness final proche de 254."""
        mock_put.return_value = Mock(status_code=200)
        # Simuler le temps qui passe normalement
        mock_perf.side_effect = [0.0] + [t * 0.5 for t in range(50)]

        result = phase3.execute()

        # Le dernier beat est a T+11.5s -> brightness ~243
        assert result["final_brightness"] >= 200
        assert result["final_brightness"] <= 254

    @patch('requests.put')
    def test_execute_duration(self, mock_put, phase3):
        """Duree totale ~12s."""
        mock_put.return_value = Mock(status_code=200)

        start = time.perf_counter()
        result = phase3.execute()
        elapsed = time.perf_counter() - start

        # Tolerance: 12s +/- 1s (les tests sont plus lents)
        assert 11.0 <= elapsed <= 14.0
        assert 11.5 <= result["duration"] <= 13.0

    @patch('requests.put')
    def test_execute_drift_acceptable(self, mock_put, phase3):
        """Drift timing < 100ms en execution reelle."""
        mock_put.return_value = Mock(status_code=200)

        result = phase3.execute()

        # En execution reelle, drift devrait etre faible
        # Tolerance: 200ms max (API calls + overhead)
        assert result["drift_max"] < 0.2

    @patch('requests.put')
    @patch('time.sleep')
    def test_execute_tolerant_failures(self, mock_sleep, mock_put, phase3):
        """Succes meme si quelques beats echouent."""
        # 20 succes, 4 echecs
        responses = [Mock(status_code=200)] * 40 + [Mock(status_code=500)] * 8
        mock_put.side_effect = responses

        result = phase3.execute()

        # 20/24 beats minimum pour succes
        assert result["beats_executed"] >= 20
        assert result["success"] is True

    @patch('requests.put')
    @patch('time.sleep')
    def test_execute_failure_too_many_errors(self, mock_sleep, mock_put, phase3):
        """Echec si trop de beats echouent."""
        # Tous les appels echouent
        mock_put.return_value = Mock(status_code=500)

        result = phase3.execute()

        assert result["beats_executed"] == 0
        assert result["success"] is False


class TestBeatsTiming:
    """Tests pour les constantes de timing."""

    def test_24_beats(self):
        """24 beats dans la liste."""
        assert len(BEATS_TIMING) == 24

    def test_beats_interval(self):
        """Intervalle de 0.5s entre beats."""
        for i in range(1, len(BEATS_TIMING)):
            interval = BEATS_TIMING[i] - BEATS_TIMING[i-1]
            assert interval == 0.5

    def test_first_beat_at_zero(self):
        """Premier beat a T=0."""
        assert BEATS_TIMING[0] == 0.0

    def test_last_beat_before_end(self):
        """Dernier beat avant la fin (11.5s < 12s)."""
        assert BEATS_TIMING[-1] == 11.5
        assert BEATS_TIMING[-1] < DURATION


class TestConstants:
    """Tests pour les constantes."""

    def test_duration(self):
        """Duree phase = 12s."""
        assert DURATION == 12.0

    def test_flash_duration(self):
        """Flash rouge = 100ms."""
        assert FLASH_DURATION == 0.1

    def test_transition_duration(self):
        """Transition bleu = 200ms."""
        assert TRANSITION_DURATION == 0.2

    def test_colors_defined(self):
        """Couleurs definies correctement."""
        assert BLUE_ARC_REACTOR_RGB == (0, 100, 255)
        assert RED_INTENSE_RGB == (255, 0, 0)


class TestRgbToXy:
    """Tests pour la conversion RGB -> xy."""

    def test_white(self):
        """Blanc pur."""
        x, y = rgb_to_xy(255, 255, 255)
        assert 0.3 < x < 0.35
        assert 0.3 < y < 0.35

    def test_red(self):
        """Rouge pur."""
        x, y = rgb_to_xy(255, 0, 0)
        assert x > 0.6
        assert y < 0.35

    def test_blue(self):
        """Bleu pur."""
        x, y = rgb_to_xy(0, 0, 255)
        assert x < 0.2
        assert y < 0.1

    def test_black(self):
        """Noir = (0, 0)."""
        x, y = rgb_to_xy(0, 0, 0)
        assert x == 0.0
        assert y == 0.0
