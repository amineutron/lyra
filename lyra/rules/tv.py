"""Regles de detection pour les outils TV Philips (tv.*)."""

import re

from .base import make, normalize

_TV_KW = r'\b(?:tv|t[eé]l[eé](?:vision)?)\b'
_APP_NAMES = r'\b(?:netflix|youtube|spotify|prime|disney|plex|arte|twitch|tubi|dazn)\b'

_AMBI_COLOR_MAP = {
    "rouge": (255, 0, 0), "vert": (0, 255, 0), "verte": (0, 255, 0),
    "bleu": (0, 0, 255), "bleue": (0, 0, 255), "violet": (128, 0, 128),
    "violette": (128, 0, 128), "orange": (255, 165, 0), "jaune": (255, 255, 0),
    "rose": (255, 192, 203), "blanc": (255, 255, 255), "blanche": (255, 255, 255),
    "cyan": (0, 255, 255)
}


# Ambilight, ou "les leds de/derriere la tele"
_AMBI_KW = r'\b(?:ambilight|leds?\s+(?:de\s+|derriere\s+)?(?:la\s+)?(?:tele|tv|television))\b'
_AMBI_MODES = {"musique": "follow_audio", "audio": "follow_audio", "son": "follow_audio",
               "video": "follow_video", "film": "follow_video",
               "lounge": "lounge_light", "ambiance": "lounge_light", "manuel": "manual",
               "image": "follow_video"}


# Touches de telecommande (noms valides de pylips-mcp send_key) : on ne devine jamais
_TV_KEYS = {
    "retour": "Back", "back": "Back", "accueil": "Home", "home": "Home", "ok": "Confirm",
    "valide": "Confirm", "entree": "Confirm", "haut": "CursorUp", "bas": "CursorDown",
    "gauche": "CursorLeft", "droite": "CursorRight", "pause": "Pause", "lecture": "Play",
    "play": "Play", "stop": "Stop", "info": "Info", "options": "Options", "source": "Source",
    "quitter": "Exit", "sortie": "Exit",
}


