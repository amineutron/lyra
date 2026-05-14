"""
Lyra V1 - Module Audio (STT/TTS)

Gere la capture vocale (faster-whisper) et la synthese (Piper).
"""

import io
import os
import sys
import wave
import queue
import threading
import warnings
import numpy as np

# Note: Les "Exception ignored" de sounddevice sont geres via suppress_stderr()

import sounddevice as sd
from pathlib import Path
from typing import Optional, Callable
from dataclasses import dataclass
from contextlib import contextmanager


@contextmanager
def suppress_stderr():
    """Supprime temporairement stderr (pour les exceptions cffi ignorees)."""
    # Sauvegarder stderr
    old_stderr = sys.stderr
    # Rediriger vers /dev/null
    sys.stderr = open(os.devnull, 'w')
    try:
        yield
    finally:
        sys.stderr.close()
        sys.stderr = old_stderr


@dataclass
class AudioConfig:
    """Configuration audio."""
    sample_rate: int = 16000
    channels: int = 1
    silence_threshold: float = 0.01
    silence_duration: float = 1.0  # Secondes de silence pour fin de phrase
    max_duration: float = 30.0  # Duree max d'enregistrement
    input_device: Optional[int] = None
    output_device: Optional[int] = None


class STT:
    """Speech-to-Text avec faster-whisper."""

    def __init__(
        self,
        model: str = "base",
        language: str = "fr",
        device: str = "cuda",
        compute_type: str = "float16"
    ):
        """
        Initialise le modele STT.

        Args:
            model: Taille du modele (tiny, base, small, medium, large-v2, large-v3)
            language: Langue cible
            device: cuda ou cpu
            compute_type: float16, int8, etc.
        """
        from faster_whisper import WhisperModel

        self.model = WhisperModel(
            model,
            device=device,
            compute_type=compute_type
        )
        self.language = language

    def _resample(self, audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
        """Resample audio vers un nouveau sample rate."""
        if orig_sr == target_sr:
            return audio
        duration = len(audio) / orig_sr
        new_length = int(duration * target_sr)
        indices = np.linspace(0, len(audio) - 1, new_length)
        return np.interp(indices, np.arange(len(audio)), audio).astype(np.float32)

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        """
        Transcrit un tableau audio en texte.

        Args:
            audio: Tableau numpy float32 normalise [-1, 1]
            sample_rate: Taux d'echantillonnage de l'audio source

        Returns:
            Texte transcrit
        """
        # Convertir en float32 si necessaire
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)

        # Resampler vers 16kHz si necessaire (optimal pour Whisper)
        if sample_rate != 16000:
            audio = self._resample(audio, sample_rate, 16000)

        # Normaliser si necessaire
        if len(audio) > 0 and (audio.max() > 1.0 or audio.min() < -1.0):
            audio = audio / max(abs(audio.max()), abs(audio.min()))

        # Transcrire
        segments, info = self.model.transcribe(
            audio,
            language=self.language,
            beam_size=5,
            vad_filter=True
        )

        # Concatener les segments
        text = " ".join(segment.text.strip() for segment in segments)
        return text.strip()

    def transcribe_file(self, file_path: str) -> str:
        """Transcrit un fichier audio."""
        segments, info = self.model.transcribe(
            file_path,
            language=self.language,
            beam_size=5,
            vad_filter=True
        )
        text = " ".join(segment.text.strip() for segment in segments)
        return text.strip()


