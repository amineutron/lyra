#!/usr/bin/env python3
"""
MCP Server pour Denon AVR - Controle Home Cinema Denon.

Ce serveur expose les commandes Denon AVR via le protocole MCP pour
permettre a Lyra de controler le home cinema avec une latence minimale.

Protocole: Denon AVR Control Protocol via telnet (port 23)
Modele supporte: AVR-X1700H DAB (et autres AVR-X series)

Usage:
    python server.py

Configuration:
    Les parametres Denon sont lus depuis config.yaml ou variables d'env:
    - DENON_HOST: IP du Denon
    - DENON_PORT: Port telnet (default: 23)
"""

import asyncio
import json
import os
import sys
import socket
import time
from pathlib import Path
from typing import Any, Optional

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
except ImportError:
    print("Error: mcp package not installed. Run: pip install mcp", file=sys.stderr)
    sys.exit(1)


def load_config() -> dict:
    """Charge la configuration Denon depuis config.yaml ou variables d'env."""
    config = {
        "host": os.environ.get("DENON_HOST", ""),
        "port": int(os.environ.get("DENON_PORT", "23")),
    }

    # Essayer de charger depuis config.yaml de Lyra
    config_path = Path(__file__).parent.parent.parent / "config.yaml"
    if config_path.exists():
        try:
            import yaml
            with open(config_path) as f:
                cfg = yaml.safe_load(f)
            denon_cfg = cfg.get("denon", {})
            config["host"] = denon_cfg.get("host", config["host"])
            config["port"] = denon_cfg.get("port", config["port"])
        except Exception as e:
            print(f"Warning: Could not load config.yaml: {e}", file=sys.stderr)

    return config


