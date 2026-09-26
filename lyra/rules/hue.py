"""Regles de detection pour les outils HUE (Philips Hue)."""

import re

from .base import make, normalize

_RGB_COLOR_MAP = {
    "rouge": (255, 0, 0), "vert": (0, 255, 0), "verte": (0, 255, 0),
    "bleu": (0, 0, 255), "bleue": (0, 0, 255), "violet": (128, 0, 128),
    "violette": (128, 0, 128), "orange": (255, 165, 0), "jaune": (255, 255, 0),
    "rose": (255, 192, 203), "blanc": (255, 255, 255), "blanche": (255, 255, 255),
    "cyan": (0, 255, 255)
}


# Groupe Hue par defaut (piece principale), comme turn_on_group / turn_off_group
_DEFAULT_GROUP = 81
_BEAT_PALETTES = ("ironman", "fire", "neon", "cool", "sunset", "arctic", "auto")
# Presets de hue.set_group_color_preset (hue-mcp) accessibles par la teinte du blanc.
# Teinte ABSOLUE seulement : « plus chaude / plus froide » decale la temperature
# (hue.set_color_temperature pour les jeux hors regles) et reste au modele.
_WHITE_PRESETS = (
    (r'\blumieres?\s+(?:du|de)\s+jour\b', "daylight"),
    (r'\blumieres?\s+chaudes?\b', "warm"),
    (r'\blumieres?\s+froides?\b', "cool"),
)


def _pct_to_bri(pct: int) -> int:
    """Pourcentage -> luminosite Hue (0-254 : 255 est hors limites pour le pont)."""
    return round(max(0, min(100, pct)) * 254 / 100)


def _detect_beat_and_reads(q: str):
    """Outils sans regle jusqu'a lyra#24 : hue beat, lectures, clignotement, teinte du blanc."""
    if re.search(r'\bhue[\s_-]?beat\b', q):
        if re.search(r'\b(?:arrete[rz]?|stop(?:pe[rz]?)?|coupe[rz]?|eteins?|desactive[rz]?)\b', q):
            return make("hue.hue_beat_stop", {}, "rule: arrete hue beat", 0.93)
        if re.search(r'\b(?:etat|statut|tourne|actif|marche|en\s+cours)\b', q):
            return make("hue.hue_beat_status", {}, "rule: etat de hue beat", 0.92)
        if re.search(r'\b(?:lance[rz]?|demarre[rz]?|active[rz]?|allume[rz]?|mets?)\b', q):
            palette = next((p for p in _BEAT_PALETTES if re.search(rf'\b{p}\b', q)), None)
            return make("hue.hue_beat_start", {"palette": palette} if palette else {},
                        f"rule: lance hue beat{' ' + palette if palette else ''}", 0.93)

    m = re.search(r'\b(?:fais|fait)\s+clignoter\s+la\s+(?:lampe|lumiere|ampoule)\s+(\d+)'
                  r'|\bidentifie[rz]?\s+la\s+(?:lampe|lumiere|ampoule)\s+(\d+)', q)
    if m:
        return make("hue.alert_light", {"light_id": int(m.group(1) or m.group(2))},
                    "rule: fais clignoter la lampe N", 0.92)

    if re.search(r'\bgroupes?\b', q) and re.search(r'\b(?:liste[rz]?|affiche[rz]?|quels?|montre[rz]?)\b', q) \
            and re.search(r'\b(?:lumieres?|lampes?|hue)\b', q):
        return make("hue.get_all_groups", {}, "rule: liste les groupes hue", 0.91)

    if re.search(r'\b(?:liste[rz]?|affiche[rz]?|montre[rz]?)\s+(?:les|mes|toutes?\s+les)\s+(?:lumieres|lampes)\b', q) \
            or re.search(r'\bquell(?:es?)?\s+(?:lumieres|lampes)\b', q):
        return make("hue.get_all_lights", {}, "rule: liste les lumieres", 0.91)

    for pattern, preset in _WHITE_PRESETS:
        if re.search(pattern, q):
            return make("hue.set_group_color_preset", {"group_id": _DEFAULT_GROUP, "preset": preset},
                        f"rule: lumiere {preset} -> preset du groupe", 0.90)
    return None


def detect(query: str):
    q = normalize(query)

    hit = _detect_beat_and_reads(q)
    if hit is not None:
        return hit

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

    # Luminosite sans lampe nommee = le groupe (lyra#24). Avant : hue.set_brightness sans
    # light_id (obligatoire, l'appel echouait) et une echelle 0-255 (Hue : 0-254).
    m_pct = re.search(r'luminosite?\s+a\s+(\d+)\s*(?:pour\s*cent|%)?', q) or \
        re.search(r'(?:lumieres?|lampes?)\s+a\s+(\d+)\s*(?:pour\s*cent|%)', q)
    if m_pct:
        brightness = _pct_to_bri(int(m_pct.group(1)))
        return make("hue.set_group_brightness", {"group_id": _DEFAULT_GROUP, "brightness": brightness},
                    f"rule: luminosite du groupe {brightness}", 0.92)

    if re.search(r'\b(?:lumieres?|lampes?|lumiere)\s+plus\s+(?:fort[esz]*|intens[aeés]*|haut[esz]*|viv[esz]*)', q) or \
            re.search(r'\b(?:monte|augmente|hausse|eleve)\b.*\bluminosite\b|\bluminosite\b.*\b(?:monte|augmente|hausse|eleve)\b', q):
        return make("hue.set_group_brightness", {"group_id": _DEFAULT_GROUP, "brightness": 200},
                    "rule: luminosite du groupe haute (relative)", 0.88)

    if re.search(r'\b(?:lumieres?|lampes?|lumiere)\s+plus\s+(?:doux|douce[sz]*|faible[sz]*|bas[esz]*)', q) or \
            re.search(r'\b(?:baisse|diminue|reduis|attenues?)\b.*\bluminosite\b|\bluminosite\b.*\b(?:baisse|diminue|reduis|attenues?)\b', q):
        return make("hue.set_group_brightness", {"group_id": _DEFAULT_GROUP, "brightness": 50},
                    "rule: luminosite du groupe basse (relative)", 0.88)

    # hue.set_group_color_rgb: "lumieres en rouge/bleu/..." (pluriel/ambiance =
    # tout le groupe). Arguments au format MCP complet (red/green/blue, PAS
    # r/g/b : set_color_rgb exigeait light_id et plantait en validation).
    m_rgb = re.search(r'\b(rouge|verte?|bleue?|violet(?:te)?|orange|jaune|rose|blanc(?:he)?|cyan)\b', q)
    if m_rgb and re.search(r'\b(?:lumieres?|lampes?|ambiance|atmosphere|couleur|mode)\b', q):
        rgb = _RGB_COLOR_MAP.get(m_rgb.group(1), (255, 255, 255))
        # Une lampe precise ("la lampe du bureau", "juste celle-la") n'est pas le
        # groupe (lyra#22) : set_color_rgb, et l'identifiant reste a demander.
        if re.search(r'\b(?:la|une|cette)\s+lampe\b|\bjuste\s+celle', q) and not re.search(r'\blampes\b', q):
            return make("hue.set_color_rgb",
                        {"red": rgb[0], "green": rgb[1], "blue": rgb[2]},
                        f"rule: set_color_rgb {m_rgb.group(1)} (lampe precise)", 0.88,
                        missing_args=["light_id"])
        return make("hue.set_group_color_rgb",
                    {"red": rgb[0], "green": rgb[1], "blue": rgb[2]},
                    f"rule: set_group_color_rgb {m_rgb.group(1)}", 0.90)

    return None
