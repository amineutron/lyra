import sys
from pathlib import Path
from unittest.mock import Mock, patch
import pytest
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from scenes.ironman.orchestrator import IronManOrchestrator, SceneState

@pytest.fixture
def config_mock():
    return {"hue": {"bridge_ip": "192.168.1.51", "username": "u"}, "tv": {"host": "192.168.1.50", "user": "u", "pass": "p"}}

@pytest.fixture
def orchestrator(config_mock):
    with patch.object(IronManOrchestrator, "_load_config", return_value=config_mock):
        return IronManOrchestrator()

def _make_phase_mock(success=True, duration=1.0):
    m = Mock()
    m.execute.return_value = {"success": success, "duration": duration}
    return m
def _setup_all_ok(orch):
    orch._phase0 = Mock()
    orch._phase0.is_trigger_detected.return_value = True
    orch._phase0.validate_and_prepare.return_value = (True, "OK", {"tv": {"power": "On", "volume": 25}, "hue": {"lights": {}}})
    orch._phase1 = _make_phase_mock(True, 3.0)
    orch._phase1.execute.return_value = {"success": True, "lights_off": True, "tv_off": True, "tv_action": "off", "duration": 3.0, "latency_ms": 45.0}
    orch._phase2 = _make_phase_mock(True, 3.5)
    orch._phase2.execute.return_value = {"success": True, "flash_ok": True, "blue_ok": True, "tv_on": True, "music_started": True, "ambilight_active": True, "duration": 3.5, "youtube_launch_time": None}
    orch._phase3 = _make_phase_mock(True, 12.0)
    orch._phase3.execute.return_value = {"success": True, "beats_executed": 22, "total_beats": 24, "duration": 12.0}
    orch._phase4 = _make_phase_mock(True, 7.0)
    orch._phase4.execute.return_value = {"success": True, "beats_executed": 5, "fade_ok": True, "music_stopped": True, "duration": 7.0}
    orch._phase5 = _make_phase_mock(True, 5.5)
    orch._phase5.execute.return_value = {"success": True, "tts_ok": True, "pulse_ok": True, "phrase_used": "Systemes armure.", "duration": 5.5}


class TestFullSceneSuccess:
    def test_all_phases_called(self, orchestrator):
        with patch.object(orchestrator, "_init_phases"):
            _setup_all_ok(orchestrator)
            with patch.object(orchestrator, "_start_hue_beat", return_value=False):
                with patch.object(orchestrator, "_stop_hue_beat"):
                    orchestrator.trigger("je suis iron man")
        orchestrator._phase0.validate_and_prepare.assert_called_once()
        orchestrator._phase1.execute.assert_called_once()
        orchestrator._phase2.execute.assert_called_once()
        orchestrator._phase3.execute.assert_called_once()
        orchestrator._phase4.execute.assert_called_once()
        orchestrator._phase5.execute.assert_called_once()

    def test_final_state_stable(self, orchestrator):
        with patch.object(orchestrator, "_init_phases"):
            _setup_all_ok(orchestrator)
            with patch.object(orchestrator, "_start_hue_beat", return_value=False):
                with patch.object(orchestrator, "_stop_hue_beat"):
                    orchestrator.trigger("je suis iron man")
        assert orchestrator.state == SceneState.STABLE

    def test_phase_results_stored(self, orchestrator):
        with patch.object(orchestrator, "_init_phases"):
            _setup_all_ok(orchestrator)
            with patch.object(orchestrator, "_start_hue_beat", return_value=False):
                with patch.object(orchestrator, "_stop_hue_beat"):
                    orchestrator.trigger("je suis iron man")
        s = orchestrator.get_status()
        assert "validating" in s["phase_results"]
        assert "blackout" in s["phase_results"]
        assert "impact" in s["phase_results"]

    def test_returns_true(self, orchestrator):
        with patch.object(orchestrator, "_init_phases"):
            _setup_all_ok(orchestrator)
            with patch.object(orchestrator, "_start_hue_beat", return_value=False):
                with patch.object(orchestrator, "_stop_hue_beat"):
                    r = orchestrator.trigger("je suis iron man")
        assert r is True

    def test_not_running_after_done(self, orchestrator):
        with patch.object(orchestrator, "_init_phases"):
            _setup_all_ok(orchestrator)
            with patch.object(orchestrator, "_start_hue_beat", return_value=False):
                with patch.object(orchestrator, "_stop_hue_beat"):
                    orchestrator.trigger("je suis iron man")
        assert orchestrator.is_running is False

    def test_saved_state_populated(self, orchestrator):
        with patch.object(orchestrator, "_init_phases"):
            _setup_all_ok(orchestrator)
            with patch.object(orchestrator, "_start_hue_beat", return_value=False):
                with patch.object(orchestrator, "_stop_hue_beat"):
                    orchestrator.trigger("je suis iron man")
        assert orchestrator._saved_state is not None
        assert "tv" in orchestrator._saved_state
        assert "hue" in orchestrator._saved_state

