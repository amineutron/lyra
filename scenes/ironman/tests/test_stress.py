import gc
import sys
import time
from pathlib import Path
from unittest.mock import Mock, patch
import pytest
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from scenes.ironman.orchestrator import IronManOrchestrator, SceneState

@pytest.fixture
def config_mock():
    return {
        "hue": {"bridge_ip": "192.168.1.51", "username": "test-user"},
        "tv": {"host": "192.168.1.50", "user": "u", "pass": "p"},
    }

def _make_fresh_orchestrator(config_mock):
    with patch.object(IronManOrchestrator, "_load_config", return_value=config_mock):
        return IronManOrchestrator()

def _setup_all_ok(orch):
    orch._phase0 = Mock()
    orch._phase0.is_trigger_detected.return_value = True
    orch._phase0.validate_and_prepare.return_value = (True, "OK", {"tv": {}, "hue": {"lights": {}}})
    for attr in ["_phase1", "_phase2", "_phase3", "_phase4", "_phase5"]:
        m = Mock()
        m.execute.return_value = {"success": True, "duration": 0.1}
        if attr == "_phase2":
            m.execute.return_value = {"success": True, "duration": 0.1, "youtube_launch_time": None}
        setattr(orch, attr, m)


class TestRepeatedScenes:
    def test_ten_scenes_all_succeed(self, config_mock):
        results = []
        for i in range(10):
            orch = _make_fresh_orchestrator(config_mock)
            with patch.object(orch, "_init_phases"):
                _setup_all_ok(orch)
                with patch.object(orch, "_start_hue_beat", return_value=False):
                    with patch.object(orch, "_stop_hue_beat"):
                        r = orch.trigger("je suis iron man")
            results.append(r)
            assert orch.state == SceneState.STABLE, f"Scene {i} failed: state={orch.state}"
        assert all(r is True for r in results)

    def test_no_memory_leak_on_repeated_scenes(self, config_mock):
        gc.collect()
        initial_objects = len(gc.get_objects())
        for _ in range(5):
            orch = _make_fresh_orchestrator(config_mock)
            with patch.object(orch, "_init_phases"):
                _setup_all_ok(orch)
                with patch.object(orch, "_start_hue_beat", return_value=False):
                    with patch.object(orch, "_stop_hue_beat"):
                        orch.trigger("je suis iron man")
            del orch
        gc.collect()
        final_objects = len(gc.get_objects())
        growth = final_objects - initial_objects
        assert growth < 500, f"Possible memory leak: {growth} new objects"

    def test_scenes_independent(self, config_mock):
        for i in range(3):
            orch = _make_fresh_orchestrator(config_mock)
            assert orch.state == SceneState.IDLE
            with patch.object(orch, "_init_phases"):
                _setup_all_ok(orch)
                with patch.object(orch, "_start_hue_beat", return_value=False):
                    with patch.object(orch, "_stop_hue_beat"):
                        orch.trigger("je suis iron man")
            assert orch.state == SceneState.STABLE

    def test_repeated_trigger_checks_fast(self, config_mock):
        orch = _make_fresh_orchestrator(config_mock)
        with patch.object(orch, "_init_phases"):
            orch._phase0 = Mock()
            orch._phase0.is_trigger_detected.return_value = False
            start = time.perf_counter()
            for _ in range(100):
                orch.trigger("bonjour lyra")
            elapsed = time.perf_counter() - start
        assert elapsed < 1.0


class TestMultipleCancellations:
    def test_cancel_five_times_rollback_ok(self, config_mock):
        for i in range(5):
            orch = _make_fresh_orchestrator(config_mock)
            orch._state = SceneState.BUILDUP
            orch._saved_state = {"hue": {"lights": {}}, "tv": {}}
            with patch.object(orch, "_stop_hue_beat"):
                with patch("requests.put", return_value=Mock(status_code=200)):
                    orch.cancel()
            assert orch.state == SceneState.IDLE, f"Cancel {i}: state={orch.state}"

    def test_cancel_different_states(self, config_mock):
        cancellable = [SceneState.BLACKOUT, SceneState.IMPACT, SceneState.BUILDUP,
                       SceneState.TRANSITION, SceneState.TTS]
        for state in cancellable:
            orch = _make_fresh_orchestrator(config_mock)
            orch._state = state
            orch._saved_state = {"hue": {"lights": {}}, "tv": {}}
            with patch.object(orch, "_stop_hue_beat"):
                with patch("requests.put", return_value=Mock(status_code=200)):
                    orch.cancel()
            assert orch.state == SceneState.IDLE, f"State {state.name}: final={orch.state}"

    def test_cancel_then_retrigger(self, config_mock):
        orch = _make_fresh_orchestrator(config_mock)
        orch._state = SceneState.BUILDUP
        orch._saved_state = {"hue": {"lights": {}}, "tv": {}}
        with patch.object(orch, "_stop_hue_beat"):
            with patch("requests.put", return_value=Mock(status_code=200)):
                orch.cancel()
        assert orch.state == SceneState.IDLE
        with patch.object(orch, "_init_phases"):
            with patch.object(orch, "_execute_scene") as mock_exec:
                orch._phase0 = Mock()
                orch._phase0.is_trigger_detected.return_value = True
                r = orch.trigger("je suis iron man")
        assert r is True
        mock_exec.assert_called_once()

    def test_cancel_rollback_no_state_saved(self, config_mock):
        orch = _make_fresh_orchestrator(config_mock)
        orch._state = SceneState.BUILDUP
        orch._saved_state = None
        with patch.object(orch, "_stop_hue_beat"):
            orch.cancel()
        assert orch.state == SceneState.IDLE


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
