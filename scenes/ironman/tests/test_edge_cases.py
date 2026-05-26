import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import requests
import pytest
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from scenes.ironman.orchestrator import IronManOrchestrator, SceneState
from scenes.ironman.phases.phase0_detection import Phase0Detection

@pytest.fixture
def config_mock():
    return {
        "hue": {"bridge_ip": "192.168.1.51", "username": "test-user"},
        "tv": {"host": "192.168.1.50", "user": "u", "pass": "p"},
    }

@pytest.fixture
def orchestrator(config_mock):
    with patch.object(IronManOrchestrator, "_load_config", return_value=config_mock):
        return IronManOrchestrator()

class TestDoubleTrigger:
    def test_double_trigger_ignored(self, orchestrator):
        orchestrator._state = SceneState.BUILDUP
        r = orchestrator.trigger("je suis iron man")
        assert r is False

    def test_trigger_allowed_after_stable(self, orchestrator):
        # Apres STABLE, un nouveau trigger devrait etre accepte si IDLE
        orchestrator._state = SceneState.IDLE
        with patch.object(orchestrator, "_init_phases"):
            with patch.object(orchestrator, "_execute_scene"):
                orchestrator._phase0 = Mock()
                orchestrator._phase0.is_trigger_detected.return_value = True
                r = orchestrator.trigger("je suis iron man")
        assert r is True

    def test_trigger_ignored_in_rollback(self, orchestrator):
        orchestrator._state = SceneState.ROLLBACK
        r = orchestrator.trigger("je suis iron man")
        assert r is False

    def test_trigger_ignored_in_validating(self, orchestrator):
        orchestrator._state = SceneState.VALIDATING
        r = orchestrator.trigger("je suis iron man")
        assert r is False

    def test_is_running_all_active_states(self, orchestrator):
        active = [SceneState.VALIDATING, SceneState.BLACKOUT, SceneState.IMPACT,
                  SceneState.BUILDUP, SceneState.TRANSITION, SceneState.TTS, SceneState.ROLLBACK]
        for state in active:
            orchestrator._state = state
            assert orchestrator.is_running is True


class TestTVOfflineGraceful:
    def test_tv_offline_aborts_cleanly(self, orchestrator):
        with patch.object(orchestrator, "_init_phases"):
            with patch.object(orchestrator, "_rollback") as mock_rb:
                orchestrator._phase0 = Mock()
                orchestrator._phase0.is_trigger_detected.return_value = True
                orchestrator._phase0.validate_and_prepare.return_value = (False, "TV non disponible", {})
                r = orchestrator.trigger("je suis iron man")
        assert r is True
        mock_rb.assert_not_called()
        assert orchestrator.state == SceneState.IDLE

    def test_tv_offline_message_clear(self):
        with patch.object(Phase0Detection, "_load_config", return_value={"tv": {"host": "192.168.1.50"}, "hue": {"bridge_ip": "192.168.1.51", "username": "u"}}):
            phase0 = Phase0Detection()
        with patch("requests.get") as mock_get:
            mock_get.side_effect = requests.exceptions.ConnectionError()
            ok, msg = phase0.check_tv_available()
        assert ok is False
        assert len(msg) > 0

    def test_tv_offline_phase0_check_fails(self):
        with patch.object(Phase0Detection, "_load_config", return_value={"tv": {"host": "192.168.1.50"}}):
            phase0 = Phase0Detection()
        with patch("requests.get") as mock_get:
            mock_get.side_effect = requests.exceptions.Timeout()
            ok, msg = phase0.check_tv_available()
        assert ok is False
        assert "timeout" in msg.lower()


class TestHueOfflineAbort:
    def test_hue_offline_aborts(self, orchestrator):
        with patch.object(orchestrator, "_init_phases"):
            with patch.object(orchestrator, "_rollback") as mock_rb:
                orchestrator._phase0 = Mock()
                orchestrator._phase0.is_trigger_detected.return_value = True
                orchestrator._phase0.validate_and_prepare.return_value = (False, "Bridge non disponible", {})
                orchestrator.trigger("je suis iron man")
        mock_rb.assert_not_called()
        assert orchestrator.state == SceneState.IDLE

    def test_hue_offline_message(self):
        with patch.object(Phase0Detection, "_load_config", return_value={"hue": {"bridge_ip": "192.168.1.51", "username": "u"}}):
            phase0 = Phase0Detection()
        with patch("requests.get") as mock_get:
            mock_get.side_effect = requests.exceptions.ConnectionError()
            ok, msg = phase0.check_hue_available()
        assert ok is False
        assert "non disponible" in msg.lower()

