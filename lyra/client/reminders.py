"""Rappels affiches au demarrage du client (REPL et one-shot).

incomplete_integrations est ecrit dans config.yaml par installer/core/
steps/config.py quand un MCP selectionne a l'install est reste incomplet
(device injoignable, paquet casse...) -- voir installer/core/pipeline.py
StepDef.optional. Non bloquant pour Lyra, mais l'utilisateur doit savoir
que cette partie ne fonctionnera pas tant que non reconfiguree.
"""
from __future__ import annotations

from modules import ui


def print_incomplete_integrations(cfg: dict) -> None:
    incomplete = cfg.get("incomplete_integrations") or []
    if not incomplete:
        return
    print(f"{ui.Colors.YELLOW}[!] Integrations incompletes :{ui.Colors.RESET}")
    for item in incomplete:
        label = item.get("label", item.get("id", "?"))
        reason = item.get("reason", "raison inconnue")
        print(f"{ui.Colors.YELLOW}    - {label} : {reason}{ui.Colors.RESET}")
    print(f"{ui.Colors.YELLOW}    Cette partie ne fonctionnera pas tant que "
          f"non configuree. Relance ./installer/install.sh pour la "
          f"reconfigurer, ou complete config.yaml/secrets.yaml a la "
          f"main.{ui.Colors.RESET}")
