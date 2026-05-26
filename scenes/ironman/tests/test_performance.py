import sys
import time
from pathlib import Path
from unittest.mock import Mock, patch
import pytest
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from scenes.ironman.orchestrator import IronManOrchestrator, SceneState
from scenes.ironman.phases.phase1_blackout import Phase1Blackout
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


class TestTimingPrecision:
    def test_phase0_validation_fast(self):
        with patch.object(Phase0Detection, "_load_config", return_value={"tv": {"host": "192.168.1.50"}, "hue": {"bridge_ip": "192.168.1.51", "username": "u"}}):
            phase0 = Phase0Detection()
        with patch.object(phase0, "check_tv_available", return_value=(True, "")):
            with patch.object(phase0, "check_hue_available", return_value=(True, "")):
                with patch.object(phase0, "save_current_state", return_value={"tv": {}, "hue": {}}):
                    start = time.perf_counter()
                    ok, msg, state = phase0.validate_and_prepare()
                    elapsed = time.perf_counter() - start
        assert ok is True
        assert elapsed < 2.0

    def test_trigger_detection_fast(self):
        with patch.object(Phase0Detection, "_load_config", return_value={}):
            phase0 = Phase0Detection()
        phrases = ["je suis iron man", "JE SUIS IRON MAN", "mode iron man",
                   "bonjour", "allume les lumieres", "quelles heures est-il"]
        start = time.perf_counter()
        for _ in range(100):
            for phrase in phrases:
                phase0.is_trigger_detected(phrase)
        elapsed = time.perf_counter() - start
        assert elapsed < 1.0

    def test_trigger_detection_under_10ms(self):
        with patch.object(Phase0Detection, "_load_config", return_value={}):
            phase0 = Phase0Detection()
        times = []
        for _ in range(50):
            start = time.perf_counter()
            phase0.is_trigger_detected("je suis iron man")
            times.append(time.perf_counter() - start)
        avg_ms = (sum(times) / len(times)) * 1000
        assert avg_ms < 10.0

    def test_total_pipeline_phases_simulated(self, orchestrator):
        phase_durations = {
            "phase0": 0.05, "phase1": 3.0, "phase2": 3.5,
            "phase3": 12.0, "phase4": 7.0, "phase5": 5.5,
        }
        total_expected = sum(phase_durations.values())
        assert 30.0 <= total_expected <= 36.0


class TestLatencyLights:
    def test_hue_command_latency_simulated(self):
        import requests
        with patch.object(Phase1Blackout, "_load_config", return_value={"hue": {"bridge_ip": "192.168.1.51", "username": "u"}}):
            phase1 = Phase1Blackout()
        with patch("requests.put") as mock_put:
            mock_put.return_value = Mock(status_code=200)
            start = time.perf_counter()
            ok, latency = phase1._turn_off_lights()
            elapsed_ms = (time.perf_counter() - start) * 1000
        assert ok is True
        assert latency > 0
        assert elapsed_ms < 500.0

    def test_lights_off_latency_returned(self):
        with patch.object(Phase1Blackout, "_load_config", return_value={"hue": {"bridge_ip": "192.168.1.51", "username": "u"}}):
            phase1 = Phase1Blackout()
        with patch("requests.put") as mock_put:
            mock_put.return_value = Mock(status_code=200)
            ok, latency = phase1._turn_off_lights()
        assert isinstance(latency, float)
        assert latency >= 0


class TestLatencyTV:
    def test_tv_command_under_500ms_simulated(self):
        with patch.object(Phase1Blackout, "_load_config", return_value={"tv": {"host": "192.168.1.50", "user": "u", "pass": "p"}, "hue": {"bridge_ip": "192.168.1.51", "username": "u"}}):
            phase1 = Phase1Blackout()
        with patch.object(phase1, "_check_tv_power", return_value="On"):
            with patch("requests.put") as mock_put:
                mock_put.return_value = Mock(status_code=200)
                start = time.perf_counter()
                ok, action = phase1._turn_off_tv()
                elapsed = time.perf_counter() - start
        assert ok is True
        assert elapsed < 0.5

    def test_orchestrator_state_transitions_fast(self, orchestrator):
        states = [SceneState.VALIDATING, SceneState.BLACKOUT, SceneState.IMPACT,
                  SceneState.BUILDUP, SceneState.TRANSITION, SceneState.TTS, SceneState.STABLE]
        start = time.perf_counter()
        for state in states * 100:
            orchestrator._state = state
            _ = orchestrator.is_running
        elapsed = time.perf_counter() - start
        assert elapsed < 0.1


class TestTimingConstants:
    def test_blackout_duration(self):
        from scenes.ironman.phases.phase1_blackout import BLACKOUT_DURATION
        assert BLACKOUT_DURATION == 3.0

    def test_phase4_duration(self):
        from scenes.ironman.phases.phase4_transition import DURATION
        assert DURATION == 7.0

    def test_phase5_pulse_duration(self):
        from scenes.ironman.phases.phase5_tts import PULSE_DURATION
        assert PULSE_DURATION == 0.5

    def test_total_scene_within_bounds(self):
        from scenes.ironman.phases.phase1_blackout import BLACKOUT_DURATION
        from scenes.ironman.phases.phase4_transition import DURATION as PHASE4_DUR
        from scenes.ironman.phases.phase3_buildup import PHASE_DURATION
        total_min = BLACKOUT_DURATION + PHASE_DURATION + PHASE4_DUR
        assert total_min < 40.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
