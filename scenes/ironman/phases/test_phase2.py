"""
Tests unitaires pour Phase 2 - Premier Impact
=============================================

Usage:
    pytest scenes/ironman/phases/test_phase2.py -v
"""

import sys
import time
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import requests

# Add parent dir to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from phase2_impact import (
    Phase2Impact,
    rgb_to_xy,
    YOUTUBE_VIDEO_ID,
    FLASH_DURATION,
    BLUE_TRANSITION,
    PHASE_DURATION,
    WHITE_RGB,
    BLUE_ARC_REACTOR_RGB,
)


# =============================================================================
# Tests rgb_to_xy
# =============================================================================

class TestRgbToXy:
    """Tests pour la conversion RGB -> xy."""

    def test_white(self):
        """Blanc pur."""
        x, y = rgb_to_xy(255, 255, 255)
        assert 0.3 < x < 0.4  # Approximativement
        assert 0.3 < y < 0.4

    def test_red(self):
        """Rouge pur."""
        x, y = rgb_to_xy(255, 0, 0)
        assert x > 0.6  # Rouge = x eleve

    def test_blue(self):
        """Bleu pur."""
        x, y = rgb_to_xy(0, 0, 255)
        assert x < 0.2  # Bleu = x faible
        assert y < 0.1  # Bleu = y faible

    def test_black(self):
        """Noir = (0, 0)."""
        x, y = rgb_to_xy(0, 0, 0)
        assert x == 0.0
        assert y == 0.0


# =============================================================================
# Tests _flash_white
# =============================================================================

class TestFlashWhite:
    """Tests pour le flash blanc."""

    @pytest.fixture
    def phase2(self):
        with patch.object(Phase2Impact, '_load_config', return_value={
            'hue': {'bridge_ip': '192.168.1.51', 'username': 'testuser'}
        }):
            return Phase2Impact()

    def test_flash_white_success(self, phase2):
        """Flash blanc reussi."""
        with patch.object(phase2, '_set_hue_group_state', return_value=True):
            with patch('time.sleep'):
                success = phase2._flash_white()
                assert success is True

    def test_flash_white_calls_correct_params(self, phase2):
        """Verifie les parametres du flash."""
        with patch.object(phase2, '_set_hue_group_state', return_value=True) as mock:
            with patch('time.sleep'):
                phase2._flash_white()
                mock.assert_called_once_with(
                    brightness=254,
                    rgb=WHITE_RGB,
                    transition_time=0
                )

    def test_flash_white_failure(self, phase2):
        """Flash echoue gracieusement."""
        with patch.object(phase2, '_set_hue_group_state', return_value=False):
            success = phase2._flash_white()
            assert success is False


# =============================================================================
# Tests _transition_to_blue
# =============================================================================

class TestTransitionBlue:
    """Tests pour la transition bleu."""

    @pytest.fixture
    def phase2(self):
        with patch.object(Phase2Impact, '_load_config', return_value={
            'hue': {'bridge_ip': '192.168.1.51', 'username': 'testuser'}
        }):
            return Phase2Impact()

    def test_transition_blue_success(self, phase2):
        """Transition bleu reussie."""
        with patch.object(phase2, '_set_hue_group_state', return_value=True):
            with patch('time.sleep'):
                success = phase2._transition_to_blue()
                assert success is True

    def test_transition_blue_correct_color(self, phase2):
        """Verifie la couleur bleu arc reactor."""
        with patch.object(phase2, '_set_hue_group_state', return_value=True) as mock:
            with patch('time.sleep'):
                phase2._transition_to_blue()
                mock.assert_called_once_with(
                    brightness=200,
                    rgb=BLUE_ARC_REACTOR_RGB,
                    transition_time=3  # 300ms
                )


# =============================================================================
# Tests _power_on_tv
# =============================================================================

class TestPowerOnTV:
    """Tests pour l'allumage TV."""

    @pytest.fixture
    def phase2(self):
        with patch.object(Phase2Impact, '_load_config', return_value={
            'tv': {'host': '192.168.1.50', 'user': 'test', 'pass': 'pass'}
        }):
            return Phase2Impact()

    def test_tv_power_on_success(self, phase2):
        """TV s'allume."""
        with patch('requests.put') as mock_put:
            mock_put.return_value = MagicMock(status_code=200)
            success = phase2._power_on_tv()
            assert success is True

    def test_tv_power_on_failure(self, phase2):
        """TV ne s'allume pas."""
        with patch('requests.put') as mock_put:
            mock_put.return_value = MagicMock(status_code=500)
            success = phase2._power_on_tv()
            assert success is False

    def test_tv_power_on_timeout(self, phase2):
        """Timeout TV."""
        with patch('requests.put') as mock_put:
            mock_put.side_effect = requests.exceptions.Timeout()
            success = phase2._power_on_tv()
            assert success is False


# =============================================================================
# Tests _launch_youtube
# =============================================================================