def detect(query: str):
    q = normalize(query)

    # tv.list_apps (lyra#24) : applis installees sur la TV
    if re.search(r'\b(?:applis?|applications?)\b', q) and re.search(r'\b(?:tele|tv|televiseur)\b', q) and \
            re.search(r'\b(?:quell(?:es?)?|liste[rz]?|affiche[rz]?|montre[rz]?)\b', q):
        return make("tv.list_apps", {}, "rule: liste les applis de la tele", 0.91)

    # tv.send_key (lyra#24) : "appuie sur X" / "touche X (sur la tele)", X parmi les touches connues
    m_key = re.search(r'\b(?:appuie[rz]?\s+sur(?:\s+la\s+touche)?|touche)\s+(\w+)', q)
    if m_key and m_key.group(1) in _TV_KEYS:
        return make("tv.send_key", {"key": _TV_KEYS[m_key.group(1)]},
                    f"rule: touche {m_key.group(1)}", 0.90)

    # tv.ambilight_mode: "ambilight/leds en mode musique|video|lounge" (lyra#22 : "les leds
    # de la tele en mode musique" tombait sur sound_only, qui coupe l'image)
    if re.search(_AMBI_KW, q):
        m_mode = re.search(r'\bmode\s+(musique|audio|son|video|film|lounge|ambiance|manuel)\b', q)
        if m_mode:
            return make("tv.ambilight_mode", {"mode": _AMBI_MODES[m_mode.group(1)]},
                        f"rule: ambilight_mode {m_mode.group(1)}", 0.93)
        # "l'ambilight qui suit la musique / la video" (jeu 5, 2026-09-19)
        m_suit = re.search(r'\b(?:suit|suive|suivre|synchro(?:nise)?|cale)\b.{0,25}\b(musique|son|audio|video|film|image)\b', q)
        if m_suit:
            return make("tv.ambilight_mode", {"mode": _AMBI_MODES[m_suit.group(1)] if m_suit.group(1) in _AMBI_MODES else "follow_video"},
                        f"rule: ambilight suit {m_suit.group(1)}", 0.92)

    # tv.screen_off: "son seul", "mode musique/audio" — pas besoin de "tv" dans la phrase.
    # (pylips-mcp n'a jamais expose "sound_only" : screen_off eteint l'ecran et
    # garde le son, c'est le mode musique ; audit 2026-09-19)
    if re.search(r'\b(?:son\s+seul|mode\s+(?:musique|audio|son|radio)|musique\s+seul(?:e|ement)?)\b', q) and \
            not re.search(_AMBI_KW, q):
        return make("tv.screen_off", {}, "rule: tv son seul (screen_off)", 0.97)

    # tv.screen_off: "coupe/eteins l'ecran/la dalle" — "dalle" et "ecran" suffisent
    if re.search(r'\b(?:etein[ts]?|coupes?|desactiv[ea]?[rz]?|mets?\s+en\s+veille)\b', q) and \
            re.search(r'\b(?:ecran|affichage|dalle|image)\b', q):
        return make("tv.screen_off", {}, "rule: tv screen_off", 0.95)

    # tv.screen_on: "rallume/reactive l'ecran/la dalle"
    if re.search(r'\b(?:rallume[rz]?|reactiv[ea]?[rz]?|remet[sz]?|remonte[rz]?|affiche[rz]?)\b', q) and \
            re.search(r'\b(?:ecran|affichage|dalle|image)\b', q):
        return make("tv.screen_on", {}, "rule: tv screen_on", 0.95)

    if re.search(_TV_KW, q):
        # tv.get_state: une question d'etat n'est pas un ordre (lyra#23 : "est-ce que
        # la tele est en veille" tombait sur power_off)
        # "il est"/"elle est" ne marque une question que devant un etat ("on eteint
        # la tele, il est tard" est un ordre : jeu 4, 2026-09-19)
        if re.search(r'^est-ce que\b|\?\s*$|\b(?:est-elle|est-il)\b'
                     r'|\b(?:elle|il)\s+est\s+(?:en\s+)?(?:veille|allumee?|eteinte?|marche|standby)\b', q) and \
                re.search(r'\b(?:veille|allumee?|eteinte?|en marche|etat|standby)\b', q) and \
                not re.search(r'^(?:allume|eteins|mets|coupe|remets|peux-tu|tu peux)\b', q):
            return make("tv.get_state", {}, "rule: tv get_state (question)", 0.92)

        # tv.power_off: "eteins/veille la tv" - excl. volume/ambilight/denon/ecran
        if re.search(r'\b(?:etein[ts]?|eteignez|eteindre|arrete[rz]?|ferme[rz]?|veille|standby)\b', q) and \
                not re.search(r'\b(?:volume|son|ambilight|leds?|denon|ecran|affichage)\b', q):
            return make("tv.power_off", {}, "rule: tv power_off", 0.93)

        # tv.power_on: "allume/reveille/demarre la tv" - excl. apps + ambilight
        if re.search(r'\b(?:allume[rz]?|active[rz]?|reveille[rz]?|demarr[ea]?[rz]?|ouvre[rz]?)\b', q) and \
                not re.search(_APP_NAMES, q) and \
                not re.search(r'\b(?:ambilight|leds?)\b', q):
            return make("tv.power_on", {}, "rule: tv power_on", 0.93)

        # tv.youtube_video: URL YouTube + contexte tv (pas de verbe cast)
        m_yt = re.search(r'https?://(?:www\.)?(?:youtube\.com/watch\S*|youtu\.be/[\w-]+)', query, re.IGNORECASE)   # casse de l'id conservee
        if m_yt and not re.search(r'\b(?:caste?[rz]?|diffuse?[rz]?)\b', q):
            return make("tv.youtube_video", {"video": m_yt.group(0)},   # schema pylips-mcp : "video"
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
    if re.search(_AMBI_KW, q):   # "ambilight" ou "les leds de la tele" (jeu 6 : "eteins les leds de la tele" -> power_off)
        if re.search(r'\b(?:etein[ts]?|eteignez|eteindre|desactive[rz]?|coupe[rz]?|arrete[rz]?|enleve[rzs]?|enlever|vire[rz]?|retire[rz]?|degage[rz]?)\b', q):
            return make("tv.ambilight_off", {}, "rule: ambilight_off", 0.93)
        m_amb = re.search(r'\b(?:ambiance|style)\s+(lounge|musique|audio|video|film|manuel)\b', q)
        if m_amb:
            return make("tv.ambilight_mode", {"mode": _AMBI_MODES[m_amb.group(1)]},
                        f"rule: ambilight ambiance {m_amb.group(1)}", 0.92)
        # Une couleur ("ambilight en rouge") : pylips-mcp n'expose pas de reglage
        # de couleur (ambilight_on/off/mode seulement) ; l'ancien tv.ambilight_color
        # n'existait dans aucun serveur. En attendant, le mode manuel (FOLLOW_COLOR)
        # est l'action la plus proche qui existe.
        m_ac = re.search(r'\b(rouge|verte?|bleue?|violet(?:te)?|orange|jaune|rose|blanc(?:he)?|cyan)\b', q)
        if m_ac:
            return make("tv.ambilight_mode", {"mode": "manual"},
                        f"rule: ambilight couleur {m_ac.group(1)} (mode manuel, couleur non reglable)", 0.80)
        # "les leds de la tele" sans verbe d'allumage : le modele decide ; "ambilight" seul reste un allumage
        if re.search(r'\bambilight\b', q) or \
                re.search(r'\b(?:allume[rz]?|active[rz]?|remets?|rallume[rz]?|mets?)\b', q):
            return make("tv.ambilight_on", {}, "rule: ambilight_on (defaut)", 0.93)
        return None

    return None
