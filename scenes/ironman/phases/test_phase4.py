"""
Tests pour Phase 4 - Transition & Stabilisation
"""

import time
from unittest.mock import Mock, patch, MagicMock
import pytest

from .phase4_transition import (
    Phase4Transition,
    DURATION,
    SLOWDOWN_BEATS,
    FADE_START,
    MUSIC_STOP,
    STABLE_BRIGHTNESS,
    FLASH_DURATION,
    rgb_to_xy,
)


class TestPhase4Transition:
    """Tests pour la classe Phase4Transition."""

    @pytest.fixture
    def phase4(self):
        """Cree une instance Phase4 avec config mockee."""
        with patch.object(Phase4Transition, '_load_config') as mock_config:
            mock_config.return_value = {
                "hue": {
                    "bridge_ip": "192.168.1.51",
                    "username": "test-user-123"
                },
                "tv": {
                    "host": "192.168.1.50",
                    "user": "test-user",
                    "pass": "test-pass"
                }
            }
            return Phase4Transition()

    @patch('requests.put')
    def test_slowdown_beats_count(self, mock_put, phase4):
        """Execute 5 beats ralentis."""
        mock_put.return_value = Mock(status_code=200)

        beats = phase4._slowdown_beats()

        assert beats == 5

    @patch('requests.put')
    def test_slowdown_beats_timing(self, mock_put, phase4):
        """Beats espacés correctement (0.0, 0.5, 1.2, 2.0, 3.0)."""
        mock_put.return_value = Mock(status_code=200)
        timestamps = []

        original_execute_beat = phase4._execute_beat

        def track_beat(*args, **kwargs):
            timestamps.append(time.perf_counter())
            return original_execute_beat(*args, **kwargs)

        phase4._execute_beat = track_beat

        start = time.perf_counter()
        phase4._slowdown_beats()

        # Verifier les espacements
        relative_times = [t - start for t in timestamps]

        # Tolerence de 100ms
        assert abs(relative_times[0] - 0.0) < 0.15
        assert abs(relative_times[1] - 0.5) < 0.15
        assert abs(relative_times[2] - 1.2) < 0.15
        assert abs(relative_times[3] - 2.0) < 0.15
        assert abs(relative_times[4] - 3.0) < 0.15

    @patch('requests.put')
    def test_fade_to_stable(self, mock_put, phase4):
        """Fondu vers brightness 150."""
        mock_put.return_value = Mock(status_code=200)

        result = phase4._fade_to_stable()

        assert result is True
        # Verifier payload
        call_args = mock_put.call_args
        payload = call_args.kwargs.get('json') or call_args[1].get('json')
        assert payload["bri"] == STABLE_BRIGHTNESS
        assert payload["transitiontime"] == 20  # 2 secondes

    @patch('subprocess.run')
    @patch('os.path.exists')
    def test_stop_music_adb_pause(self, mock_exists, mock_run, phase4):
        """Arret musique via ADB pause."""
        mock_exists.return_value = True
        mock_run.return_value = Mock(returncode=0)

        result = phase4._stop_music()

        assert result is True
        # Verifier keycode MEDIA_PAUSE
        call_args = mock_run.call_args[0][0]
        assert "127" in call_args  # MEDIA_PAUSE keycode

    @patch('subprocess.run')
    @patch('os.path.exists')
    @patch('requests.post')
    def test_stop_music_fallback_volume(self, mock_post, mock_exists, mock_run, phase4):
        """Fallback volume 0 si ADB echoue."""
        mock_exists.return_value = True
        mock_run.return_value = Mock(returncode=1)  # ADB echoue
        mock_post.return_value = Mock(status_code=200)

        result = phase4._stop_music()

        assert result is True
        # Verifier volume 0
        call_args = mock_post.call_args
        payload = call_args.kwargs.get('json') or call_args[1].get('json')
        assert payload["current"] == 0

    @patch('subprocess.run')
    @patch('os.path.exists')
    @patch('requests.post')
    @patch('requests.put')
    def test_stop_music_fallback_poweroff(self, mock_put, mock_post, mock_exists, mock_run, phase4):
        """Fallback power off si tout echoue."""
        mock_exists.return_value = True
        mock_run.return_value = Mock(returncode=1)  # ADB echoue
        mock_post.return_value = Mock(status_code=500)  # Volume echoue
        mock_put.return_value = Mock(status_code=200)

        result = phase4._stop_music()

        assert result is True
        # Verifier powerstate Standby
        call_args = mock_put.call_args
        payload = call_args.kwargs.get('json') or call_args[1].get('json')
        assert payload["powerstate"] == "Standby"

    @patch('requests.put')
    def test_execute_duration(self, mock_put, phase4):
        """Duree totale ~7s."""
        mock_put.return_value = Mock(status_code=200)

        with patch.object(phase4, '_stop_music', return_value=True):
            result = phase4.execute()

        # Tolerance: 7s +/- 0.5s
        assert 6.5 <= result["duration"] <= 7.5

    @patch('requests.put')
    def test_execute_success(self, mock_put, phase4):
        """Succes si fade OK."""
        mock_put.return_value = Mock(status_code=200)

        with patch.object(phase4, '_stop_music', return_value=True):
            result = phase4.execute()

        assert result["success"] is True
        assert result["fade_ok"] is True
        assert result["beats_executed"] == 5

    @patch('requests.put')
    def test_execute_music_stopped(self, mock_put, phase4):
        """Musique arretee."""
        mock_put.return_value = Mock(status_code=200)

        with patch.object(phase4, '_stop_music', return_value=True):
            result = phase4.execute()

        assert result["music_stopped"] is True

    @patch('requests.put')
    def test_execute_continues_if_music_fails(self, mock_put, phase4):
        """Continue meme si musique pas arretee."""
        mock_put.return_value = Mock(status_code=200)

        with patch.object(phase4, '_stop_music', return_value=False):
            result = phase4.execute()

        assert result["success"] is True  # Succes car fade OK
        assert result["music_stopped"] is False


class TestSlowdownBeats:
    """Tests pour les constantes de ralentissement."""

    def test_5_beats(self):
        """5 beats dans la liste."""
        assert len(SLOWDOWN_BEATS) == 5

    def test_increasing_intervals(self):
        """Intervalles croissants."""
        intervals = []
        for i in range(1, len(SLOWDOWN_BEATS)):
            intervals.append(SLOWDOWN_BEATS[i] - SLOWDOWN_BEATS[i-1])

        # 0.5, 0.7, 0.8, 1.0 - croissant
        assert intervals[0] == 0.5
        assert intervals[1] == 0.7
        assert intervals[2] == 0.8
        assert intervals[3] == 1.0

    def test_last_beat_at_3s(self):
        """Dernier beat a 3.0s."""
        assert SLOWDOWN_BEATS[-1] == 3.0


class TestConstants:
    """Tests pour les constantes."""

    def test_duration(self):
        """Duree phase = 7s."""
        assert DURATION == 7.0

    def test_fade_start(self):
        """Debut fondu = 3s."""
        assert FADE_START == 3.0

    def test_music_stop(self):
        """Arret musique = 4s."""
        assert MUSIC_STOP == 4.0

    def test_stable_brightness(self):
        """Brightness stable = 150."""
        assert STABLE_BRIGHTNESS == 150
