#!/usr/bin/env python3
"""Genere docs/user/MCP_TOOLS.md depuis les serveurs MCP reellement configures.

    .venv/bin/python scripts/gen_mcp_tools_md.py [--config config.yaml] [--sortie docs/user/MCP_TOOLS.md]

Interroge chaque serveur de la section mcp.servers (list_tools) et ecrit, par
serveur, un tableau outil | description | arguments | confirmation. La colonne
confirmation vient de lyra/core/constants.py (DANGEREUX / DESTRUCTIF /
PERFORMANCE) : la doc ne peut plus diverger des listes du code.
Audit 2026-09-19 : la version manuelle listait 15 outils inexistants et en
oubliait 30.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import yaml  # noqa: E402

from lyra.core.constants import (  # noqa: E402
    is_dangerous_tool,
    is_destructive_tool,
    is_performance_tool,
)

TITRES = {
    "fedora": "FEDORA - VM KVM et sauvegardes (fedora-agents)",
    "tv": "TV - Philips Android TV (pylips-mcp)",
    "hue": "HUE - Lumieres Philips Hue (hue-mcp)",
    "denon": "DENON - Home cinema Denon AVR (denon-mcp)",
    "catt": "CATT - Chromecast et cast navigateur (catt-mcp)",
}


def confirmation(nom: str) -> str:
    if is_destructive_tool(nom):
        return "DESTRUCTIF : oui explicite, jamais auto-confirme"
    if is_dangerous_tool(nom):
        return "SENSIBLE : oui explicite, jamais auto-confirme"
    if is_performance_tool(nom):
        return "sans confirmation en mode performance (-p)"
    return "confirmation [O/n]"


def arguments(schema: dict) -> str:
    props = (schema or {}).get("properties") or {}
    requis = set((schema or {}).get("required") or [])
    if not props:
        return "-"
    morceaux = []
    for nom, spec in props.items():
        typ = spec.get("type") or ("/".join(spec["enum"]) if spec.get("enum") else "any")
        if spec.get("enum") and spec.get("type"):
            typ = f"{typ}: {'/'.join(str(e) for e in spec['enum'])}"
        morceaux.append(f"`{nom}` ({typ}{'' if nom in requis else ', opt'})")
    return ", ".join(morceaux)


def description_courte(texte: str, maximum: int = 110) -> str:
    texte = " ".join((texte or "").split())
    texte = texte.replace("|", "/")
    return texte if len(texte) <= maximum else texte[:maximum].rsplit(" ", 1)[0] + "..."


def rendre(outils: list[dict]) -> str:
    par_serveur: dict[str, list[dict]] = {}
    for o in outils:
        par_serveur.setdefault(o["_server"], []).append(o)
    total = len(outils)
    lignes = [
        "# Lyra - Liste des outils MCP",
        "",
        f"Genere le {date.today().isoformat()} par `scripts/gen_mcp_tools_md.py` depuis les serveurs "
        f"configures ({total} outils, {len(par_serveur)} serveurs). Ne pas editer a la main : relancer le script.",
        "",
        "Colonne confirmation (source : `lyra/core/constants.py`) :",
        "",
        "- **DESTRUCTIF** : perte ou ecrasement irreversible ; banniere rouge, `o`/`oui` obligatoire, jamais auto-confirme (`-y`, `-p`).",
        "- **SENSIBLE** : ecrit, execute une commande ou coupe une machine ; `o`/`oui` obligatoire, jamais auto-confirme.",
        "- **sans confirmation en mode performance** : domotique reversible ; en mode par defaut, confirmation `[O/n]`.",
        "- **confirmation [O/n]** : Entree vaut oui.",
        "",
    ]
    for serveur in sorted(par_serveur, key=lambda s: list(TITRES).index(s) if s in TITRES else 99):
        liste = sorted(par_serveur[serveur], key=lambda o: o["name"])
        lignes += [f"## {TITRES.get(serveur, serveur.upper())} ({len(liste)} outils)", "",
                   "| Outil | Description | Arguments | Confirmation |", "|---|---|---|---|"]
        for o in liste:
            lignes.append(f"| `{o['name']}` | {description_courte(o.get('description'))} | "
                          f"{arguments(o.get('parameters'))} | {confirmation(o['name'])} |")
        lignes.append("")
    lignes += [
        "## Hors MCP",
        "",
        "- `tracking.*` et `ironman.run_scene` sont interceptes par HESTIA avant tout serveur (lyra/hestia/executor.py).",
        "- `mermaid-mcp` (mcp-servers/) n'est pas branche dans config.yaml : ses outils ne sont pas appelables par Lyra.",
        "",
    ]
    return "\n".join(lignes)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(REPO / "config.yaml"))
    parser.add_argument("--sortie", default=str(REPO / "docs" / "user" / "MCP_TOOLS.md"))
    args = parser.parse_args()
    from modules.mcp import MCPManager
    config = yaml.safe_load(Path(args.config).read_text()) or {}
    manager = MCPManager(config, verbose=False)
    outils = manager.get_all_tools()
    if not outils:
        print("Aucun outil remonte : serveurs injoignables ?", file=sys.stderr)
        return 1
    Path(args.sortie).write_text(rendre(outils))
    print(f"{len(outils)} outils -> {args.sortie}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
