"""Regles de detection pour les outils SCREEN-MANAGER (gestion multi-ecrans)."""

import re

from .base import normalize, make

# Verbes d'affichage/ouverture - large spectre naturel
_DISPLAY_VERBS = (
    r'\b(?:ouvr[ei]r?|lanc[ei]r?|affich[ei]r?|montr[ei]r?|mets?|met(?:tre)?|'
    r'envoie?r?|projette?r?|deplace[rz]?|bascule[rz]?|pouss[ei]r?|'
    r'demarre[rz]?|demarr[ei]r?)\b'
)

# Mots-cles destination ecran - large spectre naturel
# La valeur brute est passee au MCP qui gere les formulations naturelles
_SCREEN_KW = (
    r'\b(?:ecran|moniteur|display|affichage|tele(?:vision)?|tv|'
    r'grand\s+ecran|deuxieme|2e|2eme|troisieme|3e|3eme|'
    r'premier|1er|gauche|droite|milieu|principal|secondaire|'
    r'hdmi|bureau|second)\b'
)

# URLs valides
_URL_RE = r'https?://\S+|localhost(?::\d+)?(?:/\S*)?|\w+\.\w{2,}(?:/\S*)?'

# Prepositions de destination
_ON_SCREEN = r'\bsur\b|\bvers\b|\ba\s+(?:l[ae]?\s+)?(?:' + _SCREEN_KW[3:]  # retire le \b debut


def detect(query: str):
    q = normalize(query)

    # ------------------------------------------------------------------ #
    # list_screens: "quels sont mes ecrans", "liste les moniteurs"         #
    # ------------------------------------------------------------------ #
    if re.search(r'\b(?:liste[rz]?|liste|quels?|quelles?|combien|montre[rz]?|affiche[rz]?|donne[rz]?)\b', q) and \
            re.search(r'\b(?:ecrans?|moniteurs?|displays?|affichages?)\b', q) and \
            not re.search(r'\bsur\b', q):
        return make("screen-manager.list_screens", {}, "rule: list_screens", 0.93)

    # ------------------------------------------------------------------ #
    # list_apps: "liste les applications", "quelles apps sont dispo"       #
    # ------------------------------------------------------------------ #
    if re.search(r'\b(?:liste[rz]?|quels?|quelles?|montre[rz]?|affiche[rz]?|donne[rz]?|disponibles?)\b', q) and \
            re.search(r'\b(?:appli(?:cation)?s?|apps?|programmes?|logiciels?)\b', q) and \
            not re.search(_SCREEN_KW, q):
        m_filter = re.search(r'\b(?:filtr[ei]r?\s+(?:par\s+)?|avec\s+)(\w+)', q)
        args = {"filter": m_filter.group(1)} if m_filter else {}
        return make("screen-manager.list_apps", args, "rule: list_apps", 0.92)

    # ------------------------------------------------------------------ #
    # setup_screens: "configure/detecte les ecrans"                        #
    # ------------------------------------------------------------------ #
    if re.search(r'\b(?:configur[ei]r?|configure[rz]?|setup|detecte[rz]?|initialise[rz]?|parametr[ei]r?)\b', q) and \
            re.search(r'\b(?:ecrans?|moniteurs?|displays?|affichages?)\b', q):
        return make("screen-manager.setup_screens", {}, "rule: setup_screens", 0.92)

    # ------------------------------------------------------------------ #
    # update_screen_config: "renomme l'ecran 2 en bureau"                  #
    # ------------------------------------------------------------------ #
    m_rename = re.search(
        r"\b(?:renomm[ei]r?|change[rz]?\s+(?:l[ae]?'?\s*)?(?:nom|alias)|"
        r'appelle[rz]?|nomme[rz]?)\b.*?(?:ecran|moniteur)\s*(?:numero\s*)?(\d+)',
        q
    )
    if m_rename:
        idx = int(m_rename.group(1))
        m_alias = re.search(r'\b(?:en|par|comme)\s+(\w+)', q)
        args = {"screen_index": idx}
        if m_alias:
            args["alias"] = m_alias.group(1)
        return make("screen-manager.update_screen_config", args,
                    f"rule: update_screen_config ecran {idx}", 0.91)

    # ------------------------------------------------------------------ #
    # open_url: verbe + URL + destination optionnelle                      #
    # ------------------------------------------------------------------ #
    m_url = re.search(_URL_RE, query)  # query non-normalisee pour garder casse URL
    if m_url and re.search(_DISPLAY_VERBS, q):
        url = m_url.group(0)
        screen = _extract_screen_dest(q)
        args = {"url": url}
        if screen:
            args["screen"] = screen
        return make("screen-manager.open_url", args,
                    f"rule: open_url {url[:40]}", 0.94)

    # ------------------------------------------------------------------ #
    # open_app: verbe + app + destination ecran                            #
    # Cas central - le plus large                                          #
    # ------------------------------------------------------------------ #
    if re.search(_DISPLAY_VERBS, q) and re.search(_SCREEN_KW, q):
        app_name = _extract_app_name(q)
        screen = _extract_screen_dest(q)
        args = {}
        if app_name:
            args["app_name"] = app_name
        if screen:
            args["screen"] = screen
        if app_name or screen:
            return make("screen-manager.open_app", args,
                        f"rule: open_app app={app_name} screen={screen}", 0.92)

    # ------------------------------------------------------------------ #
    # open_app sans ecran: verbe + app, pas de mot-cle ecran              #
    # -> demander l'ecran a l'utilisateur (missing_args)                   #
    # ------------------------------------------------------------------ #
    if re.search(_DISPLAY_VERBS, q):
        app_name = _extract_app_name_bare(q)
        if app_name:
            return make("screen-manager.open_app", {"app_name": app_name},
                        f"rule: open_app sans ecran app={app_name}", 0.88,
                        missing_args=["screen"])

    return None


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

