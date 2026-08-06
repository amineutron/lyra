"""
Phase 5 - TTS Lyra (J.A.R.V.I.S.)
=================================

Phase finale: Lyra parle avec voix style J.A.R.V.I.S.
Phrase signature + pulse bleu confirmation.

Timeline:
    T+0s:      Verifier etat stable
    T+0.5s:    TTS phrase J.A.R.V.I.S.
    T+4.5s:    Pulse bleu confirmation
    T+5.5s:    Phase terminee

Duree: ~5.5 secondes
"""

import logging
import random
import time
from pathlib import Path
from typing import Optional, Tuple

import numpy as np
import requests
import yaml

logger = logging.getLogger(__name__)

# Phrases J.A.R.V.I.S.
PHRASES = [
    "Bonjour monsieur. Tous les systemes sont operationnels.",
    "Armure Mark 50 prete. Bienvenue, Tony.",
    "Jarvis en ligne. Comment puis-je vous aider?",
    "Bonjour Amineutron. Que la forge commence.",
    "Systemes armure initialises. Pret au decollage.",
]

# Constantes pulse
PULSE_BRIGHTNESS_HIGH = 200
PULSE_BRIGHTNESS_LOW = 150
PULSE_DURATION = 0.5  # 500ms montee, 500ms descente

# Couleur stable
BLUE_ARC_REACTOR_RGB = (0, 100, 255)

# API
API_TIMEOUT = 3.0

# TTS config
TTS_LENGTH_SCALE = 1.1  # Plus lent (0.9x vitesse = 1/0.9 ≈ 1.1)


def rgb_to_xy(red: int, green: int, blue: int) -> Tuple[float, float]:
    """Convertit RGB en coordonnees xy pour Hue."""
    r = red / 255.0
    g = green / 255.0
    b = blue / 255.0

    r = ((r + 0.055) / 1.055) ** 2.4 if r > 0.04045 else r / 12.92
    g = ((g + 0.055) / 1.055) ** 2.4 if g > 0.04045 else g / 12.92
    b = ((b + 0.055) / 1.055) ** 2.4 if b > 0.04045 else b / 12.92

    X = r * 0.4124564 + g * 0.3575761 + b * 0.1804375
    Y = r * 0.2126729 + g * 0.7151522 + b * 0.0721750
    Z = r * 0.0193339 + g * 0.1191920 + b * 0.9503041

    total = X + Y + Z
    if total == 0:
        return (0.0, 0.0)

    return (X / total, Y / total)


