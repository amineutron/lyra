"""Authentification git partagee pour cloner les repos prives GitHub.

Teste l'acces SSH (et alimente known_hosts au passage via accept-new) ; a
defaut, demande un Personal Access Token une seule fois par run et le
reutilise pour tous les repos prives suivants (jamais ecrit sur disque).
"""
from __future__ import annotations

import subprocess

from .events import Output
from .pipeline import StepContext

_pat_cache: dict[str, str] = {}


def ssh_github_ok() -> bool:
    try:
        out = subprocess.run(
            ["ssh", "-T", "-o", "StrictHostKeyChecking=accept-new",
             "-o", "ConnectTimeout=8", "git@github.com"],
            capture_output=True, text=True, timeout=20)
        # GitHub repond code 1 avec un message de bienvenue si la cle est bonne
        return "successfully authenticated" in (out.stderr + out.stdout)
    except Exception:
        return False


_PAT_HELP = (
    "Ce depot est prive : il faut un Personal Access Token GitHub.\n"
    "  1. https://github.com/settings/tokens -> Generate new token (classic)\n"
    "  2. Coche le scope 'repo' (acces complet aux depots prives)\n"
    "  3. Generate token, copie-le (affiche une seule fois)\n"
    "Jamais ecrit sur disque, reutilise pour tous les depots prives de ce run."
)


def resolve_repo_url(ctx: StepContext, repo_url: str) -> str:
    """URL a utiliser pour git clone : SSH telle quelle si accessible,
    sinon https+PAT saisi a la volee (une seule fois par run, jamais
    stocke sur disque, reutilise pour les autres repos prives).

    Un token laisse vide n'est jamais accepte silencieusement : ce depot
    ne fonctionnera pas sans, donc on redemande tant que l'utilisateur ne
    confirme pas explicitement vouloir continuer sans (auquel cas ce repo
    precis echoue -- gere en amont comme optionnel pour les MCP, fatal
    pour le clone du repo Lyra lui-meme)."""
    if not repo_url.startswith("git@"):
        return repo_url
    if ssh_github_ok():
        return repo_url
    if "token" not in _pat_cache:
        ctx.emit(Output("Cle SSH GitHub absente ou refusee."))
        ctx.emit(Output(_PAT_HELP))
        while True:
            token = ctx.broker.input(
                "Personal Access Token GitHub (vide pour annuler)", default="")
            if token:
                _pat_cache["token"] = token
                break
            if ctx.broker.confirm(
                    "Aucun token fourni : ce depot ne pourra pas etre "
                    "clone et cette fonctionnalite ne marchera pas tant "
                    "qu'il ne sera pas configure. Continuer sans ?", False):
                raise RuntimeError(
                    "acces au repo prive impossible (ni SSH ni PAT)")
    repo_name = repo_url.split(":", 1)[1]
    return f"https://{_pat_cache['token']}@github.com/{repo_name}"
