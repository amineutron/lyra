"""Regles de detection pour les outils TV Philips (tv.*)."""

import re
from typing import Optional

from .base import normalize, make

_TV_KW = r'\b(?:tv|t[eé]l[eé](?:vision)?)\b'
_APP_NAMES = r'\b(?:netflix|youtube|spotify|prime|disney|plex|arte|twitch|tubi|dazn)\b'

_AMBI_COLOR_MAP = {
    "rouge": (255, 0, 0), "vert": (0, 255, 0), "verte": (0, 255, 0),
    "bleu": (0, 0, 255), "bleue": (0, 0, 255), "violet": (128, 0, 128),
    "violette": (128, 0, 128), "orange": (255, 165, 0), "jaune": (255, 255, 0),
    "rose": (255, 192, 203), "blanc": (255, 255, 255), "blanche": (255, 255, 255),
    "cyan": (0, 255, 255)
}


def detect(query: str):
    q = normalize(query)

    if re.search(_TV_KW, q):
        # tv.screen_off: "eteins l'ecran/l'affichage", "mode musique"
        if re.search(r'\b(?:etein[ts]?|coupes?|desactiv[ea]?[rz]?|mets?\s+en\s+veille)\b', q) and \
                re.search(r'\b(?:ecran|affichage|dalle|image)\b', q):
            return make("tv.screen_off", {}, "rule: tv screen_off", 0.95)
        if re.search(r'\bmode\s+(?:musique|audio|son|radio)\b', q) and \
                re.search(r'\b(?:tv|tele|television|ecran)\b', q):
            return make("tv.screen_off", {}, "rule: tv screen_off (mode musique)", 0.93)

        # tv.screen_on: "rallume/reactive l'ecran"
        if re.search(r'\b(?:rallume[rz]?|reactiv[ea]?[rz]?|remet[sz]?|remonte[rz]?|affiche[rz]?)\b', q) and \
                re.search(r'\b(?:ecran|affichage|dalle|image)\b', q):
            return make("tv.screen_on", {}, "rule: tv screen_on", 0.95)

        # tv.power_off: "eteins/veille la tv" - excl. volume/ambilight/denon/ecran
        if re.search(r'\b(?:etein[ts]?|eteignez|eteindre|arrete[rz]?|ferme[rz]?|veille|standby)\b', q) and \
                not re.search(r'\b(?:volume|son|ambilight|denon|ecran|affichage)\b', q):
            return make("tv.power_off", {}, "rule: tv power_off", 0.93)

        # tv.power_on: "allume/reveille/demarre la tv" - excl. apps + ambilight
        if re.search(r'\b(?:allume[rz]?|active[rz]?|reveille[rz]?|demarr[ea]?[rz]?|ouvre[rz]?)\b', q) and \
                not re.search(_APP_NAMES, q) and \
                not re.search(r'\bambilight\b', q):
            return make("tv.power_on", {}, "rule: tv power_on", 0.93)

        # tv.youtube_video: URL YouTube + contexte tv (pas de verbe cast)
        m_yt = re.search(r'https?://(?:www\.)?(?:youtube\.com/watch\S*|youtu\.be/[\w-]+)', q)
        if m_yt and not re.search(r'\b(?:caste?[rz]?|diffuse?[rz]?)\b', q):
            return make("tv.youtube_video", {"video_id": m_yt.group(0)},
                        "rule: tv youtube_video URL", 0.95)

        # tv.launch_app: app name detecte + contexte TV
        m_app = re.search(_APP_NAMES, q)
        if m_app:
            return make("tv.launch_app", {"app": m_app.group(0)},
                        f"rule: tv launch_app {m_app.group(0)}", 0.94)

        # tv.mute: "sourdine/mute/silence" ou "coupe le son"
        if re.search(r'\b(?:mute|sourdine|silence|muet)\b', q) or \
                re.search(r'coupe\s+(?:le\s+)?son', q):
            return make("tv.mute", {}, "rule: tv mute", 0.93)

        # tv.volume_set: extrait le nombre ("volume TV a 45")
        m_vol = re.search(r'(?:volume|son)[^0-9]*(\d+)|(\d+)[^0-9]*(?:volume|son)', q)
        if m_vol:
            level = int(m_vol.group(1) or m_vol.group(2))
            return make("tv.volume_set", {"level": level}, "rule: tv volume_set N", 0.93)

        # tv.volume_up: "monte/augmente le volume"
        if re.search(r'\b(?:monte|augmente|hausse|eleve|plus)\b', q) and \
                re.search(r'\b(?:volume|son)\b', q):
            return make("tv.volume_up", {}, "rule: tv volume_up", 0.93)

        # tv.volume_down: "baisse/diminue le volume"
        if re.search(r'\b(?:baisse|diminue|descend|moins|reduit|reduis)\b', q) and \
                re.search(r'\b(?:volume|son)\b', q):
            return make("tv.volume_down", {}, "rule: tv volume_down", 0.93)

    # tv.ambilight: requetes sans "tv/tele" obligatoire - ambilight seul suffit
    if re.search(r'\bambilight\b', q):
        if re.search(r'\b(?:etein[ts]?|eteignez|eteindre|desactive[rz]?|coupe[rz]?|arrete[rz]?)\b', q):
            return make("tv.ambilight_off", {}, "rule: ambilight_off", 0.93)
        m_ac = re.search(r'\b(rouge|verte?|bleue?|violette?|orange|jaune|rose|blanche?|cyan)\b', q)
        if m_ac:
            rgb = _AMBI_COLOR_MAP.get(m_ac.group(1), (255, 255, 255))
            return make("tv.ambilight_color", {"r": rgb[0], "g": rgb[1], "b": rgb[2]},
                        "rule: ambilight couleur", 0.93)
        return make("tv.ambilight_on", {}, "rule: ambilight_on (defaut)", 0.93)

    return None