class DenonAVRController:
    """Controleur pour Home Cinema Denon via telnet."""

    def __init__(self, host: str, port: int = 23):
        self.host = host
        self.port = port
        self.timeout = 3

    def _send_command(self, command: str) -> str:
        """Envoie une commande au Denon et retourne la reponse.

        Args:
            command: Commande Denon (ex: "MV44", "PWON", "MV?")

        Returns:
            Reponse brute du Denon
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)

        try:
            sock.connect((self.host, self.port))

            # Envoyer commande
            sock.send(f"{command}\r".encode('ascii'))
            time.sleep(0.3)

            # Lire reponse
            response = sock.recv(1024).decode('ascii', errors='ignore')
            sock.close()

            return response.strip()
        except socket.timeout:
            return "ERROR: Timeout - Denon may be off"
        except Exception as e:
            return f"ERROR: {str(e)}"

    def get_volume(self) -> dict:
        """Retourne le volume actuel."""
        response = self._send_command("MV?")

        if "ERROR" in response:
            return {"error": response}

        # Parser MV245 -> 24.5, MV44 -> 44
        for line in response.split('\r'):
            if line.startswith('MV') and not line.startswith('MVMAX'):
                vol_str = line[2:]  # Enlever "MV"
                if len(vol_str) == 3:  # Ex: "245" -> 24.5
                    volume = float(vol_str) / 10
                elif len(vol_str) == 2:  # Ex: "44" -> 44
                    volume = int(vol_str)
                else:
                    volume = int(vol_str) if vol_str.isdigit() else -1

                return {"current": volume, "min": 0, "max": 98}

        return {"error": "Could not parse volume"}

    def volume_set(self, level: int) -> str:
        """Regle le volume a un niveau specifique (0-98).

        Args:
            level: Niveau de volume (0-98, ou 80 = 0dB reference)

        Returns:
            Message de confirmation
        """
        level = max(0, min(98, level))

        # Format Denon: MV44 pour 44, MV445 pour 44.5
        # On utilise des entiers seulement
        response = self._send_command(f"MV{level:02d}")

        if "ERROR" in response:
            return f"Erreur: {response}"

        # Verifier que ca a marche
        time.sleep(0.2)
        check = self.get_volume()
        if "error" not in check:
            actual = check["current"]
            if abs(actual - level) < 0.6:  # Tolerance 0.5
                return f"Volume regle a {level}"
            else:
                return f"Volume partiellement regle (demande: {level}, actuel: {actual})"

        return f"Volume regle a {level}"

    def volume_up(self, step: int = 1) -> str:
        """Augmente le volume.

        Args:
            step: Nombre de fois a augmenter (default: 1)

        Returns:
            Message avec nouveau volume
        """
        for _ in range(step):
            self._send_command("MVUP")
            time.sleep(0.1)

        time.sleep(0.2)
        vol = self.get_volume()
        if "error" not in vol:
            return f"Volume: {vol['current']}"
        return "Volume augmente"

    def volume_down(self, step: int = 1) -> str:
        """Baisse le volume.

        Args:
            step: Nombre de fois a baisser (default: 1)

        Returns:
            Message avec nouveau volume
        """
        for _ in range(step):
            self._send_command("MVDOWN")
            time.sleep(0.1)

        time.sleep(0.2)
        vol = self.get_volume()
        if "error" not in vol:
            return f"Volume: {vol['current']}"
        return "Volume baisse"

    def mute_on(self) -> str:
        """Active le mute."""
        response = self._send_command("MUON")
        if "ERROR" not in response:
            return "Mute active"
        return f"Erreur: {response}"

    def mute_off(self) -> str:
        """Desactive le mute."""
        response = self._send_command("MUOFF")
        if "ERROR" not in response:
            return "Mute desactive"
        return f"Erreur: {response}"

    def mute_toggle(self) -> str:
        """Toggle le mute (lit l'etat courant, puis inverse)."""
        status = self._send_command("MU?")
        if "ERROR" in status:
            return f"Erreur lecture etat mute: {status}"
        if "MUON" in status:
            return self.mute_off()
        return self.mute_on()

    def power_on(self) -> str:
        """Allume le Denon."""
        response = self._send_command("PWON")
        if "ERROR" not in response:
            return "Denon allume"
        return f"Erreur: {response}"

    def power_off(self) -> str:
        """Eteint le Denon (standby)."""
        response = self._send_command("PWSTANDBY")
        if "ERROR" not in response:
            return "Denon en standby"
        return f"Erreur: {response}"

    def get_status(self) -> dict:
        """Retourne le statut complet du Denon."""
        vol = self.get_volume()
        power = self._send_command("PW?")

        status = {
            "volume": vol.get("current", -1),
            "power": "on" if "PWON" in power else "standby",
        }

        return status

    def set_input(self, source: str) -> str:
        """Change la source d'entree.

        Args:
            source: Source (ex: "BD", "TV", "GAME", "SAT/CBL", "DVD", "MPLAY")

        Returns:
            Message de confirmation
        """
        # Normaliser la source
        source_map = {
            "bluray": "BD",
            "blu-ray": "BD",
            "bd": "BD",
            "tv": "TV",
            "game": "GAME",
            "sat": "SAT/CBL",
            "cable": "SAT/CBL",
            "dvd": "DVD",
            "media": "MPLAY",
            "mediaplayer": "MPLAY",
        }

        source_cmd = source_map.get(source.lower())
        if source_cmd is None:
            valid = ", ".join(sorted(source_map.keys()))
            return f"Source inconnue: {source!r}. Sources valides: {valid}"

        response = self._send_command(f"SI{source_cmd}")
        if "ERROR" not in response:
            return f"Source changee: {source_cmd}"
        return f"Erreur: {response}"


# Initialiser le serveur MCP
app = Server("denon-mcp")
config = load_config()

if not config["host"]:
    print("Error: DENON_HOST not configured", file=sys.stderr)
    sys.exit(1)

denon = DenonAVRController(config["host"], config["port"])


@app.list_tools()
async def list_tools() -> list[Tool]:
    """Liste les outils disponibles."""
    return [
        Tool(
            name="volume_set",
            description="Regle le volume du Denon a un niveau specifique (0-98). 80 = 0dB reference.",
            inputSchema={
                "type": "object",
                "properties": {
                    "level": {
                        "type": "integer",
                        "description": "Niveau de volume (0-98)",
                        "minimum": 0,
                        "maximum": 98,
                    }
                },
                "required": ["level"],
            },
        ),
        Tool(
            name="volume_up",
            description="Augmente le volume du Denon.",
            inputSchema={
                "type": "object",
                "properties": {
                    "step": {
                        "type": "integer",
                        "description": "Nombre de fois a augmenter (default: 1)",
                        "minimum": 1,
                        "maximum": 10,
                        "default": 1,
                    }
                },
            },
        ),
        Tool(
            name="volume_down",
            description="Baisse le volume du Denon.",
            inputSchema={
                "type": "object",
                "properties": {
                    "step": {
                        "type": "integer",
                        "description": "Nombre de fois a baisser (default: 1)",
                        "minimum": 1,
                        "maximum": 10,
                        "default": 1,
                    }
                },
            },
        ),
        Tool(
            name="mute_on",
            description="Active le mute du Denon.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="mute_off",
            description="Desactive le mute du Denon.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="mute_toggle",
            description="Toggle le mute du Denon (on/off).",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="power_on",
            description="Allume le Denon AVR.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="power_off",
            description="Eteint le Denon AVR (standby).",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="get_status",
            description="Retourne le statut du Denon (volume, power, etc.).",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="set_input",
            description="Change la source d'entree du Denon (BD, TV, GAME, SAT/CBL, DVD, MPLAY).",
            inputSchema={
                "type": "object",
                "properties": {
                    "source": {
                        "type": "string",
                        "description": "Source (ex: BD, TV, GAME, SAT/CBL, DVD, MPLAY)",
                    }
                },
                "required": ["source"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Execute un outil."""
    try:
        if name == "volume_set":
            level = arguments.get("level")
            result = denon.volume_set(level)
        elif name == "volume_up":
            step = arguments.get("step", 1)
            result = denon.volume_up(step)
        elif name == "volume_down":
            step = arguments.get("step", 1)
            result = denon.volume_down(step)
        elif name == "mute_on":
            result = denon.mute_on()
        elif name == "mute_off":
            result = denon.mute_off()
        elif name == "mute_toggle":
            result = denon.mute_toggle()
        elif name == "power_on":
            result = denon.power_on()
        elif name == "power_off":
            result = denon.power_off()
        elif name == "get_status":
            result = json.dumps(denon.get_status(), indent=2)
        elif name == "set_input":
            source = arguments.get("source")
            result = denon.set_input(source)
        else:
            result = f"Unknown tool: {name}"

        return [TextContent(type="text", text=result)]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def main():
    """Point d'entree principal."""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
