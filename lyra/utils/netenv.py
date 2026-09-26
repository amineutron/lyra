"""Proxy d'entreprise et services locaux (roadmap #44). Logique pure, testee.

httpx et requests suivent HTTP(S)_PROXY : sans NO_PROXY, un proxy
d'entreprise recevait aussi les appels a l'Ollama local (127.0.0.1:11434),
a l'API tracking (127.0.0.1:8765) et aux serveurs MCP locaux, qu'il ne peut
pas joindre. Au demarrage du client et du demon, on ajoute la boucle locale
a NO_PROXY -- uniquement si un proxy est defini, sans toucher au reste.
Les serveurs MCP lances par le demon heritent de cet environnement.
"""

from __future__ import annotations

import os
from typing import Mapping, MutableMapping

LOOPBACK = ("localhost", "127.0.0.1", "::1")
_PROXY = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY")


def a_un_proxy(environ: Mapping[str, str]) -> bool:
    return any(environ.get(v, "").strip() or environ.get(v.lower(), "").strip() for v in _PROXY)


def no_proxy_complete(environ: Mapping[str, str]) -> str | None:
    """Nouvelle valeur de NO_PROXY (boucle locale ajoutee), ou None s'il n'y a rien a changer."""
    if not a_un_proxy(environ):
        return None
    actuel = environ.get("NO_PROXY", "").strip() or environ.get("no_proxy", "").strip()
    items = [x.strip() for x in actuel.split(",") if x.strip()]
    manquants = [h for h in LOOPBACK if h not in items]
    if not manquants:
        return None
    return ",".join(items + manquants)


def proteger_services_locaux(environ: MutableMapping[str, str] | None = None) -> None:
    """Applique no_proxy_complete a l'environnement du processus (NO_PROXY et no_proxy)."""
    env = os.environ if environ is None else environ
    valeur = no_proxy_complete(env)
    if valeur is not None:
        env["NO_PROXY"] = valeur
        env["no_proxy"] = valeur
