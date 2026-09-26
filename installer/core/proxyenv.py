"""Proxy et miroirs d'entreprise pour l'installeur (roadmap #44). Logique pure, testee.

Les outils appeles (pip, curl, huggingface_hub, dnf, apt) lisent deja
HTTP(S)_PROXY / NO_PROXY / PIP_INDEX_URL / HF_ENDPOINT dans l'environnement.
Deux endroits les perdaient pourtant :

- `sudo` reinitialise l'environnement (env_reset) : `sudo dnf install` ou
  `sudo apt-get install` partait sans proxy et echouait derriere un proxy
  d'entreprise. `with_preserved_env` ajoute `--preserve-env=<liste>`.
- le service systemd `ollama` n'herite pas du shell : `ollama pull` passe par
  lui et ne voyait pas le proxy. `ollama_proxy_dropin` produit le drop-in
  `[Service] Environment=...` documente par Ollama.
"""
from __future__ import annotations

from typing import Mapping
from urllib.parse import urlsplit, urlunsplit

PROXY_VARS: tuple[str, ...] = (
    "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "ALL_PROXY",
    "http_proxy", "https_proxy", "no_proxy", "all_proxy",
)
MIRROR_VARS: tuple[str, ...] = (
    "PIP_INDEX_URL", "PIP_EXTRA_INDEX_URL", "PIP_TRUSTED_HOST", "HF_ENDPOINT",
)
# Le service Ollama ne lit que ces trois-la (pas les miroirs pip/HF).
_OLLAMA_VARS = ("HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY")
LOOPBACK = ("localhost", "127.0.0.1", "::1")


def network_env(environ: Mapping[str, str]) -> dict[str, str]:
    """Variables proxy/miroir definies (non vides), dans un ordre stable."""
    return {k: environ[k] for k in PROXY_VARS + MIRROR_VARS if environ.get(k, "").strip()}


def has_proxy(environ: Mapping[str, str]) -> bool:
    return any(environ.get(k, "").strip() for k in PROXY_VARS if "no_proxy" not in k.lower())


def with_preserved_env(cmd: list[str], environ: Mapping[str, str]) -> list[str]:
    """`sudo ...` -> `sudo --preserve-env=VARS ...` si des variables reseau sont definies.

    Toute autre commande (ou aucun proxy) est rendue telle quelle."""
    if not cmd or cmd[0] != "sudo":
        return list(cmd)
    names = list(network_env(environ))
    if not names or any(a.startswith("--preserve-env") or a == "-E" for a in cmd[1:]):
        return list(cmd)
    return ["sudo", f"--preserve-env={','.join(names)}", *cmd[1:]]


def _get(environ: Mapping[str, str], name: str) -> str:
    return environ.get(name, "").strip() or environ.get(name.lower(), "").strip()


def no_proxy_with_loopback(value: str) -> str:
    """NO_PROXY complete par la boucle locale (sans doublon, ordre conserve)."""
    items = [x.strip() for x in value.split(",") if x.strip()]
    return ",".join(items + [h for h in LOOPBACK if h not in items])


def ollama_proxy_dropin(environ: Mapping[str, str]) -> str | None:
    """Contenu de /etc/systemd/system/ollama.service.d/proxy.conf, None sans proxy.

    NO_PROXY inclut toujours la boucle locale : les clients qui parlent au
    service sur 127.0.0.1 ne doivent pas etre renvoyes vers le proxy."""
    if not has_proxy(environ):
        return None
    lines = ["[Service]"]
    for name in _OLLAMA_VARS:
        value = _get(environ, name)
        if name == "NO_PROXY":
            value = no_proxy_with_loopback(value)
        if value:
            lines.append(f'Environment="{name}={value}"')
    return "\n".join(lines) + "\n"


def proxy_display(environ: Mapping[str, str]) -> str:
    """Proxy en usage, mot de passe masque, pour les messages de l'installeur."""
    return redact(_get(environ, "HTTPS_PROXY") or _get(environ, "HTTP_PROXY") or _get(environ, "ALL_PROXY"))


def redact(url: str) -> str:
    """Masque le mot de passe d'une URL de proxy avant de l'afficher."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    if not parts.password:
        return url
    host = parts.hostname or ""
    netloc = f"{parts.username}:***@{host}" + (f":{parts.port}" if parts.port else "")
    return urlunsplit(parts._replace(netloc=netloc))