class TestYouTubeFailure:
    def test_scene_continues_without_youtube(self, orchestrator):
        with patch.object(orchestrator, "_init_phases"):
            with patch.object(orchestrator, "_rollback") as mock_rb:
                orchestrator._phase0 = Mock()
                orchestrator._phase0.is_trigger_detected.return_value = True
                orchestrator._phase0.validate_and_prepare.return_value = (True, "OK", {"tv": {}, "hue": {"lights": {}}})
                orchestrator._phase1 = Mock()
                orchestrator._phase1.execute.return_value = {"success": True, "lights_off": True, "tv_off": True, "tv_action": "off", "duration": 3.0, "latency_ms": 45.0}
                orchestrator._phase2 = Mock()
                orchestrator._phase2.execute.return_value = {"success": True, "flash_ok": True, "blue_ok": True, "tv_on": True, "music_started": False, "ambilight_active": False, "duration": 3.5, "youtube_launch_time": None}
                orchestrator._phase3 = Mock()
                orchestrator._phase3.execute.return_value = {"success": True, "beats_executed": 20, "total_beats": 24, "duration": 12.0}
                orchestrator._phase4 = Mock()
                orchestrator._phase4.execute.return_value = {"success": True, "beats_executed": 5, "fade_ok": True, "music_stopped": True, "duration": 7.0}
                orchestrator._phase5 = Mock()
                orchestrator._phase5.execute.return_value = {"success": True, "tts_ok": True, "pulse_ok": True, "phrase_used": "OK", "duration": 5.5}
                with patch.object(orchestrator, "_start_hue_beat", return_value=False):
                    with patch.object(orchestrator, "_stop_hue_beat"):
                        orchestrator.trigger("je suis iron man")
        assert orchestrator.state == SceneState.STABLE
        mock_rb.assert_not_called()

    def test_phase2_music_not_started_marks_false(self, orchestrator):
        # Valide que le resultat music_started=False est bien stocke
        with patch.object(orchestrator, "_init_phases"):
            orchestrator._phase0 = Mock()
            orchestrator._phase0.is_trigger_detected.return_value = True
            orchestrator._phase0.validate_and_prepare.return_value = (True, "OK", {"tv": {}, "hue": {"lights": {}}})
            orchestrator._phase1 = Mock()
            orchestrator._phase1.execute.return_value = {"success": True, "lights_off": True, "tv_off": True, "tv_action": "off", "duration": 3.0, "latency_ms": 10.0}
            orchestrator._phase2 = Mock()
            orchestrator._phase2.execute.return_value = {"success": False, "flash_ok": False, "blue_ok": False, "tv_on": False, "music_started": False, "ambilight_active": False, "duration": 0.5, "youtube_launch_time": None}
            with patch.object(orchestrator, "_rollback") as mock_rb:
                with patch.object(orchestrator, "_start_hue_beat", return_value=False):
                    with patch.object(orchestrator, "_stop_hue_beat"):
                        orchestrator.trigger("je suis iron man")
            mock_rb.assert_called_once()


class TestRapidCancellation:
    def test_cancel_during_blackout(self, orchestrator):
        orchestrator._state = SceneState.BLACKOUT
        with patch.object(orchestrator, "_rollback") as mock_rb:
            orchestrator.cancel()
            mock_rb.assert_called_once()

    def test_cancel_during_impact(self, orchestrator):
        orchestrator._state = SceneState.IMPACT
        with patch.object(orchestrator, "_rollback") as mock_rb:
            orchestrator.cancel()
            mock_rb.assert_called_once()

    def test_cancel_returns_quickly(self, orchestrator):
        import time
        orchestrator._state = SceneState.TRANSITION
        orchestrator._saved_state = {"hue": {"lights": {}}, "tv": {}}
        start = time.perf_counter()
        with patch.object(orchestrator, "_stop_hue_beat"):
            with patch("requests.put", return_value=Mock(status_code=200)):
                orchestrator.cancel()
        elapsed = time.perf_counter() - start
        assert elapsed < 2.0


class TestMultipleScenesQueued:
    def test_second_trigger_ignored_while_running(self, orchestrator):
        orchestrator._state = SceneState.BUILDUP
        r1 = orchestrator.trigger("je suis iron man")
        r2 = orchestrator.trigger("je suis tony stark")
        assert r1 is False
        assert r2 is False

    def test_all_active_states_block_trigger(self, orchestrator):
        blocking = [SceneState.VALIDATING, SceneState.BLACKOUT, SceneState.IMPACT,
                    SceneState.BUILDUP, SceneState.TRANSITION, SceneState.TTS, SceneState.ROLLBACK]
        for state in blocking:
            orchestrator._state = state
            r = orchestrator.trigger("je suis iron man")
            assert r is False, f"Expected False for state {state.name}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
