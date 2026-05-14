"""
Tests unitaires pour Phase 0 - Detection & Validation
=====================================================

Usage:
    pytest scenes/ironman/phases/test_phase0.py -v
    pytest scenes/ironman/phases/test_phase0.py -v --cov=scenes/ironman/phases
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import requests

import sys
from pathlib import Path

# Add parent dir to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from phase0_detection import (
    Phase0Detection,
    normalize_text,
    TRIGGERS,
    ROLLBACK_FILE,
    load_rollback_state,
)


# =============================================================================
# Tests normalize_text
# =============================================================================

class TestNormalizeText:
    """Tests pour la fonction de normalisation."""

    def test_lowercase(self):
        assert normalize_text("HELLO") == "hello"
        assert normalize_text("JE SUIS IRON MAN") == "je suis iron man"

    def test_remove_accents(self):
        assert normalize_text("scène") == "scene"
        assert normalize_text("détente") == "detente"
        assert normalize_text("éàùôî") == "eauoi"

    def test_combined(self):
        assert normalize_text("SCÈNE Iron Man") == "scene iron man"


# =============================================================================
# Tests is_trigger_detected
# =============================================================================

class TestTriggerDetection:
    """Tests pour la detection des triggers vocaux."""

    @pytest.fixture
    def phase0(self):
        """Cree une instance Phase0 avec config mockee."""
        with patch.object(Phase0Detection, '_load_config', return_value={}):
            return Phase0Detection()

    # --- Triggers positifs ---

    def test_trigger_je_suis_iron_man(self, phase0):
        assert phase0.is_trigger_detected("je suis iron man") is True

    def test_trigger_je_suis_tony_stark(self, phase0):
        assert phase0.is_trigger_detected("je suis tony stark") is True

    def test_trigger_je_suis_tony(self, phase0):
        assert phase0.is_trigger_detected("je suis tony") is True

    def test_trigger_mode_iron_man(self, phase0):
        assert phase0.is_trigger_detected("mode iron man") is True

    def test_trigger_scene_iron_man(self, phase0):
        assert phase0.is_trigger_detected("scene iron man") is True

    # --- Case insensitive ---

    def test_trigger_uppercase(self, phase0):
        assert phase0.is_trigger_detected("JE SUIS IRON MAN") is True

    def test_trigger_mixed_case(self, phase0):
        assert phase0.is_trigger_detected("Je Suis Iron Man") is True

    def test_trigger_tony_uppercase(self, phase0):
        assert phase0.is_trigger_detected("JE SUIS TONY STARK") is True

    # --- Accents ---

    def test_trigger_scene_avec_accent(self, phase0):
        assert phase0.is_trigger_detected("scène iron man") is True

    # --- Dans phrase longue ---

    def test_trigger_in_sentence_prefix(self, phase0):
        assert phase0.is_trigger_detected("Lyra, je suis iron man") is True

    def test_trigger_in_sentence_suffix(self, phase0):
        assert phase0.is_trigger_detected("je suis iron man maintenant") is True

    def test_trigger_in_sentence_both(self, phase0):
        assert phase0.is_trigger_detected("ok Lyra, je suis iron man s'il te plait") is True

    # --- Triggers negatifs ---

    def test_no_trigger_empty(self, phase0):
        assert phase0.is_trigger_detected("") is False

    def test_no_trigger_none(self, phase0):
        assert phase0.is_trigger_detected(None) is False

    def test_no_trigger_random(self, phase0):
        assert phase0.is_trigger_detected("allume la lumiere") is False

    def test_no_trigger_partial(self, phase0):
        assert phase0.is_trigger_detected("iron man est cool") is False

    def test_no_trigger_negation(self, phase0):
        # "je ne suis pas iron man" ne contient PAS "je suis iron man" (il y a "ne...pas" au milieu)
        # Donc ce n'est PAS un trigger - comportement correct
        assert phase0.is_trigger_detected("je ne suis pas iron man") is False

    def test_no_trigger_other_hero(self, phase0):
        assert phase0.is_trigger_detected("je suis batman") is False

    def test_no_trigger_just_tony(self, phase0):
        # "tony" seul sans "je suis" devant
        assert phase0.is_trigger_detected("tony est la") is False


# =============================================================================
# Tests check_tv_available
# =============================================================================

class TestTVAvailability:
    """Tests pour la verification de disponibilite TV."""

    @pytest.fixture
    def phase0(self):
        with patch.object(Phase0Detection, '_load_config', return_value={
            'tv': {'host': '192.168.1.50'}
        }):
            return Phase0Detection()

    def test_tv_online(self, phase0):
        """TV repond avec succes."""
        with patch('requests.get') as mock_get:
            mock_get.return_value = MagicMock(status_code=200)
            success, msg = phase0.check_tv_available()
            assert success is True
            assert msg == ""

    def test_tv_offline_timeout(self, phase0):
        """TV ne repond pas (timeout)."""
        with patch('requests.get') as mock_get:
            mock_get.side_effect = requests.exceptions.Timeout()
            success, msg = phase0.check_tv_available()
            assert success is False
            assert "timeout" in msg.lower()

    def test_tv_offline_connection_error(self, phase0):
        """TV non joignable (connexion refusee)."""
        with patch('requests.get') as mock_get:
            mock_get.side_effect = requests.exceptions.ConnectionError()
            success, msg = phase0.check_tv_available()
            assert success is False
            assert "non disponible" in msg.lower()

    def test_tv_bad_response(self, phase0):
        """TV repond avec erreur HTTP."""
        with patch('requests.get') as mock_get:
            mock_get.return_value = MagicMock(status_code=500)
            success, msg = phase0.check_tv_available()
            assert success is False
            assert "500" in msg


# =============================================================================
# Tests check_hue_available
# =============================================================================

class TestHueAvailability:
    """Tests pour la verification de disponibilite Hue."""

    @pytest.fixture
    def phase0(self):
        with patch.object(Phase0Detection, '_load_config', return_value={
            'hue': {
                'bridge_ip': '192.168.1.51',
                'username': 'testuser123'
            }
        }):
            return Phase0Detection()

    @pytest.fixture
    def phase0_no_username(self):
        with patch.object(Phase0Detection, '_load_config', return_value={
            'hue': {'bridge_ip': '192.168.1.51'}
        }):
            return Phase0Detection()

    def test_hue_online(self, phase0):
        """Bridge Hue repond avec succes."""
        with patch('requests.get') as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200,
                json=lambda: {"1": {"name": "Hue"}}
            )
            success, msg = phase0.check_hue_available()
            assert success is True
            assert msg == ""

    def test_hue_offline_timeout(self, phase0):
        """Bridge Hue ne repond pas (timeout)."""
        with patch('requests.get') as mock_get:
            mock_get.side_effect = requests.exceptions.Timeout()
            success, msg = phase0.check_hue_available()
            assert success is False
            assert "timeout" in msg.lower()

    def test_hue_offline_connection_error(self, phase0):
        """Bridge Hue non joignable."""
        with patch('requests.get') as mock_get:
            mock_get.side_effect = requests.exceptions.ConnectionError()
            success, msg = phase0.check_hue_available()
            assert success is False
            assert "non disponible" in msg.lower()

    def test_hue_no_username(self, phase0_no_username):
        """Configuration Hue incomplete (pas de username)."""
        success, msg = phase0_no_username.check_hue_available()
        assert success is False
        assert "username" in msg.lower()

    def test_hue_api_error(self, phase0):
        """Bridge Hue retourne une erreur API."""
        with patch('requests.get') as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200,
                json=lambda: [{"error": {"type": 1, "description": "unauthorized user"}}]
            )
            success, msg = phase0.check_hue_available()
            assert success is False
            assert "unauthorized" in msg.lower()


# =============================================================================
# Tests save_current_state
# =============================================================================

class TestSaveState:
    """Tests pour la sauvegarde d'etat."""

    @pytest.fixture
    def phase0(self):
        with patch.object(Phase0Detection, '_load_config', return_value={
            'tv': {'host': '192.168.1.50', 'user': 'test', 'pass': 'pass'},
            'hue': {'bridge_ip': '192.168.1.51', 'username': 'testuser'}
        }):
            return Phase0Detection()

    def test_save_state_creates_file(self, phase0, tmp_path):
        """Verifie que le fichier JSON est cree."""
        # Mock the rollback file path
        test_file = tmp_path / "rollback.json"

        with patch('phase0_detection.ROLLBACK_FILE', test_file):
            with patch('requests.get') as mock_get:
                # Mock TV responses
                mock_get.return_value = MagicMock(
                    status_code=200,
                    json=lambda: {"powerstate": "On", "current": 25}
                )

                state = phase0.save_current_state()

                assert test_file.exists()
                assert "timestamp" in state
                assert "tv" in state
                assert "hue" in state

    def test_save_state_json_valid(self, phase0, tmp_path):
        """Verifie que le JSON sauvegarde est valide."""
        test_file = tmp_path / "rollback.json"

        with patch('phase0_detection.ROLLBACK_FILE', test_file):
            with patch('requests.get') as mock_get:
                mock_get.return_value = MagicMock(
                    status_code=200,
                    json=lambda: {}
                )

                phase0.save_current_state()

                # Verify JSON is parseable
                with open(test_file) as f:
                    data = json.load(f)
                    assert isinstance(data, dict)
                    assert "timestamp" in data