def _extract_screen_dest(q: str) -> str | None:
    """Extrait la destination ecran (tout apres 'sur/vers/a l[ae]? <screen_kw>')."""
    # Capturer "sur l'ecran de droite", "sur la tele", "sur le 3e moniteur", etc.
    m = re.search(
        r"\bsur\s+(?:l[ae]?['\s]\s*|le\s+|la\s+|les?\s+|mon\s+|mes?\s+)?"
        r'((?:grand\s+)?(?:ecran|moniteur|display|affichage|tele(?:vision)?|tv|bureau)'
        r'(?:\s+(?:de\s+)?(?:gauche|droite|milieu|principal|secondaire|\d+|'
        r'premier|deuxieme|troisieme|1er|2e|2eme|3e|3eme))?'
        r'(?:\s+(?:de\s+)?(?:gauche|droite|milieu))?)',
        q
    )
    if m:
        return m.group(1).strip()
    # Formulation avec numero seul: "sur le 2", "sur l'ecran 3"
    m2 = re.search(r'\bsur\s+(?:l[ae]?\s+)?(?:ecran|moniteur)?\s*(?:numero\s*)?(\d+)\b', q)
    if m2:
        return m2.group(1)
    return None


def _extract_app_name_bare(q: str) -> str | None:
    """Extrait le nom de l'app apres un verbe, sans 'sur' (pas d'ecran specifie)."""
    _LEADING_ARTICLES = {'le', 'la', 'les', 'l', 'un', 'une', 'des', 'mon', 'ma',
                         'mes', 'ce', 'cet', 'cette', 'moi', 'lui', 'app', 'application',
                         'stp', 'please', 'moi', 'nous'}
    m = re.search(
        r'(?:ouvr[ei]r?|lanc[ei]r?|affich[ei]r?|montr[ei]r?|mets?|'
        r'envoie?r?|projette?r?|deplace[rz]?|bascule[rz]?)\s+'
        r'([\w\-\.]+(?:\s+[\w\-\.]+)?)\s*$',
        q
    )
    if m:
        candidate = m.group(1).strip()
        parts = candidate.split(None, 1)
        if len(parts) == 2 and parts[0].lower() in _LEADING_ARTICLES:
            candidate = parts[1]
        if candidate.lower() not in _LEADING_ARTICLES:
            return candidate
    return None


def _extract_app_name(q: str) -> str | None:
    """Extrait le nom de l'app entre le verbe et le mot-cle ecran/sur."""
    # Pattern: verbe <app_name> sur ...
    m = re.search(
        r'(?:ouvr[ei]r?|lanc[ei]r?|affich[ei]r?|montr[ei]r?|mets?|'
        r'envoie?r?|projette?r?|deplace[rz]?|bascule[rz]?)\s+'
        r'([\w\-\.]+(?:\s+[\w\-\.]+)?)'
        r'\s+(?:sur|vers)\b',
        q
    )
    _LEADING_ARTICLES = {'le', 'la', 'les', 'l', 'un', 'une', 'des', 'mon', 'ma',
                         'mes', 'ce', 'cet', 'cette', 'moi', 'lui', 'app', 'application'}
    if m:
        candidate = m.group(1).strip()
        # Supprimer un article en tete ("le worldmonitor" -> "worldmonitor")
        parts = candidate.split(None, 1)
        if len(parts) == 2 and parts[0].lower() in _LEADING_ARTICLES:
            candidate = parts[1]
        # Ignorer si le candidat restant est lui-meme un article
        if candidate.lower() not in _LEADING_ARTICLES:
            return candidate
    return None
