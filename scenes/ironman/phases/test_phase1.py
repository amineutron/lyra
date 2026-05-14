"""
Tests unitaires pour Phase 1 - Blackout Dramatique
==================================================

Usage:
    pytest scenes/ironman/phases/test_phase1.py -v
"""

import sys
import time
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import requests

# Add parent dir to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from phase1_blackout import Phase1Blackout, BLACKOUT_DURATION, MAX_EXTINCTION_LATENCY_MS


# =============================================================================
# Tests _turn_off_lights
# =============================================================================

class TestTurnOffLights:
    """Tests pour l'extinction des lumieres."""

    @pytest.fixture
    def phase1(self):
        with patch.object(Phase1Blackout, '_load_config', return_value={
            'hue': {'bridge_ip': '192.168.1.51', 'username': 'testuser'}
        }):
            return Phase1Blackout()

    def test_lights_off_success(self, phase1):
        """Extinction reussie."""
        with patch('requests.put') as mock_put:
            mock_put.return_value = MagicMock(status_code=200)
            success, latency = phase1._turn_off_lights()

            assert success is True
            assert latency > 0
            mock_put.assert_called_once()

    def test_lights_off_timeout(self, phase1):
        """Timeout lors de l'extinction."""
        with patch('requests.put') as mock_put:
            mock_put.side_effect = requests.exceptions.Timeout()
            success, latency = phase1._turn_off_lights()

            assert success is False

    def test_lights_off_http_error(self, phase1):
        """Erreur HTTP lors de l'extinction."""
        with patch('requests.put') as mock_put:
            mock_put.return_value = MagicMock(status_code=500)
            success, latency = phase1._turn_off_lights()

            assert success is False

    def test_lights_off_no_username(self):
        """Configuration Hue manquante."""
        with patch.object(Phase1Blackout, '_load_config', return_value={
            'hue': {'bridge_ip': '192.168.1.51'}  # pas de username
        }):
            phase1 = Phase1Blackout()
            success, latency = phase1._turn_off_lights()

            assert success is False

    def test_lights_off_transitiontime_zero(self, phase1):
        """Verifie que transitiontime=0 (instantane)."""
        with patch('requests.put') as mock_put:
            mock_put.return_value = MagicMock(status_code=200)
            phase1._turn_off_lights()

            # Verifier le payload
            call_args = mock_put.call_args
            payload = call_args.kwargs.get('json') or call_args[1].get('json')
            assert payload.get('transitiontime') == 0


# =============================================================================
# Tests _turn_off_tv
# =============================================================================

class TestTurnOffTV:
    """Tests pour l'extinction de la TV."""

    @pytest.fixture
    def phase1(self):
        with patch.object(Phase1Blackout, '_load_config', return_value={
            'tv': {'host': '192.168.1.50', 'user': 'test', 'pass': 'pass'}
        }):
            return Phase1Blackout()

    def test_tv_on_turns_off(self, phase1):
        """TV allumee -> eteinte."""
        with patch.object(phase1, '_check_tv_power', return_value='On'):
            with patch('requests.put') as mock_put:
                mock_put.return_value = MagicMock(status_code=200)
                success, action = phase1._turn_off_tv()

                assert success is True
                assert action == "off"

    def test_tv_already_standby_skipped(self, phase1):
        """TV deja en veille -> skip."""
        with patch.object(phase1, '_check_tv_power', return_value='Standby'):
            success, action = phase1._turn_off_tv()

            assert success is True
            assert action == "skipped"

    def test_tv_unknown_state_tries_off(self, phase1):
        """Etat TV inconnu -> tente extinction quand meme."""
        with patch.object(phase1, '_check_tv_power', return_value='unknown'):
            with patch('requests.put') as mock_put:
                mock_put.return_value = MagicMock(status_code=200)
                success, action = phase1._turn_off_tv()

                assert success is True
                assert action == "off"
                mock_put.assert_called_once()

    def test_tv_off_timeout(self, phase1):
        """Timeout lors de l'extinction TV."""
        with patch.object(phase1, '_check_tv_power', return_value='On'):
            with patch('requests.put') as mock_put:
                mock_put.side_effect = requests.exceptions.Timeout()
                success, action = phase1._turn_off_tv()

                assert success is False
                assert action == "error"

    def test_tv_off_http_error(self, phase1):
        """Erreur HTTP lors de l'extinction TV."""
        with patch.object(phase1, '_check_tv_power', return_value='On'):
            with patch('requests.put') as mock_put:
                mock_put.return_value = MagicMock(status_code=500)
                success, action = phase1._turn_off_tv()

                assert success is False
                assert action == "error"