class TTS:
    """Text-to-Speech avec Piper."""

    def __init__(
        self,
        model_path: str = "models/fr_FR-upmc-medium.onnx",
        speaker_id: int = 0,
        length_scale: float = 1.0
    ):
        """
        Initialise le modele TTS.

        Args:
            model_path: Chemin vers le modele .onnx
            speaker_id: ID du speaker (pour modeles multi-speaker)
            length_scale: Vitesse (1.0 = normal, < 1.0 = plus rapide)
        """
        from piper import PiperVoice
        from piper.config import SynthesisConfig

        # Resoudre le chemin relatif
        model_path = Path(model_path)
        if not model_path.is_absolute():
            model_path = Path(__file__).parent.parent / model_path

        self.voice = PiperVoice.load(str(model_path))
        self.sample_rate = self.voice.config.sample_rate

        # Configurer la synthese
        self.syn_config = SynthesisConfig(
            speaker_id=speaker_id,
            length_scale=length_scale
        )

    def synthesize(self, text: str) -> np.ndarray:
        """
        Synthetise du texte en audio.

        Args:
            text: Texte a synthetiser

        Returns:
            Tableau numpy int16
        """
        # Piper retourne une liste d'AudioChunk
        chunks = list(self.voice.synthesize(text, syn_config=self.syn_config))

        # Concatener les chunks audio
        audio_arrays = [chunk.audio_int16_array for chunk in chunks]
        if audio_arrays:
            audio = np.concatenate(audio_arrays)
        else:
            audio = np.array([], dtype=np.int16)

        return audio

    def _resample(self, audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
        """Resample audio vers un nouveau sample rate."""
        if orig_sr == target_sr:
            return audio
        # Interpolation lineaire simple
        duration = len(audio) / orig_sr
        new_length = int(duration * target_sr)
        indices = np.linspace(0, len(audio) - 1, new_length)
        return np.interp(indices, np.arange(len(audio)), audio).astype(np.float32)

    def speak(self, text: str, output_device: Optional[int] = None, blocking: bool = True):
        """
        Synthetise et joue le texte.

        Args:
            text: Texte a prononcer
            output_device: ID du peripherique de sortie
            blocking: Attendre la fin de la lecture
        """
        audio = self.synthesize(text)

        # Convertir int16 -> float32 pour sounddevice
        audio_float = audio.astype(np.float32) / 32768.0

        # Resampler vers 48kHz (standard supporte par tous les peripheriques)
        target_sr = 48000
        audio_resampled = self._resample(audio_float, self.sample_rate, target_sr)

        with suppress_stderr():
            sd.play(
                audio_resampled,
                samplerate=target_sr,
                device=output_device,
                blocking=blocking
            )


class AudioRecorder:
    """Enregistreur audio avec detection de silence."""

    def __init__(self, config: Optional[AudioConfig] = None):
        """
        Initialise l'enregistreur.

        Args:
            config: Configuration audio
        """
        self.config = config or AudioConfig()
        self._recording = False
        self._audio_queue: queue.Queue = queue.Queue()

    def _audio_callback(self, indata, frames, time, status):
        """Callback pour l'enregistrement audio."""
        if status:
            print(f"Audio status: {status}")
        self._audio_queue.put(indata.copy())

    def record_until_silence(self, show_level: bool = True) -> np.ndarray:
        """
        Enregistre jusqu'a detection de silence.

        Args:
            show_level: Afficher le niveau audio en temps reel

        Returns:
            Tableau numpy float32
        """
        frames = []
        silence_frames = 0
        silence_threshold_frames = int(
            self.config.silence_duration * self.config.sample_rate / 1024
        )
        max_frames = int(
            self.config.max_duration * self.config.sample_rate / 1024
        )

        with suppress_stderr():
            with sd.InputStream(
                samplerate=self.config.sample_rate,
                channels=self.config.channels,
                dtype=np.float32,
                blocksize=1024,
                device=self.config.input_device,
                callback=self._audio_callback
            ):
                frame_count = 0
                speech_detected = False

                while frame_count < max_frames:
                    try:
                        data = self._audio_queue.get(timeout=0.5)
                    except queue.Empty:
                        continue

                    frames.append(data)
                    frame_count += 1

                    # Calculer le niveau audio (RMS)
                    rms = np.sqrt(np.mean(data ** 2))

                    # Afficher indicateur de niveau
                    if show_level:
                        level = min(int(rms * 100), 20)  # Max 20 barres, sensibilite augmentee
                        bars = "█" * level + "░" * (20 - level)
                        status = "●" if rms > self.config.silence_threshold else "○"
                        sys.stdout.write(f"\r  {status} [{bars}] {rms:.3f}  ")
                        sys.stdout.flush()

                    if rms > self.config.silence_threshold:
                        speech_detected = True
                        silence_frames = 0
                    else:
                        if speech_detected:
                            silence_frames += 1

                    # Fin si silence detecte apres parole
                    if speech_detected and silence_frames >= silence_threshold_frames:
                        break

        # Effacer la ligne de niveau
        if show_level:
            print("\r" + " " * 40 + "\r", end="", flush=True)

        # Concatener et retourner
        if frames:
            audio = np.concatenate(frames, axis=0).flatten()
            return audio
        return np.array([], dtype=np.float32)

    def record_fixed_duration(self, duration: float) -> np.ndarray:
        """
        Enregistre pendant une duree fixe.

        Args:
            duration: Duree en secondes

        Returns:
            Tableau numpy float32
        """
        frames = int(duration * self.config.sample_rate)
        with suppress_stderr():
            audio = sd.rec(
                frames,
                samplerate=self.config.sample_rate,
                channels=self.config.channels,
                dtype=np.float32,
                device=self.config.input_device
            )
            sd.wait()
        return audio.flatten()


class VoiceInterface:
    """Interface vocale complete (STT + TTS + Recording)."""

    def __init__(
        self,
        stt_model: str = "base",
        tts_model: str = "models/fr_FR-upmc-medium.onnx",
        language: str = "fr",
        device: str = "cuda",
        audio_config: Optional[AudioConfig] = None
    ):
        """
        Initialise l'interface vocale.

        Args:
            stt_model: Modele Whisper (tiny, base, small, medium, large)
            tts_model: Chemin vers le modele Piper
            language: Langue
            device: cuda ou cpu
            audio_config: Configuration audio
        """
        self.stt = STT(model=stt_model, language=language, device=device)
        self.tts = TTS(model_path=tts_model)
        self.recorder = AudioRecorder(config=audio_config)
        self.config = audio_config or AudioConfig()

    def beep(self, frequency: int = 800, duration: float = 0.15):
        """
        Joue un bip sonore pour indiquer le debut de l'ecoute.

        Args:
            frequency: Frequence du bip en Hz
            duration: Duree en secondes
        """
        sample_rate = 48000  # Sample rate standard
        t = np.linspace(0, duration, int(sample_rate * duration), False)
        # Generer une onde sinusoidale avec fade in/out
        tone = np.sin(2 * np.pi * frequency * t)
        # Fade in/out pour eviter les clics
        fade_len = int(sample_rate * 0.02)
        tone[:fade_len] *= np.linspace(0, 1, fade_len)
        tone[-fade_len:] *= np.linspace(1, 0, fade_len)
        tone = (tone * 0.3).astype(np.float32)  # Volume reduit
        with suppress_stderr():
            sd.play(tone, samplerate=sample_rate, device=self.config.output_device, blocking=True)

    def listen(self, with_beep: bool = True) -> str:
        """
        Ecoute et transcrit la parole.

        Args:
            with_beep: Jouer un bip avant l'ecoute

        Returns:
            Texte transcrit
        """
        if with_beep:
            self.beep()
        audio = self.recorder.record_until_silence()
        if len(audio) == 0:
            return ""
        return self.stt.transcribe(audio, self.config.sample_rate)

    def speak(self, text: str, blocking: bool = True):
        """
        Synthetise et prononce le texte.

        Args:
            text: Texte a prononcer
            blocking: Attendre la fin
        """
        self.tts.speak(text, output_device=self.config.output_device, blocking=blocking)

    def listen_and_respond(self, process_func: Callable[[str], str]):
        """
        Boucle ecoute -> traitement -> reponse.

        Args:
            process_func: Fonction qui prend le texte utilisateur et retourne la reponse
        """
        while True:
            text = self.listen()
            if text:
                response = process_func(text)
                if response:
                    self.speak(response)
