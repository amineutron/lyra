"""
Tests unitaires pour MusicAnticipator (anticipation musique blackout)
=====================================================================

Usage:
    pytest scenes/ironman/phases/test_music_anticipator.py -v
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Add parent dir to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from music_anticipator import MusicAnticipator, _adb_path


@pytest.fixture
def anticipator():
    return MusicAnticipator(
        tv_host="192.168.1.50", tv_auth=None,
        video_id="test1234567", tv_power="On",
    )


class TestAdbPath:

    def test_adb_in_path(self):
        with patch('music_anticipator.shutil.which', return_value='/usr/bin/adb'):
            assert _adb_path() == '/usr/bin/adb'

    def test_adb_missing(self):
        with patch('music_anticipator.shutil.which', return_value=None):
            with patch('music_anticipator.os.path.exists', return_value=False):
                assert _adb_path() is None


class TestRun:

    def test_tv_on_uses_screensaver_not_powercycle(self, anticipator):
        """TV allumee: screensaver ADB, jamais de power-cycle."""
        with patch.object(anticipator, '_blank_screen', return_value=True) as mock_blank:
            with patch.object(anticipator, '_power_on_tv') as mock_power:
                with patch.object(anticipator, '_launch_youtube_adb', return_value=True):
                    with patch('time.sleep'):
                        anticipator._run()

        mock_blank.assert_called_once()
        mock_power.assert_not_called()
        assert anticipator.music_started is True
        assert anticipator.music_method == "adb"
        assert anticipator.launch_time is not None
        assert anticipator.done.is_set()

    def test_tv_off_powers_on(self):
        """TV eteinte: power-on pendant le blackout."""
        a = MusicAnticipator("h", None, "test1234567", tv_power="Standby")
        with patch.object(a, '_power_on_tv', return_value=True) as mock_power:
            with patch.object(a, '_blank_screen') as mock_blank:
                with patch.object(a, '_launch_youtube_adb', return_value=True):
                    with patch('time.sleep'):
                        a._run()

        mock_power.assert_called_once()
        mock_blank.assert_not_called()

    def test_adb_failure_leaves_music_not_started(self, anticipator):
        """Echec ADB: music_started False, done quand meme signale."""
        with patch.object(anticipator, '_blank_screen', return_value=True):
            with patch.object(anticipator, '_launch_youtube_adb', return_value=False):
                with patch('time.sleep'):
                    anticipator._run()

        assert anticipator.music_started is False
        assert anticipator.launch_time is None
        assert anticipator.done.is_set()

    def test_exception_sets_done(self, anticipator):
        """Une exception ne bloque jamais done (la Phase 2 attend dessus)."""
        with patch.object(anticipator, '_blank_screen', side_effect=OSError("boom")):
            anticipator._run()

        assert anticipator.done.is_set()
        assert anticipator.music_started is False


class TestLaunchYoutubeAdb:

    def test_success(self, anticipator):
        with patch('music_anticipator._adb_path', return_value='/usr/bin/adb'):
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0, stdout="Starting: Intent", stderr=""
                )
                assert anticipator._launch_youtube_adb() is True
                # connect + am start
                assert mock_run.call_count == 2
                am_start_args = mock_run.call_args_list[1][0][0]
                assert "android.intent.action.VIEW" in am_start_args
                assert "test1234567" in " ".join(am_start_args)

    def test_no_adb(self, anticipator):
        with patch('music_anticipator._adb_path', return_value=None):
            assert anticipator._launch_youtube_adb() is False

    def test_adb_error_output(self, anticipator):
        """returncode 0 mais 'Error' dans stdout: echec."""
        with patch('music_anticipator._adb_path', return_value='/usr/bin/adb'):
            with patch('subprocess.run') as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0, stdout="Error: activity not found", stderr=""
                )
                assert anticipator._launch_youtube_adb() is False

    def test_timeout(self, anticipator):
        import subprocess as sp
        with patch('music_anticipator._adb_path', return_value='/usr/bin/adb'):
            with patch('subprocess.run', side_effect=sp.TimeoutExpired("adb", 8)):
                assert anticipator._launch_youtube_adb() is False