# =============================================================================
# Tests execute (Phase complete)
# =============================================================================

class TestExecute:
    """Tests pour l'execution complete de la phase."""

    @pytest.fixture
    def phase1(self):
        with patch.object(Phase1Blackout, '_load_config', return_value={
            'tv': {'host': '192.168.1.50', 'user': 'test', 'pass': 'pass'},
            'hue': {'bridge_ip': '192.168.1.51', 'username': 'testuser'}
        }):
            return Phase1Blackout()

    def test_execute_all_success(self, phase1):
        """Execution complete avec succes."""
        with patch.object(phase1, '_turn_off_lights', return_value=(True, 50.0)):
            with patch.object(phase1, '_turn_off_tv', return_value=(True, "off")):
                with patch('time.sleep'):  # Skip actual sleep
                    result = phase1.execute()

                    assert result["success"] is True
                    assert result["lights_off"] is True
                    assert result["tv_off"] is True
                    assert result["tv_action"] == "off"

    def test_execute_lights_fail_continues(self, phase1):
        """Erreur lumieres -> continue quand meme."""
        with patch.object(phase1, '_turn_off_lights', return_value=(False, 100.0)):
            with patch.object(phase1, '_turn_off_tv', return_value=(True, "off")):
                with patch('time.sleep'):
                    result = phase1.execute()

                    # Success car TV OK
                    assert result["success"] is True
                    assert result["lights_off"] is False
                    assert result["tv_off"] is True

    def test_execute_tv_fail_continues(self, phase1):
        """Erreur TV -> continue quand meme."""
        with patch.object(phase1, '_turn_off_lights', return_value=(True, 50.0)):
            with patch.object(phase1, '_turn_off_tv', return_value=(False, "error")):
                with patch('time.sleep'):
                    result = phase1.execute()

                    # Success car lumieres OK
                    assert result["success"] is True
                    assert result["lights_off"] is True
                    assert result["tv_off"] is False

    def test_execute_all_fail(self, phase1):
        """Tout echoue -> success=False."""
        with patch.object(phase1, '_turn_off_lights', return_value=(False, 100.0)):
            with patch.object(phase1, '_turn_off_tv', return_value=(False, "error")):
                with patch('time.sleep'):
                    result = phase1.execute()

                    assert result["success"] is False

    def test_execute_duration_correct(self, phase1):
        """Duree exacte 3.0s (avec tolerance)."""
        with patch.object(phase1, '_turn_off_lights', return_value=(True, 10.0)):
            with patch.object(phase1, '_turn_off_tv', return_value=(True, "off")):
                # Ne pas mocker time.sleep pour tester la vraie duree
                result = phase1.execute()

                # Tolerance: ±100ms (plus large pour les tests)
                assert abs(result["duration"] - BLACKOUT_DURATION) < 0.1

    def test_execute_returns_latency(self, phase1):
        """Verifie que la latence est retournee."""
        with patch.object(phase1, '_turn_off_lights', return_value=(True, 42.5)):
            with patch.object(phase1, '_turn_off_tv', return_value=(True, "off")):
                with patch('time.sleep'):
                    result = phase1.execute()

                    assert result["latency_ms"] == 42.5


# =============================================================================
# Tests de performance
# =============================================================================

class TestPerformance:
    """Tests de performance."""

    @pytest.fixture
    def phase1(self):
        with patch.object(Phase1Blackout, '_load_config', return_value={
            'tv': {'host': '192.168.1.50', 'user': 'test', 'pass': 'pass'},
            'hue': {'bridge_ip': '192.168.1.51', 'username': 'testuser'}
        }):
            return Phase1Blackout()

    def test_latency_under_500ms(self, phase1):
        """Latence extinction < 500ms."""
        with patch('requests.put') as mock_put:
            # Simuler une reponse rapide
            mock_put.return_value = MagicMock(status_code=200)
            success, latency = phase1._turn_off_lights()

            assert latency < MAX_EXTINCTION_LATENCY_MS


# =============================================================================
# Run tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