class TestLaunchYouTube:
    """Tests pour le lancement YouTube."""

    @pytest.fixture
    def phase2(self):
        with patch.object(Phase2Impact, '_load_config', return_value={
            'tv': {'host': '192.168.1.50'}
        }):
            return Phase2Impact()

    def test_youtube_success(self, phase2):
        """YouTube lance avec succes."""
        with patch('os.path.exists', return_value=True):
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                success = phase2._launch_youtube("test123")
                assert success is True

    def test_youtube_no_catt(self, phase2):
        """catt non disponible."""
        with patch('os.path.exists', return_value=False):
            success = phase2._launch_youtube("test123")
            assert success is False

    def test_youtube_catt_failure_no_retry(self, phase2):
        """Echec catt: retourne False sans retry (un seul appel)."""
        with patch('os.path.exists', return_value=True):
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=1, stderr="error", stdout=""
                )
                success = phase2._launch_youtube("test123")
                assert success is False
                assert mock_run.call_count == 1

    def test_youtube_timeout(self, phase2):
        """Timeout YouTube."""
        import subprocess
        with patch('os.path.exists', return_value=True):
            with patch('subprocess.run') as mock_run:
                mock_run.side_effect = subprocess.TimeoutExpired("cmd", 10)
                success = phase2._launch_youtube("test123", retry=False)
                assert success is False


# =============================================================================
# Tests _activate_ambilight
# =============================================================================

class TestActivateAmbilight:
    """Tests pour l'activation Ambilight."""

    @pytest.fixture
    def phase2(self):
        with patch.object(Phase2Impact, '_load_config', return_value={
            'tv': {'host': '192.168.1.50', 'user': 'test', 'pass': 'pass'}
        }):
            return Phase2Impact()

    def test_ambilight_success(self, phase2):
        """Ambilight active."""
        with patch('requests.post') as mock_post:
            mock_post.return_value = MagicMock(status_code=200)
            success = phase2._activate_ambilight()
            assert success is True

    def test_ambilight_failure(self, phase2):
        """Ambilight echoue."""
        with patch('requests.post') as mock_post:
            mock_post.return_value = MagicMock(status_code=500)
            success = phase2._activate_ambilight()
            assert success is False


# =============================================================================
# Tests execute
# =============================================================================

class TestExecute:
    """Tests pour l'execution complete."""

    @pytest.fixture
    def phase2(self):
        with patch.object(Phase2Impact, '_load_config', return_value={
            'tv': {'host': '192.168.1.50', 'user': 'test', 'pass': 'pass'},
            'hue': {'bridge_ip': '192.168.1.51', 'username': 'testuser'}
        }):
            return Phase2Impact()

    def test_execute_all_success(self, phase2):
        """Execution complete avec succes."""
        with patch.object(phase2, '_flash_white', return_value=True):
            with patch.object(phase2, '_transition_to_blue', return_value=True):
                with patch.object(phase2, '_power_on_tv', return_value=True):
                    with patch.object(phase2, '_launch_youtube', return_value=True):
                        with patch.object(phase2, '_activate_ambilight', return_value=True):
                            with patch('time.sleep'):
                                result = phase2.execute()

                                assert result["success"] is True
                                assert result["flash_ok"] is True
                                assert result["blue_ok"] is True
                                assert result["tv_on"] is True
                                assert result["music_started"] is True
                                assert result["ambilight_active"] is False  # execute() ne l appelle plus

    def test_execute_continues_without_music(self, phase2):
        """Continue sans musique si YouTube echoue."""
        with patch.object(phase2, '_flash_white', return_value=True):
            with patch.object(phase2, '_transition_to_blue', return_value=True):
                with patch.object(phase2, '_power_on_tv', return_value=True):
                    with patch.object(phase2, '_launch_youtube', return_value=False):
                        with patch.object(phase2, '_activate_ambilight') as mock_ambi:
                            with patch('time.sleep'):
                                result = phase2.execute()

                                # YouTube optionnel: flash_ok suffit => success=True
                                assert result["success"] is True
                                assert result["music_started"] is False
                                # Ambilight skip si pas de musique
                                mock_ambi.assert_not_called()
                                assert result["ambilight_active"] is False

    def test_execute_flash_fail_still_continues(self, phase2):
        """Continue meme si flash echoue."""
        with patch.object(phase2, '_flash_white', return_value=False):
            with patch.object(phase2, '_transition_to_blue', return_value=True):
                with patch.object(phase2, '_power_on_tv', return_value=True):
                    with patch.object(phase2, '_launch_youtube', return_value=True):
                        with patch.object(phase2, '_activate_ambilight', return_value=True):
                            with patch('time.sleep'):
                                result = phase2.execute()

                                # Success = flash_ok
                                assert result["success"] is False
                                assert result["flash_ok"] is False

    def test_execute_duration(self, phase2):
        """Duree environ 3.5s."""
        with patch.object(phase2, '_flash_white', return_value=True):
            with patch.object(phase2, '_transition_to_blue', return_value=True):
                with patch.object(phase2, '_power_on_tv', return_value=True):
                    with patch.object(phase2, '_launch_youtube', return_value=True):
                        with patch.object(phase2, '_activate_ambilight', return_value=True):
                            result = phase2.execute()

                            # Tolerance: ±200ms
                            assert abs(result["duration"] - PHASE_DURATION) < 0.2


# =============================================================================
# Run tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
