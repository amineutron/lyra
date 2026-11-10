"""
Lyra Client - Francais parle : phrases lisibles et texte adapte a l'oreille.

Logique pure (sans audio ni reseau), testable en table :
- describe_action : "tv.volume_up" -> "monter le volume de la télé"
- confirm_question : phrase de confirmation parlee (normale, sensible, destructive)
- humanize_for_speech : nettoie une reponse pour la synthese vocale
  (pas de symboles, de liens, de noms de fonctions, de JSON lu a voix haute)

Le demon n'est pas touche : tout se fait cote client a partir du payload du
ask (outil + arguments) et des textes de sortie.
"""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any, Mapping, Optional

MAX_SPOKEN_CHARS = 300
SCREEN_POINTER = "Le détail est affiché à l'écran."

# Libelles lisibles : "serveur.outil" -> (phrase avec arguments, phrase sans).
# La premiere forme est utilisee si tous les champs {x} sont presents.
_ACTIONS: dict[str, tuple[str, str]] = {
    # --- TV Philips
    "tv.get_state": ("consulter l'état de la télé", "consulter l'état de la télé"),
    "tv.power_on": ("allumer la télé", "allumer la télé"),
    "tv.power_off": ("éteindre la télé", "éteindre la télé"),
    "tv.screen_off": ("éteindre l'écran de la télé en gardant le son",
                      "éteindre l'écran de la télé en gardant le son"),
    "tv.screen_on": ("rallumer l'écran de la télé", "rallumer l'écran de la télé"),
    "tv.mute": ("couper ou remettre le son de la télé",
                "couper ou remettre le son de la télé"),
    "tv.volume_up": ("monter le volume de la télé de {step}",
                     "monter le volume de la télé"),
    "tv.volume_down": ("baisser le volume de la télé de {step}",
                       "baisser le volume de la télé"),
    "tv.volume_set": ("régler le volume de la télé à {level}",
                      "régler le volume de la télé"),
    "tv.launch_app": ("lancer {app} sur la télé", "lancer une application sur la télé"),
    "tv.list_apps": ("lister les applications de la télé",
                     "lister les applications de la télé"),
    "tv.send_key": ("envoyer la touche {key} à la télé",
                    "envoyer une touche de télécommande"),
    "tv.youtube_video": ("lancer une vidéo YouTube sur la télé",
                         "lancer une vidéo YouTube sur la télé"),
    "tv.ambilight_on": ("allumer l'Ambilight", "allumer l'Ambilight"),
    "tv.ambilight_off": ("éteindre l'Ambilight", "éteindre l'Ambilight"),
    "tv.ambilight_mode": ("changer le mode Ambilight pour {mode}",
                          "changer le mode Ambilight"),
    # --- Ampli Denon
    "denon.get_status": ("consulter l'état de l'ampli", "consulter l'état de l'ampli"),
    "denon.power_on": ("allumer l'ampli", "allumer l'ampli"),
    "denon.power_off": ("éteindre l'ampli", "éteindre l'ampli"),
    "denon.mute_on": ("couper le son de l'ampli", "couper le son de l'ampli"),
    "denon.mute_off": ("remettre le son de l'ampli", "remettre le son de l'ampli"),
    "denon.mute_toggle": ("couper ou remettre le son de l'ampli",
                          "couper ou remettre le son de l'ampli"),
    "denon.set_input": ("passer l'ampli sur la source {source}",
                        "changer la source de l'ampli"),
    "denon.volume_up": ("monter le volume de l'ampli", "monter le volume de l'ampli"),
    "denon.volume_down": ("baisser le volume de l'ampli",
                          "baisser le volume de l'ampli"),
    "denon.volume_set": ("régler le volume de l'ampli à {level}",
                         "régler le volume de l'ampli"),
    # --- Lumieres Hue
    "hue.turn_on_group": ("allumer les lumières", "allumer les lumières"),
    "hue.turn_off_group": ("éteindre les lumières", "éteindre les lumières"),
    "hue.turn_on_light": ("allumer la lumière {light_name}", "allumer une lumière"),
    "hue.turn_off_light": ("éteindre la lumière {light_name}", "éteindre une lumière"),
    "hue.activate_scene_by_name": ("activer la scène {scene_name}",
                                   "activer une scène lumineuse"),
    "hue.set_group_brightness": ("régler la luminosité des lumières à {brightness}",
                                 "régler la luminosité des lumières"),
    "hue.set_brightness": ("régler la luminosité d'une lumière à {brightness}",
                           "régler la luminosité d'une lumière"),
    "hue.hue_beat_start": ("lancer la chorégraphie lumineuse sur la musique",
                           "lancer la chorégraphie lumineuse sur la musique"),
    "hue.hue_beat_stop": ("arrêter la chorégraphie lumineuse",
                          "arrêter la chorégraphie lumineuse"),
    "hue.hue_beat_status": ("consulter l'état de la chorégraphie lumineuse",
                            "consulter l'état de la chorégraphie lumineuse"),
    # --- Chromecast
    "catt.cast_browser": ("diffuser l'onglet du navigateur sur la télé",
                          "diffuser l'onglet du navigateur sur la télé"),
    "catt.cast_pause": ("mettre la diffusion en pause", "mettre la diffusion en pause"),
    "catt.cast_resume": ("reprendre la diffusion", "reprendre la diffusion"),
    "catt.cast_stop": ("arrêter la diffusion", "arrêter la diffusion"),
    "catt.cast_status": ("consulter l'état de la diffusion",
                         "consulter l'état de la diffusion"),
    "catt.cast_info": ("consulter les infos du média en cours",
                       "consulter les infos du média en cours"),
    # --- Machines virtuelles et sauvegardes
    "fedora.vm_start": ("démarrer la machine virtuelle {vm_name}",
                        "démarrer une machine virtuelle"),
    "fedora.vm_stop": ("arrêter la machine virtuelle {vm_name}",
                       "arrêter une machine virtuelle"),
    "fedora.vm_status": ("consulter l'état de la machine virtuelle {vm_name}",
                         "consulter l'état des machines virtuelles"),
    "fedora.vm_destroy": ("supprimer définitivement la machine virtuelle {vm_name}",
                          "supprimer définitivement une machine virtuelle"),
    "fedora.vm_clone": ("cloner la machine virtuelle {source_vm} vers {new_vm_name}",
                        "cloner une machine virtuelle"),
    "fedora.vm_exec": ("exécuter une commande dans la machine virtuelle {vm_name}",
                       "exécuter une commande dans une machine virtuelle"),
    "fedora.vm_copy": ("copier des fichiers avec la machine virtuelle {vm_name}",
                       "copier des fichiers avec une machine virtuelle"),
    "fedora.vm_export": ("exporter la machine virtuelle {vm_name}",
                         "exporter une machine virtuelle"),
    "fedora.vm_import": ("importer une machine virtuelle", "importer une machine virtuelle"),
    "fedora.vm_snapshot": ("gérer les instantanés de la machine virtuelle {vm_name}",
                           "gérer les instantanés d'une machine virtuelle"),
    "fedora.backup_create": ("créer une sauvegarde {type}", "créer une sauvegarde"),
    "fedora.backup_list": ("lister les sauvegardes", "lister les sauvegardes"),
    "fedora.backup_status": ("consulter l'état des sauvegardes",
                             "consulter l'état des sauvegardes"),
    "fedora.backup_verify": ("vérifier les sauvegardes", "vérifier les sauvegardes"),
    "fedora.backup_restore": ("restaurer une sauvegarde", "restaurer une sauvegarde"),
    "fedora.backup_clean": ("nettoyer les anciennes sauvegardes",
                            "nettoyer les anciennes sauvegardes"),
}

