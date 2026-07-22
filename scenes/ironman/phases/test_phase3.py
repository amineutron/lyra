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
        """hue_beat detecte l'audio: attente passive."""
        mock_put.return_value = Mock(status_code=200)
        with patch.object(phase3, "_hue_beat_running", return_value=True):
            with patch.object(phase3, "_hue_beat_beat_count", return_value=3):
                with patch.object(phase3, "_measure_video_position",
                                  return_value=None):
                    result = phase3.execute()
        assert result["mode"] == "hue_beat"
        assert result["success"] is True
        assert result["video_anchor"] == "estimated"

    @patch("requests.put")
    @patch("time.sleep")
    def test_execute_hue_beat_silent_drives_pulses(self, mock_sleep, mock_put, phase3):
        """hue_beat n'entend rien (YouTube sur TV): pulses pilotes."""
        mock_put.return_value = Mock(status_code=200)
        phase3.beats = [0.5, 1.0, 1.5]
        with patch.object(phase3, "_hue_beat_running", return_value=True):
            with patch.object(phase3, "_hue_beat_beat_count", return_value=0):
                with patch.object(phase3, "_measure_video_position",
                                  return_value=None):
                    with patch(
                        "scenes.ironman.phases.phase3_buildup.HUE_BEAT_OBSERVE_S", 0.0
                    ):
                        with patch.object(phase3, "_send_hue_beat_ctrl",
                                          return_value=True):
                            with patch.object(phase3, "_send_hue_beat_pulse",
                                              return_value=True) as mock_pulse:
                                result = phase3.execute()

        assert result["mode"] == "hue_beat_ctrl"
        assert result["beats_executed"] == 3
        assert mock_pulse.call_count == 3
        assert result["success"] is True

    @patch("requests.put")
    @patch("time.sleep")
    def test_execute_measured_anchor(self, mock_sleep, mock_put, phase3):
        """Position video mesuree: ancrage exact des beats."""
        mock_put.return_value = Mock(status_code=200)
        phase3.beats = []
        with patch.object(phase3, "_hue_beat_running", return_value=True):
            with patch.object(phase3, "_hue_beat_beat_count", return_value=0):
                with patch.object(phase3, "_measure_video_position",
                                  return_value=4.2):
                    with patch(
                        "scenes.ironman.phases.phase3_buildup.HUE_BEAT_OBSERVE_S", 0.0
                    ):
                        with patch.object(phase3, "_send_hue_beat_ctrl",
                                          return_value=True):
                            result = phase3.execute()

        assert result["video_anchor"] == "measured"


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


class TestHueBeatStateReading:
    """Lecture du state file hue_beat (validation PID)."""

    @pytest.fixture
    def phase3(self):
        with patch.object(Phase3Buildup, '_load_config', return_value={
            'hue': {'bridge_ip': '192.168.1.51', 'username': 'testuser'},
            'tv': {'host': '192.168.1.50'}
        }):
            return Phase3Buildup()

    def test_beat_count_valid_pid(self, phase3, tmp_path):
        import json as _json
        state = tmp_path / "state.json"
        pid = tmp_path / "pid"
        state.write_text(_json.dumps({"pid": 4242, "beat_count": 7}))
        pid.write_text("4242")
        with patch('scenes.ironman.phases.phase3_buildup.HUE_BEAT_STATE_FILE', state):
            with patch('scenes.ironman.phases.phase3_buildup.HUE_BEAT_PID_FILE', pid):
                assert phase3._hue_beat_beat_count() == 7

    def test_beat_count_stale_pid_ignored(self, phase3, tmp_path):
        """State d'un ancien run (PID different): compte comme 0."""
        import json as _json
        state = tmp_path / "state.json"
        pid = tmp_path / "pid"
        state.write_text(_json.dumps({"pid": 1111, "beat_count": 50}))
        pid.write_text("2222")
        with patch('scenes.ironman.phases.phase3_buildup.HUE_BEAT_STATE_FILE', state):
            with patch('scenes.ironman.phases.phase3_buildup.HUE_BEAT_PID_FILE', pid):
                assert phase3._hue_beat_beat_count() == 0

    def test_beat_count_missing_files(self, phase3, tmp_path):
        with patch('scenes.ironman.phases.phase3_buildup.HUE_BEAT_STATE_FILE',
                   tmp_path / "absent.json"):
            assert phase3._hue_beat_beat_count() == 0

    def test_send_pulse_writes_ctrl_file(self, phase3, tmp_path):
        import json as _json
        ctrl = tmp_path / "ctrl"
        with patch('scenes.ironman.phases.phase3_buildup.HUE_BEAT_CTRL_FILE', ctrl):
            assert phase3._send_hue_beat_pulse(0.8) is True
            assert _json.loads(ctrl.read_text()) == {"pulse": 0.8}


