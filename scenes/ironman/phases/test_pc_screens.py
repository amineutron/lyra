"""
Tests unitaires pour PCScreenController (ecrans PC Hyprland)
============================================================

Usage:
    pytest scenes/ironman/phases/test_pc_screens.py -v
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Add parent dir to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from pc_screens import PCScreenController, ARM_DELAY_S


class TestDisabled:
    """Controleur desactive: no-op complet."""

    def test_disabled_turn_off_is_noop(self):
        ctrl = PCScreenController(enabled=False)
        with patch('subprocess.run') as mock_run:
            assert ctrl.turn_off() is False
            mock_run.assert_not_called()

    def test_hyprctl_missing_disables(self):
        with patch('pc_screens.shutil.which', return_value=None):
            ctrl = PCScreenController(enabled=True)
            assert ctrl.enabled is False
            with patch('subprocess.run') as mock_run:
                assert ctrl.turn_off() is False
                mock_run.assert_not_called()

    def test_disabled_wake_is_noop(self):
        ctrl = PCScreenController(enabled=False)
        with patch('subprocess.run') as mock_run:
            ctrl.wake()
            mock_run.assert_not_called()


class TestTurnOff:
    """Extinction des ecrans + watcher detache."""

    @pytest.fixture
    def ctrl(self):
        with patch('pc_screens.shutil.which', return_value='/usr/bin/hyprctl'):
            return PCScreenController(enabled=True)

    def test_turn_off_dispatches_dpms_off(self, ctrl):
        with patch('pc_screens._get_key_press_option', return_value=0):
            with patch('subprocess.run') as mock_run:
                with patch('subprocess.Popen') as mock_popen:
                    assert ctrl.turn_off() is True
                    args = mock_run.call_args[0][0]
                    assert args == ["hyprctl", "dispatch", "dpms", "off"]
                    mock_popen.assert_called_once()

    def test_watcher_script_arms_key_exit(self, ctrl):
        """Le watcher arme key_press_enables_dpms apres le delai."""
        with patch('pc_screens._get_key_press_option', return_value=0):
            with patch('subprocess.run'):
                with patch('subprocess.Popen') as mock_popen:
                    ctrl.turn_off()
                    script = mock_popen.call_args[0][0][2]
                    assert f"sleep {ARM_DELAY_S}" in script
                    assert "keyword misc:key_press_enables_dpms 1" in script
                    # Restauration de la valeur d'origine (0)
                    assert "keyword misc:key_press_enables_dpms 0" in script

    def test_watcher_script_restores_original_option(self, ctrl):
        """Si l'option etait deja a 1, elle est restauree a 1."""
        with patch('pc_screens._get_key_press_option', return_value=1):
            with patch('subprocess.run'):
                with patch('subprocess.Popen') as mock_popen:
                    ctrl.turn_off()
                    script = mock_popen.call_args[0][0][2]
                    assert script.strip().endswith(
                        "keyword misc:key_press_enables_dpms 1 >/dev/null"
                    )

    def test_auto_wake_in_watcher_script(self):
        """auto_wake_s present dans le script du watcher (mode test)."""
        with patch('pc_screens.shutil.which', return_value='/usr/bin/hyprctl'):
            ctrl = PCScreenController(enabled=True, auto_wake_s=60)
        with patch('pc_screens._get_key_press_option', return_value=0):
            with patch('subprocess.run'):
                with patch('subprocess.Popen') as mock_popen:
                    ctrl.turn_off()
                    script = mock_popen.call_args[0][0][2]
                    assert 'auto_wake="60"' in script
                    assert "dispatch dpms on" in script

    def test_no_auto_wake_in_production(self, ctrl):
        """Sans auto_wake_s, pas de rallumage force dans le script."""
        with patch('pc_screens._get_key_press_option', return_value=0):
            with patch('subprocess.run'):
                with patch('subprocess.Popen') as mock_popen:
                    ctrl.turn_off()
                    script = mock_popen.call_args[0][0][2]
                    assert 'auto_wake=""' in script

    def test_dpms_off_failure_returns_false(self, ctrl):
        with patch('pc_screens._get_key_press_option', return_value=0):
            with patch('subprocess.run', side_effect=OSError("boom")):
                with patch('subprocess.Popen') as mock_popen:
                    assert ctrl.turn_off() is False
                    mock_popen.assert_not_called()


class TestWake:
    """Rallumage force (rollback d'erreur)."""

    @pytest.fixture
    def ctrl(self):
        with patch('pc_screens.shutil.which', return_value='/usr/bin/hyprctl'):
            return PCScreenController(enabled=True)

    def test_wake_after_turn_off(self, ctrl):
        with patch('pc_screens._get_key_press_option', return_value=0):
            with patch('subprocess.run') as mock_run:
                with patch('subprocess.Popen'):
                    ctrl.turn_off()
                    ctrl.wake()
                    args = mock_run.call_args[0][0]
                    assert args == ["hyprctl", "dispatch", "dpms", "on"]

    def test_wake_without_turn_off_is_noop(self, ctrl):
        with patch('subprocess.run') as mock_run:
            ctrl.wake()
            mock_run.assert_not_called()