_SNAPSHOT_ACTIONS = {
    "list": "lister les instantanés de la machine virtuelle {vm_name}",
    "create": "créer un instantané de la machine virtuelle {vm_name}",
    "restore": "restaurer un instantané de la machine virtuelle {vm_name}",
    "revert": "restaurer un instantané de la machine virtuelle {vm_name}",
    "delete": "supprimer un instantané de la machine virtuelle {vm_name}",
    "delete-all": "supprimer tous les instantanés de la machine virtuelle {vm_name}",
}

_SERVER_LABELS = {
    "tv": "la télé", "denon": "l'ampli", "hue": "les lumières",
    "catt": "la diffusion", "cast": "la diffusion", "fedora": "le serveur",
    "tracking": "le suivi des tâches",
}

# Outils sans prefixe serveur (noms historiques) -> prefixe
_BARE_PREFIXES = (("vm_", "fedora"), ("backup_", "fedora"))


def _full_name(tool: str) -> str:
    tool = (tool or "").strip()
    if "." in tool:
        return tool
    for prefix, server in _BARE_PREFIXES:
        if tool.startswith(prefix):
            return f"{server}.{tool}"
    return tool


def _fill(template: str, arguments: Mapping[str, Any]) -> Optional[str]:
    """Remplit {champ} ; None si un champ manque ou est vide."""
    fields = re.findall(r"{(\w+)}", template)
    values = {}
    for field in fields:
        value = arguments.get(field)
        if value is None or str(value).strip() == "":
            return None
        values[field] = _readable_value(value)
    return template.format(**values)


