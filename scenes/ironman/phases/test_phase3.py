import time
from unittest.mock import Mock, patch
import pytest
from .phase3_buildup import (
    Phase3Buildup,
    PHASE_DURATION,
    FLASH_DURATION,
    BLUE_ARC_REACTOR_RGB,
    RED_INTENSE_RGB,
    rgb_to_xy,
)

class TestPhase3Buildup:
    @pytest.fixture
    def phase3(self):
        with patch.object(Phase3Buildup, "_load_config") as mock_config:
            mock_config.return_value = {"hue": {"bridge_ip": "192.168.1.51", "username": "test"}}
            with patch.object(Phase3Buildup, "_load_beats", return_value=[i * 0.638 for i in range(24)]):
                return Phase3Buildup()

    def test_calculate_brightness_at_zero(self, phase3):
        assert phase3._calculate_brightness(0.0) == 0

    def test_calculate_brightness_at_half(self, phase3):
        assert phase3._calculate_brightness(0.5) == 127

    def test_calculate_brightness_at_full(self, phase3):
        assert phase3._calculate_brightness(1.0) == 254

    def test_calculate_brightness_clamped_negative(self, phase3):
        assert phase3._calculate_brightness(-0.5) == 0

    def test_calculate_brightness_clamped_overflow(self, phase3):
        assert phase3._calculate_brightness(2.0) == 254

    def test_calculate_brightness_quarter(self, phase3):
        b = phase3._calculate_brightness(0.25)
        assert abs(b - 63) <= 1

    def test_calculate_brightness_threequarters(self, phase3):
        b = phase3._calculate_brightness(0.75)
        assert abs(b - 190) <= 1

    @patch("requests.put")
    def test_execute_beat_calls_hue(self, mock_put, phase3):
        mock_put.return_value = Mock(status_code=200)
        with patch("time.sleep"):
            result = phase3._execute_beat()
        assert result is True
        assert mock_put.call_count >= 1

    @patch("requests.put")
    def test_execute_beat_flash_rouge(self, mock_put, phase3):
        mock_put.return_value = Mock(status_code=200)
        with patch("time.sleep"):
            phase3._execute_beat()
        first_call = mock_put.call_args_list[0]
        payload = first_call.kwargs.get("json") or first_call[1].get("json")
        xy_rouge = rgb_to_xy(*RED_INTENSE_RGB)
        assert payload["bri"] == 254
        assert payload["transitiontime"] == 0

    @patch("requests.put")
    @patch("time.sleep")
    def test_execute_success_with_beats(self, mock_sleep, mock_put, phase3):
        mock_put.return_value = Mock(status_code=200)
        with patch.object(phase3, "_hue_beat_running", return_value=False):
            result = phase3.execute()
        assert "beats_executed" in result
        assert result["success"] is True
        assert result["beats_executed"] >= 0

    @patch("requests.put")
    @patch("time.sleep")
    def test_execute_returns_duration(self, mock_sleep, mock_put, phase3):
        mock_put.return_value = Mock(status_code=200)
        with patch.object(phase3, "_hue_beat_running", return_value=False):
            result = phase3.execute()
        assert "duration" in result
        assert result["duration"] >= 0

    @patch("requests.put")
    @patch("time.sleep")
    def test_execute_hue_beat_mode(self, mock_sleep, mock_put, phase3):
        mock_put.return_value = Mock(status_code=200)
        with patch.object(phase3, "_hue_beat_running", return_value=True):
            result = phase3.execute()
        assert result["mode"] == "hue_beat"
        assert result["success"] is True


class TestConstants:
    def test_phase_duration(self):
        assert PHASE_DURATION == 12.0

    def test_flash_duration(self):
        assert FLASH_DURATION == 0.08

    def test_colors_defined(self):
        assert BLUE_ARC_REACTOR_RGB == (0, 0, 255)
        assert RED_INTENSE_RGB == (255, 0, 0)


class TestRgbToXy:
    def test_white(self):
        x, y = rgb_to_xy(255, 255, 255)
        assert 0.3 < x < 0.4
        assert 0.3 < y < 0.4

    def test_red(self):
        x, y = rgb_to_xy(255, 0, 0)
        assert x > 0.6

    def test_blue(self):
        x, y = rgb_to_xy(0, 0, 255)
        assert x < 0.2

    def test_black(self):
        x, y = rgb_to_xy(0, 0, 0)
        assert x == 0.0 and y == 0.0
