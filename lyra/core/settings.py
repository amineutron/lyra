"""
Lyra Core - Reglages utilisateur persistants.

Les reglages modifiables a chaud (voix TTS, vitesse, mode) sont stockes dans
~/.lyra/settings.json et fusionnes PAR-DESSUS config.yaml au demarrage.
config.yaml n'est jamais reecrit (il reste la reference commentee du projet).
"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

SETTINGS_PATH = Path.home() / ".lyra" / "settings.json"

# Cles autorisees dans settings.json (dot-notation)
ALLOWED_KEYS = {
    "tts.model",         # nom du modele piper sans extension (ex: fr_FR-siwis-medium)
    "tts.speaker_id",    # speaker pour les modeles multi-speaker
    "tts.length_scale",  # vitesse (1.0 = normal, >1 = plus lent)
    "active_mode",       # default | performance
}

# Genre connu des voix Piper fr_FR (les metadonnees .onnx.json ne le donnent pas)
VOICE_GENDERS = {
    "jessica": "femme",
    "pierre": "homme",
    "siwis": "femme",
    "tom": "homme",
    "gilles": "homme",
}

# Au-dela de ce nombre de speakers, on n'expose que les premiers (corpus mls: 125)
MAX_SPEAKERS_SHOWN = 2


@dataclass(frozen=True)
class VoiceInfo:
    """Une voix selectionnable = un modele Piper + un speaker."""
    model: str          # nom du modele sans extension (ex: fr_FR-upmc-medium)
    model_path: Path    # chemin absolu du .onnx
    speaker_id: int
    speaker_name: str   # "jessica", "pierre", ou nom du modele si mono-speaker
    quality: str        # low / medium / high

    @property
    def label(self) -> str:
        """Libelle court pour le menu.

        Exemples: 'jessica (upmc, femme)', 'siwis (femme)', 'mls 1840'.
        """
        short_model = self.model.replace("fr_FR-", "").rsplit("-", 1)[0]
        gender = VOICE_GENDERS.get(self.speaker_name.lower())
        if self.speaker_name.isdigit():
            name = f"{short_model} {self.speaker_name}"
            details = []
        else:
            name = self.speaker_name
            details = [] if self.speaker_name.lower() == short_model.lower() else [short_model]
        if gender:
            details.append(gender)
        if self.quality != "medium":
            details.append(f"qualite {self.quality}")
        return f"{name} ({', '.join(details)})" if details else name


class UserSettings:
    """Reglages utilisateur persistants (~/.lyra/settings.json).

    Lecture au demarrage, ecriture atomique a chaque changement.
    Les getters retournent des copies : l'etat interne n'est jamais expose.
    """

    def __init__(self, path: Path = SETTINGS_PATH):
        self._path = path
        self._data = self._load()

    def _load(self) -> dict:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}

    def get(self, key: str, default: Any = None) -> Any:
        """Lit une cle en dot-notation (ex: 'tts.model')."""
        node: Any = self._data
        for part in key.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, key: str, value: Any) -> None:
        """Ecrit une cle en dot-notation et persiste immediatement (atomique)."""
        if key not in ALLOWED_KEYS:
            raise ValueError(f"Cle de reglage inconnue: {key}")
        new_data = json.loads(json.dumps(self._data))  # copie profonde
        node = new_data
        parts = key.split(".")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
        self._write(new_data)
        self._data = new_data

    def _write(self, data: dict) -> None:
        """Ecriture atomique : fichier temporaire puis rename."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(data, indent=2, ensure_ascii=False)
        with tempfile.NamedTemporaryFile(
            "w", dir=self._path.parent, suffix=".tmp", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)
        tmp_path.replace(self._path)

    def merged_tts(self, yaml_tts: dict) -> dict:
        """Fusionne la section tts de config.yaml avec les overrides utilisateur.

        Returns:
            Nouveau dict {model, speaker_id, length_scale} (les entrees yaml
            inconnues sont conservees).
        """
        merged = dict(yaml_tts or {})
        for yaml_key, settings_key in (
            ("model", "tts.model"),
            ("speaker_id", "tts.speaker_id"),
            ("length_scale", "tts.length_scale"),
        ):
            value = self.get(settings_key)
            if value is not None:
                merged[yaml_key] = value
        return merged

    def active_mode(self, default: str = "default") -> str:
        mode = self.get("active_mode")
        return mode if mode in ("default", "performance") else default


def list_available_voices(models_dir: Path) -> list[VoiceInfo]:
    """Scanne models/*.onnx.json et retourne les voix selectionnables.

    Une entree par (modele, speaker). Les modeles a tres nombreux speakers
    (corpus mls) sont plafonnes a MAX_SPEAKERS_SHOWN entrees.
    """
    voices: list[VoiceInfo] = []
    for meta_path in sorted(models_dir.glob("*.onnx.json")):
        onnx_path = meta_path.with_suffix("")  # retire .json -> .onnx
        if not onnx_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        model = onnx_path.stem  # ex: fr_FR-upmc-medium (sans .onnx)
        quality = meta.get("audio", {}).get("quality", "medium")
        speaker_map = meta.get("speaker_id_map") or {}
        if not speaker_map:
            short = model.replace("fr_FR-", "").rsplit("-", 1)[0]
            speaker_map = {short: 0}
        speakers = sorted(speaker_map.items(), key=lambda kv: kv[1])[:MAX_SPEAKERS_SHOWN]
        for speaker_name, speaker_id in speakers:
            voices.append(VoiceInfo(
                model=model,
                model_path=onnx_path,
                speaker_id=speaker_id,
                speaker_name=speaker_name,
                quality=quality,
            ))
    return voices


def find_voice(
    voices: list[VoiceInfo], model: str, speaker_id: int
) -> Optional[VoiceInfo]:
    """Retrouve une VoiceInfo par (model, speaker_id)."""
    for voice in voices:
        if voice.model == model and voice.speaker_id == speaker_id:
            return voice
    return None