def _readable_value(value: Any) -> str:
    if isinstance(value, bool):
        return "oui" if value else "non"
    return str(value).replace("_", " ").strip()


def _generic_phrase(full: str) -> str:
    """Repli pour un outil absent de la table : mots du nom + serveur."""
    server, _, name = full.rpartition(".")
    words = name.replace("_", " ").strip() or "une action"
    label = _SERVER_LABELS.get(server)
    return f"{words} ({label})" if label else words


def describe_action(tool: str, arguments: Optional[Mapping[str, Any]] = None) -> str:
    """Phrase lisible (infinitif) decrivant ce que fait l'outil."""
    args = arguments or {}
    full = _full_name(tool)
    if full == "fedora.vm_snapshot":
        template = _SNAPSHOT_ACTIONS.get(str(args.get("action", "")).lower())
        if template:
            filled = _fill(template, args)
            if filled:
                return filled
    entry = _ACTIONS.get(full)
    if entry is None:
        return _generic_phrase(full)
    with_args, without_args = entry
    return _fill(with_args, args) or without_args


def confirm_question(tool: str, arguments: Optional[Mapping[str, Any]] = None,
                     danger: bool = False, destructive: bool = False) -> str:
    """Question de confirmation parlee, du ton adapte a la gravite."""
    action = describe_action(tool, arguments)
    if destructive:
        return (f"Attention, action irréversible : {action}. "
                "Dis oui pour confirmer, ou non pour annuler.")
    if danger:
        return f"Attention, action sensible : {action}. Dis oui pour confirmer."
    return f"Je vais {action}. Tu confirmes ?"


# --------------------------------------------------------------------------
# Texte adapte a l'oreille
# --------------------------------------------------------------------------

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_TAG_RE = re.compile(r"^\s*\[[+\-!?*]\]\s*")
_PROMPT_SUFFIX_RE = re.compile(r"\s*\[[oOyY]/[nN](/[mM])?\]\s*$")
_CODE_BLOCK_RE = re.compile(r"```.*?```", re.S)
_URL_RE = re.compile(r"https?://\S+|www\.\S+")
_IPV4_RE = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?\b")
_TOOL_ID_RE = re.compile(r"\b(?:[a-z]+\.)?[a-z]+(?:_[a-z]+)+\b")
_MARKUP_DROP_RE = re.compile(r"[*_`#>~\[\]{}]+")
_MARKUP_SPACE_RE = re.compile(r"[|=]+")
_SPACE_BEFORE_STOP_RE = re.compile(r"\s+([.,])")
_BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+", re.M)
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")