# =============================================================================
# Tests validate_and_prepare
# =============================================================================

class TestValidateAndPrepare:
    """Tests pour la fonction principale d'orchestration."""

    @pytest.fixture
    def phase0(self):
        with patch.object(Phase0Detection, '_load_config', return_value={
            'tv': {'host': '192.168.1.50'},
            'hue': {'bridge_ip': '192.168.1.51', 'username': 'testuser'}
        }):
            return Phase0Detection()

    def test_validate_all_ok(self, phase0, tmp_path):
        """Tous les devices sont disponibles."""
        test_file = tmp_path / "rollback.json"

        with patch('phase0_detection.ROLLBACK_FILE', test_file):
            with patch.object(phase0, 'check_tv_available', return_value=(True, "")):
                with patch.object(phase0, 'check_hue_available', return_value=(True, "")):
                    with patch.object(phase0, 'save_current_state', return_value={"test": True}):
                        success, msg, state = phase0.validate_and_prepare()

                        assert success is True
                        assert "pret" in msg.lower()
                        assert state == {"test": True}

    def test_validate_tv_offline(self, phase0):
        """TV non disponible -> echec."""
        with patch.object(phase0, 'check_tv_available', return_value=(False, "TV offline")):
            success, msg, state = phase0.validate_and_prepare()

            assert success is False
            assert "TV offline" in msg
            assert state == {}

    def test_validate_hue_offline(self, phase0):
        """Hue non disponible -> echec."""
        with patch.object(phase0, 'check_tv_available', return_value=(True, "")):
            with patch.object(phase0, 'check_hue_available', return_value=(False, "Hue offline")):
                success, msg, state = phase0.validate_and_prepare()

                assert success is False
                assert "Hue offline" in msg
                assert state == {}


# =============================================================================
# Tests load_rollback_state
# =============================================================================

class TestLoadRollback:
    """Tests pour le chargement de l'etat de rollback."""

    def test_load_existing_file(self, tmp_path):
        """Charge un fichier existant."""
        test_file = tmp_path / "rollback.json"
        test_data = {"timestamp": "2026-01-24", "tv": {"power": "on"}}

        with open(test_file, 'w') as f:
            json.dump(test_data, f)

        with patch('phase0_detection.ROLLBACK_FILE', test_file):
            state = load_rollback_state()
            assert state == test_data

    def test_load_nonexistent_file(self, tmp_path):
        """Fichier inexistant -> None."""
        test_file = tmp_path / "nonexistent.json"

        with patch('phase0_detection.ROLLBACK_FILE', test_file):
            state = load_rollback_state()
            assert state is None

    def test_load_invalid_json(self, tmp_path):
        """JSON invalide -> None."""
        test_file = tmp_path / "invalid.json"
        test_file.write_text("not valid json {")

        with patch('phase0_detection.ROLLBACK_FILE', test_file):
            state = load_rollback_state()
            assert state is None


# =============================================================================
# Run tests
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
