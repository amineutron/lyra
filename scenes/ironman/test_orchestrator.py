"""
Tests pour l'Orchestrateur Iron Man
"""

import time
from unittest.mock import Mock, patch, MagicMock
import pytest

from .orchestrator import IronManOrchestrator, SceneState


class TestIronManOrchestrator:
    """Tests pour la classe IronManOrchestrator."""

    @pytest.fixture
    def orchestrator(self):
        """Cree un orchestrateur avec config mockee."""
        with patch.object(IronManOrchestrator, '_load_config') as mock_config:
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
            return IronManOrchestrator()

    def test_initial_state_idle(self, orchestrator):
        """Etat initial = IDLE."""
        assert orchestrator.state == SceneState.IDLE
        assert orchestrator.is_running is False

    def test_trigger_detected_launches_scene(self, orchestrator):
        """Trigger detecte lance la scene."""
        with patch.object(orchestrator, '_execute_scene') as mock_exec:
            with patch.object(orchestrator, '_init_phases'):
                # Mock phase0 pour detecter le trigger
                orchestrator._phase0 = Mock()
                orchestrator._phase0.is_trigger_detected.return_value = True

                result = orchestrator.trigger("je suis iron man")

                assert result is True
                mock_exec.assert_called_once()

    def test_trigger_not_detected(self, orchestrator):
        """Pas de trigger = pas de scene."""
        with patch.object(orchestrator, '_init_phases'):
            orchestrator._phase0 = Mock()
            orchestrator._phase0.is_trigger_detected.return_value = False

            result = orchestrator.trigger("bonjour lyra")

            assert result is False

    def test_trigger_ignored_when_running(self, orchestrator):
        """Trigger ignore si scene en cours."""
        orchestrator._state = SceneState.BUILDUP  # Simule scene en cours

        result = orchestrator.trigger("je suis iron man")

        assert result is False

    def test_is_running_states(self, orchestrator):
        """is_running correct pour chaque etat."""
        # Etats non-running
        for state in [SceneState.IDLE, SceneState.STABLE]:
            orchestrator._state = state
            assert orchestrator.is_running is False

        # Etats running
        for state in [SceneState.VALIDATING, SceneState.BLACKOUT,
                      SceneState.IMPACT, SceneState.BUILDUP,
                      SceneState.TRANSITION, SceneState.TTS, SceneState.ROLLBACK]:
            orchestrator._state = state
            assert orchestrator.is_running is True

    @patch('requests.put')
    @patch('requests.get')
    def test_execute_scene_all_phases(self, mock_get, mock_put, orchestrator):
        """Toutes les phases executees dans l'ordre."""
        # Mock API calls
        mock_get.return_value = Mock(status_code=200, json=lambda: {})
        mock_put.return_value = Mock(status_code=200)

        # Mock phases
        with patch.object(orchestrator, '_init_phases'):
            orchestrator._phase0 = Mock()
            orchestrator._phase0.is_trigger_detected.return_value = True
            orchestrator._phase0.validate_and_prepare.return_value = (True, "OK", {"tv": {}, "hue": {}})

            orchestrator._phase1 = Mock()
            orchestrator._phase1.execute.return_value = {"success": True}

            orchestrator._phase2 = Mock()
            orchestrator._phase2.execute.return_value = {"success": True}

            orchestrator._phase3 = Mock()
            orchestrator._phase3.execute.return_value = {"success": True}

            orchestrator._phase4 = Mock()
            orchestrator._phase4.execute.return_value = {"success": True}

            orchestrator._phase5 = Mock()
            orchestrator._phase5.execute.return_value = {"success": True}

            orchestrator.trigger("je suis iron man")

            # Verifier que toutes les phases ont ete appelees
            orchestrator._phase0.validate_and_prepare.assert_called_once()
            orchestrator._phase1.execute.assert_called_once()
            orchestrator._phase2.execute.assert_called_once()
            orchestrator._phase3.execute.assert_called_once()
            orchestrator._phase4.execute.assert_called_once()
            orchestrator._phase5.execute.assert_called_once()

            # Etat final = STABLE
            assert orchestrator.state == SceneState.STABLE

    def test_phase0_failure_no_rollback(self, orchestrator):
        """Echec Phase 0 = pas de rollback, retour IDLE."""
        with patch.object(orchestrator, '_init_phases'):
            with patch.object(orchestrator, '_rollback') as mock_rollback:
                orchestrator._phase0 = Mock()
                orchestrator._phase0.is_trigger_detected.return_value = True
                orchestrator._phase0.validate_and_prepare.return_value = (False, "TV offline", {})

                orchestrator.trigger("je suis iron man")

                # Pas de rollback car rien n'a change
                mock_rollback.assert_not_called()
                assert orchestrator.state == SceneState.IDLE

    def test_phase_failure_triggers_rollback(self, orchestrator):
        """Echec phase 1-5 declenche rollback."""
        with patch.object(orchestrator, '_init_phases'):
            with patch.object(orchestrator, '_rollback') as mock_rollback:
                orchestrator._phase0 = Mock()
                orchestrator._phase0.is_trigger_detected.return_value = True
                orchestrator._phase0.validate_and_prepare.return_value = (True, "OK", {"tv": {}, "hue": {}})

                orchestrator._phase1 = Mock()
                orchestrator._phase1.execute.return_value = {"success": True}

                orchestrator._phase2 = Mock()
                orchestrator._phase2.execute.side_effect = Exception("YouTube failed")

                orchestrator.trigger("je suis iron man")

                # Rollback appele
                mock_rollback.assert_called_once()

    def test_cancel_when_idle(self, orchestrator):
        """Cancel quand IDLE = rien."""
        with patch.object(orchestrator, '_rollback') as mock_rollback:
            orchestrator.cancel()
            mock_rollback.assert_not_called()

    def test_cancel_when_running(self, orchestrator):
        """Cancel quand running = rollback."""
        orchestrator._state = SceneState.BUILDUP

        with patch.object(orchestrator, '_rollback') as mock_rollback:
            orchestrator.cancel()
            mock_rollback.assert_called_once()

    @patch('requests.put')
    def test_rollback_restores_hue(self, mock_put, orchestrator):
        """Rollback restaure les lumieres Hue."""
        mock_put.return_value = Mock(status_code=200)

        orchestrator._saved_state = {
            "hue": {
                "lights": {
                    "1": {"on": True, "brightness": 200, "xy": [0.3, 0.3]},
                    "2": {"on": False, "brightness": 0},
                }
            },
            "tv": {}
        }

        orchestrator._state = SceneState.BUILDUP
        orchestrator._rollback()

        # Verifier les appels API Hue
        assert mock_put.call_count >= 2
        assert orchestrator.state == SceneState.IDLE

    def test_get_status(self, orchestrator):
        """get_status retourne les bonnes infos."""
        orchestrator._state = SceneState.BUILDUP
        orchestrator._phase_results = {"blackout": {"success": True}}

        status = orchestrator.get_status()

        assert status["state"] == "BUILDUP"
        assert status["is_running"] is True
        assert "blackout" in status["phase_results"]


