"""
Constantes partagees entre les modules Lyra.

Source unique de verite pour les listes d'outils (DANGEROUS_TOOLS, ASYNC_TOOLS, etc.)
afin d'eviter les divergences silencieuses entre les fichiers.
"""

from __future__ import annotations

# Outils qui exigent une confirmation explicite "oui" et un affichage rouge
DANGEROUS_TOOLS: frozenset[str] = frozenset({
    "vm_destroy",
    "vm_stop",
    "backup_restore",
    "backup_clean",
    "vm_clone_system",
})

# Outils domotique executes sans confirmation en mode performance
PERFORMANCE_TOOLS: frozenset[str] = frozenset({
    "tv.power_on", "tv.power_off", "tv.volume_up", "tv.volume_down",
    "tv.volume_set", "tv.mute", "tv.ambilight_on", "tv.ambilight_off",
    "tv.ambilight_mode", "tv.launch_app", "tv.youtube_video",
    "hue.turn_on_light", "hue.turn_off_light", "hue.set_brightness",
    "hue.set_color_rgb", "hue.set_group_brightness",
    "hue.set_group_color_rgb", "hue.set_group_color_preset",
    "hue.turn_on_group", "hue.turn_off_group", "hue.activate_scene_by_name",
    "cast_youtube", "cast_url", "cast_stop", "cast_pause",
    "cast_resume", "cast_volume", "cast_seek", "cast_browser",
})

# Templates valides pour le filtre du dashboard tracking
VALID_TRACKING_FILTERS: frozenset[str] = frozenset({
    "lyra_task", "errors", "download", "machine", "movie", "free",
})
