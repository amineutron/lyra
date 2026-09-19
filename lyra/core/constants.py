"""
Constantes partagees entre les modules Lyra.

Source unique de verite pour les listes d'outils (DANGEROUS_TOOLS, ASYNC_TOOLS, etc.)
afin d'eviter les divergences silencieuses entre les fichiers.
"""

from __future__ import annotations

# Outils qui exigent une confirmation explicite "oui" et un affichage rouge.
# vm_exec execute une commande arbitraire extraite du texte utilisateur :
# jamais d'auto-confirmation, meme en mode -y.
DANGEROUS_TOOLS: frozenset[str] = frozenset({
    "vm_destroy",
    "vm_stop",
    "vm_exec",
    "backup_restore",
    "backup_clean",
    "vm_clone_system",
    # Audit 2026-09-19 : ces trois-la ecrivent ou ecrasent sans etre listes.
    "vm_snapshot",      # action=revert remplace l'etat, action=delete supprime
    "vm_import",        # copie un disque dans libvirt + virsh define (sudo)
    "vm_copy",          # ecrase des fichiers sur l'hote ou dans la VM (scp)
    # Interceptes hors MCP par HESTIA (tracking.*) : suppression d'une session
    # de suivi, kill d'un processus enregistre (lyra#24).
    "delete",
    "kill_task",
})

# Sous-ensemble REELLEMENT destructif (perte/ecrasement irreversible).
# Les autres DANGEROUS sont "sensibles" : confirmation exigee mais pas de
# destruction (vm_stop est reversible, vm_clone_system CREE une VM...).
DESTRUCTIVE_TOOLS: frozenset[str] = frozenset({
    "vm_destroy",
    "backup_restore",
    "backup_clean",
})

# Outils domotique executes sans confirmation en mode performance.
# Noms PREFIXES par le serveur : la comparaison est exacte (actions.py,
# main_rag.py). Les "cast_*" etaient listes sans prefixe et ne matchaient
# jamais (audit 2026-09-19) ; les outils Denon et les lectures manquaient.
PERFORMANCE_TOOLS: frozenset[str] = frozenset({
    "tv.power_on", "tv.power_off", "tv.volume_up", "tv.volume_down",
    "tv.volume_set", "tv.mute", "tv.ambilight_on", "tv.ambilight_off",
    "tv.ambilight_mode", "tv.launch_app", "tv.youtube_video",
    "tv.screen_off", "tv.screen_on", "tv.get_state", "tv.list_apps",
    "hue.turn_on_light", "hue.turn_off_light", "hue.set_brightness",
    "hue.set_color_rgb", "hue.set_color_temperature", "hue.set_color_preset",
    "hue.set_group_brightness", "hue.set_group_color_rgb",
    "hue.set_group_color_preset", "hue.turn_on_group", "hue.turn_off_group",
    "hue.activate_scene_by_name", "hue.set_scene", "hue.alert_light",
    "hue.set_light_effect", "hue.hue_beat_start", "hue.hue_beat_stop",
    "hue.hue_beat_set", "hue.hue_beat_status", "hue.get_all_lights",
    "hue.get_all_groups", "hue.get_all_scenes", "hue.get_light",
    "hue.get_group", "hue.find_light_by_name",
    "denon.power_on", "denon.power_off", "denon.volume_up",
    "denon.volume_down", "denon.volume_set", "denon.mute_on",
    "denon.mute_off", "denon.mute_toggle", "denon.set_input",
    "denon.get_status",
    "catt.cast_youtube", "catt.cast_url", "catt.cast_stop", "catt.cast_pause",
    "catt.cast_resume", "catt.cast_volume", "catt.cast_seek",
    "catt.cast_browser", "catt.cast_browser_dual", "catt.cast_dual_stop",
    "catt.cast_dual_resync", "catt.cast_dual_offset", "catt.cast_status",
    "catt.cast_info", "catt.cast_scan",
})

# Templates valides pour le filtre du dashboard tracking
VALID_TRACKING_FILTERS: frozenset[str] = frozenset({
    "lyra_task", "errors", "download", "machine", "movie", "free",
})


def is_dangerous_tool(tool_name: str) -> bool:
    """Vrai si l'outil (prefixe serveur ou non) exige une confirmation.

    Les sets ci-dessus contiennent des noms COURTS ; les appelants recoivent
    souvent "fedora.vm_stop" — comparer sans normaliser laissait passer les
    outils dangereux prefixes (regression 2026-08-14).
    """
    return tool_name.split(".")[-1] in DANGEROUS_TOOLS


def is_destructive_tool(tool_name: str) -> bool:
    """Vrai si l'outil detruit/ecrase des donnees (sous-ensemble rouge)."""
    return tool_name.split(".")[-1] in DESTRUCTIVE_TOOLS


def is_performance_tool(tool_name: str) -> bool:
    """Vrai si l'outil (nom prefixe) s'execute sans confirmation en mode performance.

    Jamais vrai pour un outil dangereux, quel que soit le contenu de la liste.
    """
    return tool_name in PERFORMANCE_TOOLS and not is_dangerous_tool(tool_name)