class TestDrivePulses:
    """Pilotage des pulses sur beats precalcules."""

    @pytest.fixture
    def phase3(self):
        with patch.object(Phase3Buildup, '_load_config', return_value={
            'hue': {'bridge_ip': '192.168.1.51', 'username': 'testuser'},
            'tv': {'host': '192.168.1.50'}
        }):
            return Phase3Buildup()

    def test_beats_after_deadline_not_sent(self, phase3):
        """Les beats au-dela de la fin de phase ne sont pas envoyes."""
        phase3.beats = [0.05, 0.10, 5.0, 9.0]
        now = time.perf_counter()
        with patch.object(phase3, '_send_hue_beat_ctrl', return_value=True):
            with patch.object(phase3, '_send_hue_beat_pulse',
                              return_value=True) as mock_pulse:
                sent = phase3._drive_hue_beat_pulses(
                    phase_start=now, deadline=now + 0.3
                )
        assert sent == 2
        assert mock_pulse.call_count == 2

    def test_setup_ctrl_sent_before_pulses(self, phase3):
        """floor + anchor off envoyes avant le premier pulse."""
        phase3.beats = [0.05]
        now = time.perf_counter()
        with patch.object(phase3, '_send_hue_beat_ctrl',
                          return_value=True) as mock_ctrl:
            with patch.object(phase3, '_send_hue_beat_pulse', return_value=True):
                phase3._drive_hue_beat_pulses(phase_start=now, deadline=now + 0.2)
        setup = mock_ctrl.call_args_list[0][0][0]
        assert setup["anchor"] is False
        assert setup["floor"] > 0

    def test_intensity_follows_pattern(self, phase3):
        """L'intensite suit le pattern cyclique (groove, pas de strobe)."""
        from .phase3_buildup import CTRL_INTENSITY_PATTERN
        phase3.beats = [0.01, 0.02, 0.03, 0.04, 0.05]
        now = time.perf_counter()
        with patch.object(phase3, '_send_hue_beat_ctrl', return_value=True):
            with patch.object(phase3, '_send_hue_beat_pulse',
                              return_value=True) as mock_pulse:
                phase3._drive_hue_beat_pulses(phase_start=now, deadline=now + 1.0)
        intensities = [c[0][0] for c in mock_pulse.call_args_list]
        expected = [CTRL_INTENSITY_PATTERN[i % len(CTRL_INTENSITY_PATTERN)]
                    for i in range(5)]
        assert intensities == expected


class TestMeasureVideoPosition:
    """Mesure de la position de lecture YouTube via ADB."""

    @pytest.fixture
    def phase3(self):
        with patch.object(Phase3Buildup, '_load_config', return_value={
            'hue': {'bridge_ip': '192.168.1.51', 'username': 'testuser'},
            'tv': {'host': '192.168.1.50'}
        }):
            return Phase3Buildup()

    def _dumpsys(self, state=3, position=8500, speed=1.0, updated=1000000):
        return (
            "  package=com.google.android.youtube.tv\n"
            "  active=true\n"
            f"  state=PlaybackState {{state={state}, position={position}, "
            f"buffered position=0, speed={speed}, updated={updated}, "
            "actions=382, custom actions=[], active item id=-1, error=null}\n"
            "---UPTIME---\n"
            "1002.50 4000.00\n"
        )

    def test_playing_returns_position(self, phase3):
        """state=3 (lecture): position = position + delta uptime."""
        with patch('shutil.which', return_value='/usr/bin/adb'):
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = Mock(
                    returncode=0,
                    stdout=self._dumpsys(state=3, position=8500,
                                         updated=1000000)
                )
                pos = phase3._measure_video_position()
        # 8500ms + (1002500 - 1000000)ms * 1.0 = 11000ms
        assert pos == pytest.approx(11.0, abs=0.01)

    def test_paused_returns_none(self, phase3):
        with patch('shutil.which', return_value='/usr/bin/adb'):
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = Mock(
                    returncode=0, stdout=self._dumpsys(state=2)
                )
                assert phase3._measure_video_position() is None

    def test_no_youtube_session_returns_none(self, phase3):
        with patch('shutil.which', return_value='/usr/bin/adb'):
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = Mock(
                    returncode=0,
                    stdout="package=org.droidtv.playtv\n---UPTIME---\n100.0 50.0\n"
                )
                assert phase3._measure_video_position() is None

    def test_no_adb_returns_none(self, phase3):
        with patch('shutil.which', return_value=None):
            assert phase3._measure_video_position() is None

    def test_absurd_position_rejected(self, phase3):
        """Position > 300s: session residuelle, rejetee."""
        with patch('shutil.which', return_value='/usr/bin/adb'):
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = Mock(
                    returncode=0,
                    stdout=self._dumpsys(state=3, position=900000,
                                         updated=1002500)
                )
                assert phase3._measure_video_position() is None


class TestSendCtrlAtomic:
    """Ecriture atomique du CTRL_FILE."""

    @pytest.fixture
    def phase3(self):
        with patch.object(Phase3Buildup, '_load_config', return_value={
            'hue': {'bridge_ip': '192.168.1.51', 'username': 'testuser'},
            'tv': {'host': '192.168.1.50'}
        }):
            return Phase3Buildup()

    def test_ctrl_written_via_tmp_rename(self, phase3, tmp_path):
        import json as _json
        ctrl = tmp_path / "ctrl"
        with patch('scenes.ironman.phases.phase3_buildup.HUE_BEAT_CTRL_FILE', ctrl):
            assert phase3._send_hue_beat_ctrl({"floor": 0.22}) is True
            assert _json.loads(ctrl.read_text()) == {"floor": 0.22}
            # le fichier temporaire ne traine pas
            assert not (tmp_path / "ctrl.tmp").exists()
