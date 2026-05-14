"""Regles de detection pour les outils HUE (Philips Hue)."""

import re
from typing import Optional

from .base import normalize, make

_RGB_COLOR_MAP = {
    "rouge": (255, 0, 0), "vert": (0, 255, 0), "verte": (0, 255, 0),
    "bleu": (0, 0, 255), "bleue": (0, 0, 255), "violet": (128, 0, 128),
    "violette": (128, 0, 128), "orange": (255, 165, 0), "jaune": (255, 255, 0),
    "rose": (255, 192, 203), "blanc": (255, 255, 255), "blanche": (255, 255, 255),
    "cyan": (0, 255, 255)
}


def detect(query: str):
    q = normalize(query)

    # hue.activate_scene_by_name (Cas A: avec groupe specifique)
    # Doit venir AVANT vm_start ET AVANT set_color_rgb
    m_grp = re.search(
        r'(?:mets?|mettre[sz]?|applique[rz]?|active[rz]?|utilise[rz]?|lance[rz]?)\s+'
        r'(?:(?:la\s+)?scene\s+)?([\w][\w\s.-]*?)\s+'
        r'(?:sur|dans)\s+(?:le\s+)?(?:groupe?\s*(\d+)|(?:les?\s+)?(?:lumieres?|lampes?))',
        q
    )
    if m_grp:
        scene_name = m_grp.group(1).strip()
        group_id = int(m_grp.group(2)) if m_grp.group(2) else 81
        return make("hue.activate_scene_by_name",
                    {"scene_name": scene_name, "group_id": group_id},
                    f"rule: scene {scene_name!r} groupe {group_id}", 0.93)

    # hue.activate_scene_by_name (Cas B: sans groupe)
    m = re.search(
        r'(?:lance[rz]?|active[rz]?|demarr[ea]?[rz]?|execute[rz]?|applique[rz]?|mets?)\s+'
        r'(?:la\s+)?scene\s+([\w][\w. -]*)',
        q
    )
    if m:
        return make("hue.activate_scene_by_name", {"scene_name": m.group(1).strip()},
                    "rule: lance la scene NAME", 0.93)

    # hue.get_all_scenes: "liste/affiche/quelles mes/les scenes ou ambiances"
    if re.search(r'\b(?:scenes?|ambiances?)\b', q) and (
            re.search(r'\b(?:liste[rz]?|affiche[rz]?|quell(?:es?)?|montre[rz]?|donne[rz]?|voir)\b', q) or
            re.search(r'\b(?:mes|les|toutes?|disponibles?)\s+(?:scenes?|ambiances?)\b', q) or
            re.search(r'\b(?:scenes?|ambiances?)\s+(?:disponibles?|existantes?|j.?ai)\b', q)
    ):
        return make("hue.get_all_scenes", {}, "rule: liste scenes/ambiances hue", 0.92)

    # hue.turn_on_group: "allume [toutes les/les] lumieres" (groupe entier)
    if re.search(r'\b(?:allume[rz]?|actives?[rz]?|allumez)\b', q) and \
            (re.search(r'\btoutes?\s+les\s+(?:lumieres?|lampes?)\b', q) or
             re.search(r'\bles\s+(?:lumieres|lampes)\b', q)):
        return make("hue.turn_on_group", {"group_id": 81},
                    "rule: allume les/toutes les lumieres -> group", 0.93)

    # hue.turn_off_group: "eteins [toutes les/les] lumieres" (groupe entier)
    if re.search(r'\b(?:etein[ts]?|eteignez|eteindre|desactive[rz]?|coupe[rz]?)\b', q) and \
            (re.search(r'\btoutes?\s+les\s+(?:lumieres?|lampes?)\b', q) or
             re.search(r'\bles\s+(?:lumieres?|lampes?)\b', q)):
        return make("hue.turn_off_group", {"group_id": 81},
                    "rule: eteins les/toutes les lumieres -> group", 0.93)

    # hue.turn_off_light: "eteins la lumiere NAME" (lumiere specifique)
    m = re.search(
        r'(?:etein[ts]?|eteignez|eteindre|desactive[rz]?|ferme[rz]?)\s+'
        r'la\s+(?:lumiere|lampe|ampoule)\s+([\w]+)',
        q
    )
    if m:
        return make("hue.turn_off_light", {"light_name": m.group(1).strip()},
                    "rule: eteins la lumiere NAME", 0.90)

    # hue.turn_on_light: "allume la lumiere NAME" (lumiere specifique, singulier)
    m = re.search(
        r'(?:allume[rz]?|active[rz]?)\s+la\s+(?:lumiere|lampe|ampoule)\s+([\w]+)',
        q
    )
    if m:
        return make("hue.turn_on_light", {"light_name": m.group(1).strip()},
                    "rule: allume la lumiere NAME", 0.90)

    # hue.set_brightness (Cas 1a: "luminosite a N pour cent / N%")
    m_pct = re.search(r'luminosite?\s+a\s+(\d+)\s*(?:pour\s*cent|%)?', q)
    if m_pct:
        brightness = int(int(m_pct.group(1)) * 255 // 100)
        return make("hue.set_brightness", {"brightness": brightness},
                    f"rule: set_brightness {brightness}", 0.92)

    # hue.set_brightness (Cas 1b: "lumieres/lampes a N%")
    m_lum_pct = re.search(r'(?:lumieres?|lampes?)\s+a\s+(\d+)\s*(?:pour\s*cent|%)', q)
    if m_lum_pct:
        brightness = int(int(m_lum_pct.group(1)) * 255 // 100)
        return make("hue.set_brightness", {"brightness": brightness},
                    f"rule: set_brightness {brightness} (lumieres a N%)", 0.91)

    # hue.set_brightness (Cas 2a: relatif haut)
    if re.search(r'\b(?:lumieres?|lampes?|lumiere)\s+plus\s+(?:fort[esz]*|intens[aeés]*|haut[esz]*|viv[esz]*)', q) or \
            re.search(r'\b(?:monte|augmente|hausse|eleve)\b.*\bluminosite\b|\bluminosite\b.*\b(?:monte|augmente|hausse|eleve)\b', q):
        return make("hue.set_brightness", {"brightness": 200},
                    "rule: set_brightness high (relative)", 0.88)

    # hue.set_brightness (Cas 2b: relatif bas)
    if re.search(r'\b(?:lumieres?|lampes?|lumiere)\s+plus\s+(?:doux|douce[sz]*|faible[sz]*|bas[esz]*)', q) or \
            re.search(r'\b(?:baisse|diminue|reduis|attenues?)\b.*\bluminosite\b|\bluminosite\b.*\b(?:baisse|diminue|reduis|attenues?)\b', q):
        return make("hue.set_brightness", {"brightness": 50},
                    "rule: set_brightness low (relative)", 0.88)

    # hue.set_color_rgb: "lumieres en rouge/bleu/..." ou "ambiance rouge/bleue/..."
    m_rgb = re.search(r'\b(rouge|verte?|bleue?|violette?|orange|jaune|rose|blanche?|cyan)\b', q)
    if m_rgb and re.search(r'\b(?:lumieres?|lampes?|ambiance|atmosphere|couleur|mode)\b', q):
        rgb = _RGB_COLOR_MAP.get(m_rgb.group(1), (255, 255, 255))
        return make("hue.set_color_rgb", {"r": rgb[0], "g": rgb[1], "b": rgb[2]},
                    f"rule: set_color_rgb {m_rgb.group(1)}", 0.90)

    return None