class Phase5TTS:
    """
    Phase 5: TTS J.A.R.V.I.S. - Voix finale + pulse confirmation.

    Usage:
        phase5 = Phase5TTS()
        result = phase5.execute()
        # ou avec phrase specifique
        result = phase5.execute(phrase="Bonjour monsieur.")
    """

    def __init__(self, config_path: Path = None):
        """Initialise Phase5 avec la configuration."""
        if config_path is None:
            config_path = Path(__file__).parent.parent.parent.parent / "config.yaml"

        self.config = self._load_config(config_path)
        self.hue_config = self.config.get("hue", {})

        # TTS engine (lazy load)
        self._tts = None

    def _load_config(self, config_path: Path) -> dict:
        """Charge config.yaml et fusionne secrets.yaml si present."""
        config = {}
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning(f"Impossible de charger config.yaml: {e}")

        secrets_path = config_path.parent / "secrets.yaml"
        if secrets_path.exists():
            try:
                with open(secrets_path, 'r') as f:
                    secrets = yaml.safe_load(f) or {}
                for section, values in secrets.items():
                    if section in config and isinstance(config[section], dict):
                        config[section].update(values)
                    else:
                        config[section] = values
            except Exception as e:
                logger.warning(f"Impossible de charger secrets.yaml: {e}")

        return config

    def _get_tts(self):
        """Retourne le TTS engine (lazy load)."""
        if self._tts is None:
            try:
                from piper import PiperVoice
                from piper.config import SynthesisConfig

                # Voix choisie via /setting (fallback: upmc speaker 0)
                models_dir = Path(__file__).parent.parent.parent.parent / "models"
                model_name = "fr_FR-upmc-medium"
                speaker_id = 0
                try:
                    from lyra.core.settings import UserSettings
                    settings = UserSettings()
                    model_name = settings.get("tts.model", model_name)
                    speaker_id = int(settings.get("tts.speaker_id", speaker_id))
                except Exception as e:
                    logger.warning(f"Settings TTS non lus, voix par defaut: {e}")

                model_path = models_dir / f"{model_name}.onnx"
                if not model_path.exists():
                    model_path = models_dir / "fr_FR-upmc-medium.onnx"
                    speaker_id = 0

                self._tts = {
                    "voice": PiperVoice.load(str(model_path)),
                    "config": SynthesisConfig(
                        speaker_id=speaker_id,
                        length_scale=TTS_LENGTH_SCALE  # Plus lent pour style J.A.R.V.I.S.
                    )
                }
            except Exception as e:
                logger.warning(f"TTS init error: {e}")
                self._tts = None
        return self._tts

    def _set_hue_brightness(self, brightness: int, transition_time: int = 0) -> bool:
        """Change le brightness du groupe Hue 81."""
        bridge_ip = self.hue_config.get("bridge_ip", "192.168.1.51")
        username = self.hue_config.get("username", "")

        if not username:
            return False

        url = f"http://{bridge_ip}/api/{username}/groups/81/action"
        payload = {
            "bri": max(1, brightness),
            "transitiontime": transition_time,
        }

        try:
            response = requests.put(url, json=payload, timeout=API_TIMEOUT)
            return response.status_code == 200
        except Exception as e:
            logger.debug(f"Hue brightness error: {e}")
            return False

    def _select_phrase(self, phrase: Optional[str] = None) -> str:
        """
        Selectionne la phrase a prononcer.

        Args:
            phrase: Phrase specifique ou None pour random

        Returns:
            Phrase selectionnee
        """
        if phrase:
            return phrase
        return random.choice(PHRASES)

    def _speak_jarvis_style(self, text: str) -> bool:
        """
        Prononce le texte avec style J.A.R.V.I.S.

        Args:
            text: Texte a prononcer

        Returns:
            True si succes
        """
        tts = self._get_tts()
        if not tts:
            logger.warning("TTS non disponible")
            return False

        try:
            import sounddevice as sd

            # Synthetiser
            voice = tts["voice"]
            config = tts["config"]
            chunks = list(voice.synthesize(text, syn_config=config))

            if not chunks:
                return False

            # Concatener audio
            audio_arrays = [chunk.audio_int16_array for chunk in chunks]
            audio = np.concatenate(audio_arrays)

            # Convertir int16 -> float32
            audio_float = audio.astype(np.float32) / 32768.0

            # Resampler vers 48kHz
            orig_sr = voice.config.sample_rate
            target_sr = 48000
            if orig_sr != target_sr:
                duration = len(audio_float) / orig_sr
                new_length = int(duration * target_sr)
                indices = np.linspace(0, len(audio_float) - 1, new_length)
                audio_float = np.interp(indices, np.arange(len(audio_float)), audio_float).astype(np.float32)

            # Jouer
            sd.play(audio_float, samplerate=target_sr, blocking=True)

            return True

        except Exception as e:
            logger.warning(f"TTS speak error: {e}")
            return False

    def _confirmation_pulse(self) -> bool:
        """
        Execute le pulse de confirmation: 150 -> 200 -> 150.

        Returns:
            True si succes
        """
        logger.debug("Pulse confirmation...")

        # Montee 150 -> 200 en 500ms
        up_ok = self._set_hue_brightness(
            brightness=PULSE_BRIGHTNESS_HIGH,
            transition_time=5  # 500ms
        )

        if up_ok:
            time.sleep(PULSE_DURATION)

            # Descente 200 -> 150 en 500ms
            self._set_hue_brightness(
                brightness=PULSE_BRIGHTNESS_LOW,
                transition_time=5  # 500ms
            )
            time.sleep(PULSE_DURATION)

        return up_ok

    def execute(self, phrase: Optional[str] = None) -> dict:
        """
        Execute la Phase 5: TTS J.A.R.V.I.S. + pulse.

        Timeline:
            T+0s:      Verifier etat
            T+0.5s:    TTS phrase
            T+4.5s:    Pulse confirmation
            T+5.5s:    Fin

        Args:
            phrase: Phrase specifique ou None pour random

        Returns:
            dict avec: success, phrase_used, tts_ok, pulse_ok, duration
        """
        logger.info("Phase 5: TTS J.A.R.V.I.S. - Debut")
        phase_start = time.perf_counter()

        results = {
            "phrase_used": "",
            "tts_ok": False,
            "pulse_ok": False,
        }

        # T+0s: Petit delai pour s'assurer que tout est stable
        time.sleep(0.5)

        # T+0.5s: TTS
        selected_phrase = self._select_phrase(phrase)
        results["phrase_used"] = selected_phrase
        logger.info(f"TTS: \"{selected_phrase}\"")

        results["tts_ok"] = self._speak_jarvis_style(selected_phrase)

        # Attendre T+4.5s pour le pulse (meme si TTS plus court)
        elapsed = time.perf_counter() - phase_start
        target_pulse_time = 4.5
        if elapsed < target_pulse_time:
            time.sleep(target_pulse_time - elapsed)

        # T+4.5s: Pulse confirmation
        results["pulse_ok"] = self._confirmation_pulse()

        duration = time.perf_counter() - phase_start

        # Succes si TTS ou pulse a fonctionne
        results["success"] = results["tts_ok"] or results["pulse_ok"]
        results["duration"] = duration

        logger.info(
            f"Phase 5: TTS J.A.R.V.I.S. - Fin (duree: {duration:.2f}s, "
            f"tts: {results['tts_ok']}, pulse: {results['pulse_ok']})"
        )

        return results