class TestRollback:
    def test_rollback_on_exception(self, orchestrator):
        with patch.object(orchestrator, "_init_phases"):
            with patch.object(orchestrator, "_rollback") as mock_rb:
                orchestrator._phase0 = Mock()
                orchestrator._phase0.is_trigger_detected.return_value = True
                orchestrator._phase0.validate_and_prepare.return_value = (True, "OK", {"tv": {}, "hue": {}})
                orchestrator._phase1 = _make_phase_mock(True)
                orchestrator._phase2 = Mock()
                orchestrator._phase2.execute.side_effect = Exception("timeout")
                orchestrator.trigger("je suis iron man")
                mock_rb.assert_called_once()

    def test_rollback_on_phase3_fail(self, orchestrator):
        with patch.object(orchestrator, "_init_phases"):
            with patch.object(orchestrator, "_rollback") as mock_rb:
                _setup_all_ok(orchestrator)
                orchestrator._phase3.execute.return_value = {"success": False, "beats_executed": 0, "total_beats": 24, "duration": 12.0}
                with patch.object(orchestrator, "_start_hue_beat", return_value=False):
                    with patch.object(orchestrator, "_stop_hue_beat"):
                        orchestrator.trigger("je suis iron man")
                mock_rb.assert_called_once()

    @patch("requests.put")
    def test_rollback_restores_hue(self, mock_put, orchestrator):
        mock_put.return_value = Mock(status_code=200)
        orchestrator._saved_state = {"hue": {"lights": {"1": {"on": True, "brightness": 200, "xy": [0.3, 0.3]}, "2": {"on": False, "brightness": 0}}}, "tv": {}}
        orchestrator._state = SceneState.BUILDUP
        with patch.object(orchestrator, "_stop_hue_beat"):
            orchestrator._rollback()
        assert mock_put.call_count >= 2

    def test_rollback_sets_idle(self, orchestrator):
        orchestrator._state = SceneState.BUILDUP
        orchestrator._saved_state = {"hue": {"lights": {}}, "tv": {}}
        with patch.object(orchestrator, "_stop_hue_beat"):
            with patch("requests.put", return_value=Mock(status_code=200)):
                orchestrator._rollback()
        assert orchestrator.state == SceneState.IDLE

    def test_no_rollback_on_phase0_fail(self, orchestrator):
        with patch.object(orchestrator, "_init_phases"):
            with patch.object(orchestrator, "_rollback") as mock_rb:
                orchestrator._phase0 = Mock()
                orchestrator._phase0.is_trigger_detected.return_value = True
                orchestrator._phase0.validate_and_prepare.return_value = (False, "TV offline", {})
                orchestrator.trigger("je suis iron man")
            mock_rb.assert_not_called()

    def test_idle_after_phase0_fail(self, orchestrator):
        with patch.object(orchestrator, "_init_phases"):
            orchestrator._phase0 = Mock()
            orchestrator._phase0.is_trigger_detected.return_value = True
            orchestrator._phase0.validate_and_prepare.return_value = (False, "TV offline", {})
            orchestrator.trigger("je suis iron man")
        assert orchestrator.state == SceneState.IDLE

class TestCancellation:
    def test_cancel_idle_noop(self, orchestrator):
        with patch.object(orchestrator, "_rollback") as mock_rb:
            orchestrator.cancel()
            mock_rb.assert_not_called()

    def test_cancel_buildup(self, orchestrator):
        orchestrator._state = SceneState.BUILDUP
        with patch.object(orchestrator, "_rollback") as mock_rb:
            orchestrator.cancel()
            mock_rb.assert_called_once()

    def test_cancel_tts(self, orchestrator):
        orchestrator._state = SceneState.TTS
        with patch.object(orchestrator, "_rollback") as mock_rb:
            orchestrator.cancel()
            mock_rb.assert_called_once()

    def test_cancel_impact(self, orchestrator):
        orchestrator._state = SceneState.IMPACT
        with patch.object(orchestrator, "_rollback") as mock_rb:
            orchestrator.cancel()
            mock_rb.assert_called_once()

    def test_state_idle_after_cancel(self, orchestrator):
        orchestrator._state = SceneState.BLACKOUT
        orchestrator._saved_state = {"hue": {"lights": {}}, "tv": {}}
        with patch.object(orchestrator, "_stop_hue_beat"):
            with patch("requests.put", return_value=Mock(status_code=200)):
                orchestrator.cancel()
        assert orchestrator.state == SceneState.IDLE


class TestLyraIntegration:
    def test_trigger_launches_scene(self, orchestrator):
        with patch.object(orchestrator, "_init_phases"):
            with patch.object(orchestrator, "_execute_scene") as mock_exec:
                orchestrator._phase0 = Mock()
                orchestrator._phase0.is_trigger_detected.return_value = True
                r = orchestrator.trigger("je suis iron man")
        assert r is True
        mock_exec.assert_called_once()

    def test_normal_cmd_no_trigger(self, orchestrator):
        with patch.object(orchestrator, "_init_phases"):
            orchestrator._phase0 = Mock()
            orchestrator._phase0.is_trigger_detected.return_value = False
            r = orchestrator.trigger("allume les lumieres")
        assert r is False

    def test_trigger_ignored_running(self, orchestrator):
        orchestrator._state = SceneState.BUILDUP
        r = orchestrator.trigger("je suis iron man")
        assert r is False

    def test_get_status(self, orchestrator):
        orchestrator._state = SceneState.IMPACT
        orchestrator._phase_results = {"blackout": {"success": True}}
        s = orchestrator.get_status()
        assert s["state"] == "IMPACT"
        assert s["is_running"] is True
        assert "blackout" in s["phase_results"]

    def test_many_cmds_no_trigger(self, orchestrator):
        with patch.object(orchestrator, "_init_phases"):
            orchestrator._phase0 = Mock()
            orchestrator._phase0.is_trigger_detected.return_value = False
            for cmd in ["allume lumieres", "liste VMs", "meteo"]:
                assert orchestrator.trigger(cmd) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
