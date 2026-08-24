"""Configuration des devices : boucle generique sur McpDef.fields.

Remplace le _phase_config_devices de install-lyra-interactive.py (un bloc
if/elif par MCP) : ici tout vient du catalogue — un popup par MCP
selectionne ayant des champs, un Prompt.ask par champ (password si secret).
"""
from __future__ import annotations

import time
from typing import Sequence

from rich.console import Console
from rich.prompt import Prompt

from installer.core.catalog import FieldDef, McpDef

from .popup import popup_header
from .theme import DIM, GOLD


def demo_device_config(selected: Sequence[McpDef]) -> dict[str, dict[str, str]]:
    """Valeurs factices 10.0.0.X pour le mode demo (aucun prompt)."""
    config: dict[str, dict[str, str]] = {}
    counter = 2
    for mcp in selected:
        if not mcp.fields:
            continue
        values: dict[str, str] = {}
        for field in mcp.fields:
            if field.default:
                values[field.key] = field.default
            else:
                values[field.key] = f"10.0.0.{counter}"
                counter += 1
        config[mcp.id] = values
    return config


def _ask_field(console: Console, mcp: McpDef, field: FieldDef) -> str:
    if field.help:
        console.print(f"  [{DIM}]{field.help}[/]")
    suffix = " (optionnel)" if field.optional else ""
    value = str(Prompt.ask(
        f"  [bold {mcp.color}]{field.label}{suffix}[/]",
        password=field.secret, console=console,
        default=field.default or ""))
    if not value.strip():
        console.print(f"  [{DIM}]-> laisse vide : a renseigner plus tard "
                      f"({'secrets.yaml' if field.secret else 'config.yaml'})[/]")
    console.print()
    return value


def collect_device_config(console: Console, selected: Sequence[McpDef],
                          demo: bool = False) -> dict[str, dict[str, str]]:
    """Popup 'CONFIGURATION <NAME>' par MCP ; retourne {mcp_id: {key: val}}."""
    if demo:
        config = demo_device_config(selected)
        console.clear()
        popup_header(console, "CONFIGURATION DES DEVICES", GOLD)
        console.print("  [dim yellow][DEMO] Configuration par defaut "
                      "appliquee.[/dim yellow]")
        console.print()
        for mcp_id, values in config.items():
            summary = "  ".join(f"{k}={v}" for k, v in values.items())
            console.print(f"  [{DIM}]--[/] [bold]{mcp_id:<12}[/]  "
                          f"[{DIM}]{summary}[/]")
        time.sleep(1.2)
        return config

    config: dict[str, dict[str, str]] = {}
    for mcp in selected:
        if not mcp.fields:
            continue
        console.clear()
        popup_header(console, f"CONFIGURATION {mcp.name.upper()}", mcp.color)
        console.print(f"  [{DIM}]Entree sans valeur = configurer plus tard. "
                      f"Tout reste modifiable apres l'installation :[/]")
        console.print(f"  [{DIM}]~/lyra/config.yaml (adresses, devices) · "
                      f"~/lyra/secrets.yaml (credentials)[/]")
        console.print()
        values: dict[str, str] = {}
        for field in mcp.fields:
            values[field.key] = _ask_field(console, mcp, field)
        config[mcp.id] = values
        time.sleep(0.4)
    return config
