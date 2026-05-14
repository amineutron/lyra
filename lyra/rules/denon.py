"""Regles de detection pour les outils DENON AVR (denon.*)."""

import re
from typing import Optional

from .base import normalize, make

_DENON_INPUT_MAP = [
    (r'\b(?:bluray|blu.ray|bd)\b', "BD"),
    (r'\b(?:jeu[xz]?|game|gaming|console)\b', "GAME"),
    (r'\b(?:satellite|sat|cable|cbl)\b', "SAT/CBL"),
    (r'\b(?:dvd)\b', "DVD"),
    (r'\b(?:media.?player|mplay|mediaplayer)\b', "MPLAY"),
    (r'\b(?:tv|tele|television)\b', "TV"),
]


def detect(query: str):
    q = normalize(query)

    if not re.search(r'\bdenon\b', q):
        return None

    # power_off: "eteins/arrete/stop" SANS contexte volume/mute
    if re.search(r'\b(?:etein[ts]?|eteignez|eteindre|stop|stoppe|arrete)\b', q) and \
            not re.search(r'\b(?:volume|son|mute|sourdine)\b', q):
        return make("denon.power_off", {}, "rule: denon power_off", 0.93)

    # power_on: "allume/demarre" (exclure si contexte mute)
    if re.search(r'\b(?:allumes?|allumez|demarre[sz]?|active)\b', q) and \
            not re.search(r'\b(?:mute|sourdine|silence|muet)\b', q):
        return make("denon.power_on", {}, "rule: denon power_on", 0.93)

    # mute_off: "demute/unmute/reactive" ou "enleve/desactive le mute"
    if re.search(r'\b(?:demute|unmute|reactive)\b', q) or \
            re.search(r'(?:enleve|desactive|remet)\s+(?:le\s+)?(?:mute|sourdine|silence)', q):
        return make("denon.mute_off", {}, "rule: denon mute_off", 0.93)

    # mute_toggle: "toggle/bascule/inverse le mute" - AVANT mute_on!
    if re.search(r'\btoggle\b', q) or re.search(r'\b(?:bascule[rz]?|inverse[rz]?)\b', q):
        return make("denon.mute_toggle", {}, "rule: denon mute_toggle", 0.90)

    # mute_on: "mute/sourdine/silence/coupe le son"
    if re.search(r'\b(?:mute|sourdine|silence|muet)\b', q) or \
            re.search(r'coupe\s+(?:le\s+)?son', q):
        return make("denon.mute_on", {}, "rule: denon mute_on", 0.93)

    # get_status: "status/etat/statut du denon" SANS chiffre ni verbe directionnel
    if re.search(r'\b(?:status|statut|etat|info[sz]?|volume)\b', q) and \
            not re.search(r'\d', q) and \
            not re.search(r'\b(?:monte|augmente|hausse|baisse|diminue|reduis)\b', q):
        return make("denon.get_status", {}, "rule: denon get_status", 0.88)

    # set_input: "change la source en bluray/hdmi/tv"
    if re.search(r'\b(?:source|entree|input|change|passe|mets?|bascule)\b', q):
        for alias_re, src_val in _DENON_INPUT_MAP:
            if re.search(alias_re, q):
                return make("denon.set_input", {"input": src_val},
                            f"rule: denon set_input {src_val}", 0.92)

    # volume_set: extrait le nombre ("volume denon a 50", "50 de volume")
    m_vol = re.search(r'(?:volume|son)[^0-9]*(\d+)|(\d+)[^0-9]*(?:volume|son)', q)
    if m_vol:
        level = int(m_vol.group(1) or m_vol.group(2))
        return make("denon.volume_set", {"level": level}, "rule: denon volume_set N", 0.93)

    # volume_up
    if re.search(r'\b(?:monte|augmente|hausse|eleve|plus)\b', q):
        return make("denon.volume_up", {}, "rule: denon volume_up", 0.90)

    # volume_down
    if re.search(r'\b(?:baisse|diminue|descend|moins|reduit|reduis)\b', q):
        return make("denon.volume_down", {}, "rule: denon volume_down", 0.90)

    return None
