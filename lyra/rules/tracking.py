"""Regles de detection pour les outils TRACKING."""

import re
from typing import Optional

from .base import normalize, make


def detect(query: str):
    q = normalize(query)

    # kill_task : detectable meme sans mot-cle "track*"
    # "kill/stop/annule/arrete [la] [tache] ID_OU_NOM"
    # "stop tache X" uniquement (pour ne pas capturer "stop preprod-09")
    m = re.search(
        r'(?:kill|annule[rz]?|arr[eê]te[rz]?|cancel|tue[rz]?)\s+'
        r'(?:la\s+)?(?:tache\s+|task\s+)?([a-z0-9][a-z0-9_-]{3,})'
        r'|stop\s+(?:la\s+)?(?:tache|task)\s+([a-z0-9][a-z0-9_-]{3,})', q
    )
    if m:
        identifier = m.group(1) or m.group(2)
        return make("tracking.kill_task", {"identifier": identifier},
                    f"rule: kill tache '{identifier}'", 0.93)

    _has_track_kw = bool(re.search(r'\btrack(?:ing|er)?\b|\bdashboard\b|\bsuivi\b', q))
    _has_track_ctx = bool(re.search(
        r'affiche|ouvre|montre|lance|liste|statut|info\b|etat|avancement|progression'
        r'|supprim|retir|efface|taches?|erreurs?|errors?|session|suivi|quoi\s+en\s+cours'
        r'|qu(?:e|\')\s+est.ce|quoi\s+tourne', q
    ))

    if _has_track_kw and _has_track_ctx:
        # delete : "supprime/retire/efface [la tache] ID"
        m = re.search(r'(?:supprim[ea]?[rz]?|retir[ea]?[rz]?|efface[rz]?)\s+'
                      r'(?:la\s+)?(?:tache\s+)?([a-z0-9]{6,})', q)
        if m:
            return make("tracking.delete", {"session_id": m.group(1)},
                        "rule: supprime tache ID", 0.90)

        # get : "statut/info/etat/avancement/progression [de la tache] ID"
        m = re.search(r'(?:statut|info|etat|avancement|progression)\s+'
                      r'(?:de\s+)?(?:la\s+)?(?:tache\s+)?([a-z0-9]{6,})', q)
        if m:
            return make("tracking.get", {"session_id": m.group(1)},
                        "rule: statut tache ID", 0.91)

        # list : taches en cours / liste / quoi tourne
        if re.search(r'(?:taches?|operations?)\s+(?:en\s+cours|actives?|lancees?)'
                     r'|liste\s+(?:(?:les?|mes|des)\s+)?taches?'
                     r'|qu(?:e|\')\s+est.ce\s+(?:que\s+)?tu\s+suis'
                     r'|quoi\s+(?:en\s+cours|tourne)', q):
            return make("tracking.list",
                        {"template": "lyra_task", "status": "running"},
                        "rule: liste taches en cours", 0.92)

        # open_ui : tout le reste (affiche, ouvre, montre, etc.)
        filter_template = None
        if re.search(r'\berreurs?\b|\berrors?\b', q):
            filter_template = "errors"
        elif re.search(r'\blyra\b', q):
            filter_template = "lyra_task"
        args: dict = {}
        if filter_template:
            args["filter_template"] = filter_template
        return make("tracking.open_ui", args, "rule: ouvre le dashboard tracking", 0.95)

    # tracking_list sans mot-cle "track*" : "quoi en cours", "liste mes taches", etc.
    if re.search(r'quoi\s+(?:en\s+cours|tourne)'
                 r'|qu(?:e|\')\s+est.ce\s+(?:que\s+)?tu\s+suis'
                 r'|liste\s+(?:(?:les?|mes|des)\s+)?taches?'
                 r'|taches?\s+(?:en\s+cours|actives?|lancees?)', q):
        return make("tracking.list",
                    {"template": "lyra_task", "status": "running"},
                    "rule: liste taches en cours (sans mot-cle track)", 0.88)

    return None