_UNITS = (
    (re.compile(r"(\d)\s?%"), r"\1 pour cent"),
    (re.compile(r"(\d)\s?°\s?C\b"), r"\1 degrés"),
    (re.compile(r"(\d)\s?(?:GB|Go|GiB|Gio)\b"), r"\1 gigaoctets"),
    (re.compile(r"(\d)\s?(?:MB|Mo|MiB|Mio)\b"), r"\1 mégaoctets"),
    (re.compile(r"(\d)\s?ms\b"), r"\1 millisecondes"),
    (re.compile(r"(\d)\s?kHz\b"), r"\1 kilohertz"),
    (re.compile(r"(\d)\s?dB\b"), r"\1 décibels"),
)


def _tool_id_to_words(match: "re.Match[str]") -> str:
    token = match.group(0)
    entry = _ACTIONS.get(_full_name(token))
    if entry:
        return entry[1]
    return token.rpartition(".")[2].replace("_", " ")


def _is_structured(text: str) -> bool:
    stripped = text.strip()
    if not stripped or stripped[0] not in "{[":
        return False
    try:
        json.loads(stripped)
    except ValueError:
        return False
    return True


def _drop_symbols(text: str) -> str:
    """Retire emojis et symboles graphiques (categories Unicode S* hors monnaie)."""
    kept = []
    for char in text:
        category = unicodedata.category(char)
        if category in ("So", "Sk", "Sm") and char not in "+-=<>":
            continue
        kept.append(char)
    return "".join(kept)


def _cut_at_sentence(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    kept = ""
    for sentence in _SENTENCE_RE.split(text):
        candidate = f"{kept} {sentence}".strip()
        if len(candidate) > limit:
            break
        kept = candidate
    if kept:
        return kept
    # une seule phrase trop longue : coupe au dernier mot, sans points de suspension
    return text[:limit].rsplit(" ", 1)[0].rstrip(",;:")


def humanize_for_speech(text: str, limit: int = MAX_SPOKEN_CHARS) -> str:
    """Texte a ecouter : sans codes, symboles, liens ni noms de fonctions.

    JSON ou tres long : on renvoie vers l'ecran plutot que de tout lire.
    """
    cleaned = _ANSI_RE.sub("", text or "").strip()
    cleaned = _TAG_RE.sub("", cleaned)
    cleaned = _PROMPT_SUFFIX_RE.sub("", cleaned)
    if not cleaned:
        return ""
    if _is_structured(cleaned):
        return SCREEN_POINTER

    cleaned = _CODE_BLOCK_RE.sub(" ", cleaned)
    lines = [ln for ln in cleaned.splitlines() if ln.strip()]
    many_lines = len(lines) > 6
    if many_lines:
        cleaned = lines[0]
    cleaned = _BULLET_RE.sub("", cleaned)
    cleaned = _URL_RE.sub("un lien", cleaned)
    cleaned = _IPV4_RE.sub("une adresse IP", cleaned)
    cleaned = _TOOL_ID_RE.sub(_tool_id_to_words, cleaned)
    for pattern, replacement in _UNITS:
        cleaned = pattern.sub(replacement, cleaned)
    cleaned = _MARKUP_DROP_RE.sub("", cleaned)
    cleaned = _MARKUP_SPACE_RE.sub(" ", cleaned)
    cleaned = _drop_symbols(cleaned)
    cleaned = " ".join(cleaned.replace("\n", ". ").split())
    cleaned = _SPACE_BEFORE_STOP_RE.sub(r"\1", cleaned)
    cleaned = _cut_at_sentence(cleaned, limit)
    if many_lines and cleaned:
        cleaned = f"{cleaned.rstrip('.')}. {SCREEN_POINTER}"
    return cleaned