class TestTriggerDetection:
    """Tests pour la detection des triggers."""

    @pytest.fixture
    def orchestrator(self):
        """Cree un orchestrateur avec Phase0 mockee."""
        with patch.object(IronManOrchestrator, '_load_config') as mock_config:
            mock_config.return_value = {}
            orch = IronManOrchestrator()
            orch._init_phases()
            return orch

    def test_trigger_exact_match(self, orchestrator):
        """Trigger exact detecte."""
        with patch.object(orchestrator, '_execute_scene'):
            result = orchestrator.trigger("je suis iron man")
            assert result is True

    def test_trigger_in_sentence(self, orchestrator):
        """Trigger dans une phrase."""
        with patch.object(orchestrator, '_execute_scene'):
            result = orchestrator.trigger("Lyra, je suis iron man s'il te plait")
            assert result is True

    def test_trigger_case_insensitive(self, orchestrator):
        """Trigger insensible a la casse."""
        with patch.object(orchestrator, '_execute_scene'):
            result = orchestrator.trigger("JE SUIS IRON MAN")
            assert result is True

    def test_trigger_with_accents(self, orchestrator):
        """Trigger avec accents."""
        with patch.object(orchestrator, '_execute_scene'):
            # "scène" avec accent
            result = orchestrator.trigger("scène iron man")
            assert result is True

    def test_no_trigger(self, orchestrator):
        """Pas de trigger dans le texte."""
        result = orchestrator.trigger("quelle heure est-il")
        assert result is False


class TestSceneState:
    """Tests pour l'enum SceneState."""

    def test_all_states_defined(self):
        """Tous les etats sont definis."""
        states = [
            SceneState.IDLE,
            SceneState.VALIDATING,
            SceneState.BLACKOUT,
            SceneState.IMPACT,
            SceneState.BUILDUP,
            SceneState.TRANSITION,
            SceneState.TTS,
            SceneState.STABLE,
            SceneState.ROLLBACK,
        ]
        assert len(states) == 9

    def test_states_unique(self):
        """Chaque etat a une valeur unique."""
        values = [s.value for s in SceneState]
        assert len(values) == len(set(values))
