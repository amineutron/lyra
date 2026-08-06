"""
Lyra Core - Menu interactif /setting.

Machine a etats geree directement par la boucle REPL de main_rag.py
(hors pipeline : les reponses "1", "2"... ne passent jamais par le RAG).

Usage cote REPL:
    menu = SettingsMenu(settings=..., models_dir=..., callbacks=...)
    print(menu.open())            # affiche le menu racine
    ...
    if menu.active:
        print(menu.handle(user_input))   # consomme l'entree tant que le menu est ouvert
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from .settings import UserSettings, VoiceInfo, list_available_voices

# Etats du menu
_ROOT = "root"
_VOICE = "voice"
_SPEED = "speed"
_MODE = "mode"

SPEED_PRESETS = [
    ("0.8", "rapide"),
    ("1.0", "normal"),
    ("1.2", "lent"),
]

_QUIT_WORDS = ("q", "quit", "exit", "retour", "annule", "annuler")

SPEED_MIN, SPEED_MAX = 0.5, 2.0


@dataclass
class SettingsCallbacks:
    """Effets de bord injectes par main_rag (tous optionnels pour les tests).

    apply_voice(model_path, speaker_id)  -> hot-swap TTS (None si pas de vocal)
    apply_speed(length_scale)            -> hot-swap vitesse
    preview(text)                        -> prononce un apercu avec la voix active
    get_mode() / set_mode(mode)          -> mode runtime de la boucle REPL
    """
    apply_voice: Optional[Callable[[Path, int], None]] = None
    apply_speed: Optional[Callable[[float], None]] = None
    preview: Optional[Callable[[str], None]] = None
    get_mode: Callable[[], str] = lambda: "default"
    set_mode: Optional[Callable[[str], None]] = None


@dataclass
class SettingsMenu:
    """Menu /setting multi-tours."""

    settings: UserSettings
    models_dir: Path
    callbacks: SettingsCallbacks = field(default_factory=SettingsCallbacks)
    _state: str = field(default=_ROOT, init=False)
    _active: bool = field(default=False, init=False)
    _voices: list[VoiceInfo] = field(default_factory=list, init=False)

    @property
    def active(self) -> bool:
        return self._active

    # ------------------------------------------------------------------
    # Entree / sortie
    # ------------------------------------------------------------------

    def open(self) -> str:
        """Ouvre le menu et retourne l'affichage racine."""
        self._active = True
        self._state = _ROOT
        return self._render_root()

    def close(self) -> str:
        self._active = False
        self._state = _ROOT
        return "Reglages fermes."

    def handle(self, user_input: str) -> str:
        """Traite une entree utilisateur pendant que le menu est ouvert."""
        text = user_input.strip().lower()
        if text in _QUIT_WORDS:
            if self._state == _ROOT:
                return self.close()
            self._state = _ROOT
            return self._render_root()

        if self._state == _ROOT:
            return self._handle_root(text)
        if self._state == _VOICE:
            return self._handle_voice(text)
        if self._state == _SPEED:
            return self._handle_speed(text)
        if self._state == _MODE:
            return self._handle_mode(text)
        return self.close()

    # ------------------------------------------------------------------
    # Rendus
    # ------------------------------------------------------------------

    def current_voice_label(self) -> str:
        model = self.settings.get("tts.model", "fr_FR-upmc-medium")
        speaker_id = int(self.settings.get("tts.speaker_id", 0))
        for voice in self.load_voices():
            if voice.model == model and voice.speaker_id == speaker_id:
                return voice.label
        return model.replace("fr_FR-", "")

    def current_speed_label(self) -> str:
        scale = float(self.settings.get("tts.length_scale", 1.0))
        for preset, name in SPEED_PRESETS:
            if abs(float(preset) - scale) < 1e-9:
                return f"{scale} ({name})"
        return str(scale)

    def _render_root(self) -> str:
        mode = self.callbacks.get_mode()
        return (
            "Reglages Lyra\n"
            f"  1. Voix    : {self.current_voice_label()}\n"
            f"  2. Vitesse : {self.current_speed_label()}\n"
            f"  3. Mode    : {mode}\n"
            "(numero, ou q pour quitter)"
        )

    def _render_voice(self) -> str:
        model = self.settings.get("tts.model", "fr_FR-upmc-medium")
        speaker_id = int(self.settings.get("tts.speaker_id", 0))
        lines = ["Voix disponibles :"]
        for idx, voice in enumerate(self.load_voices(), start=1):
            current = "  [actuelle]" if (
                voice.model == model and voice.speaker_id == speaker_id
            ) else ""
            lines.append(f"  {idx}. {voice.label}{current}")
        lines.append("(numero, ou q pour revenir)")
        return "\n".join(lines)

    def _render_speed(self) -> str:
        lines = ["Vitesse de parole :"]
        for idx, (preset, name) in enumerate(SPEED_PRESETS, start=1):
            lines.append(f"  {idx}. {preset} ({name})")
        lines.append(f"(numero, une valeur libre entre {SPEED_MIN} et {SPEED_MAX}, "
                     "ou q pour revenir)")
        return "\n".join(lines)

    def _render_mode(self) -> str:
        current = self.callbacks.get_mode()
        marker = {m: "  [actuel]" if m == current else "" for m in ("default", "performance")}
        return (
            "Mode :\n"
            f"  1. default (confirmation avant chaque action){marker['default']}\n"
            f"  2. performance (domotique sans confirmation){marker['performance']}\n"
            "(numero, ou q pour revenir)"
        )

    # ------------------------------------------------------------------
    # Handlers par etat
    # ------------------------------------------------------------------

    def _handle_root(self, text: str) -> str:
        if text in ("1", "voix", "voice"):
            self._state = _VOICE
            return self._render_voice()
        if text in ("2", "vitesse", "speed"):
            self._state = _SPEED
            return self._render_speed()
        if text in ("3", "mode"):
            self._state = _MODE
            return self._render_mode()
        return f"Choix invalide.\n{self._render_root()}"

    def _handle_voice(self, text: str) -> str:
        voices = self.load_voices()
        selected = _resolve_option(text, voices, key=lambda v: v.speaker_name)
        if selected is None:
            return f"Choix invalide.\n{self._render_voice()}"
        message = self.apply_voice_choice(selected)
        self._state = _ROOT
        return f"{message}\n\n{self._render_root()}"

    def _handle_speed(self, text: str) -> str:
        if text in ("1", "2", "3"):
            value: Optional[float] = float(SPEED_PRESETS[int(text) - 1][0])
        else:
            value = parse_speed(text)
        if value is None:
            return f"Valeur invalide.\n{self._render_speed()}"
        message = self.apply_speed_choice(value)
        self._state = _ROOT
        return f"{message}\n\n{self._render_root()}"

    def _handle_mode(self, text: str) -> str:
        mode = {"1": "default", "default": "default", "normal": "default",
                "2": "performance", "performance": "performance"}.get(text)
        if mode is None:
            return f"Choix invalide.\n{self._render_mode()}"
        message = self.apply_mode_choice(mode)
        self._state = _ROOT
        return f"{message}\n\n{self._render_root()}"

    # ------------------------------------------------------------------
    # Actions (partagees avec le TUI interactif, settings_tui.py)
    # ------------------------------------------------------------------

    def apply_voice_choice(self, selected: VoiceInfo) -> str:
        """Persiste et applique une voix ; retourne le message de confirmation."""
        self.settings.set("tts.model", selected.model)
        self.settings.set("tts.speaker_id", selected.speaker_id)
        applied = self._apply(self.callbacks.apply_voice,
                              selected.model_path, selected.speaker_id)
        if applied and self.callbacks.preview:
            self._apply(self.callbacks.preview,
                        f"Bonjour, je suis la voix {selected.speaker_name}.")
        note = "" if applied else " (appliquee a la prochaine session vocale)"
        return f"[+] Voix changee : {selected.label}{note}"

    def apply_speed_choice(self, value: float) -> str:
        """Persiste et applique une vitesse ; retourne le message de confirmation."""
        self.settings.set("tts.length_scale", value)
        applied = self._apply(self.callbacks.apply_speed, value)
        if applied and self.callbacks.preview:
            self._apply(self.callbacks.preview, "Voici ma nouvelle vitesse de parole.")
        note = "" if applied else " (appliquee a la prochaine session vocale)"
        return f"[+] Vitesse reglee : {value}{note}"

    def apply_mode_choice(self, mode: str) -> str:
        """Persiste et applique un mode ; retourne le message de confirmation."""
        self.settings.set("active_mode", mode)
        self._apply(self.callbacks.set_mode, mode)
        return f"[+] Mode {mode} active (persiste)"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def load_voices(self) -> list[VoiceInfo]:
        if not self._voices:
            self._voices = list_available_voices(self.models_dir)
        return self._voices

    @staticmethod
    def _apply(callback: Optional[Callable], *args: Any) -> bool:
        """Execute un callback optionnel ; retourne False s'il est absent ou echoue."""
        if callback is None:
            return False
        try:
            callback(*args)
            return True
        except Exception:
            return False


def parse_speed(text: str) -> Optional[float]:
    """Parse une vitesse libre ('0.9', '1,5') ; None si invalide ou hors bornes."""
    try:
        value = float(text.replace(",", "."))
    except ValueError:
        return None
    return value if SPEED_MIN <= value <= SPEED_MAX else None


def _resolve_option(text: str, options: list, key: Callable[[Any], str]):
    """Resout un choix par numero (1-based) ou par nom. None si aucun match."""
    if text.isdigit():
        idx = int(text) - 1
        if 0 <= idx < len(options):
            return options[idx]
        return None
    for option in options:
        if key(option).lower() == text:
            return option
    return None
