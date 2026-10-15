"""Test de fumee du demon Lyra : le service en cours repond-il comme attendu ?

Se connecte au socket du demon et verifie, sans rien executer :
  hello -> ready, ping -> pong, health -> health,
  analyze -> analysis (une phrase connue des regles est resolue),
  tool en mode unattended sur un outil hors PERFORMANCE_TOOLS -> refuse.

Aucun appareil n'est touche : l'analyse n'execute rien et l'appel d'outil
choisi est justement celui que le demon doit refuser.

Usage : python scripts/smoke_daemon.py [--socket CHEMIN]   (exit 0 = tout est bon)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lyra.daemon.protocol import SOCKET_PATH, ChannelClosed, connect  # noqa: E402

TIMEOUT = 10.0
MAX_REPLIES = 20
KNOWN_PHRASE = "allume la télé"
KNOWN_TOOL = "tv.power_on"
# Outil reel, en LECTURE SEULE et hors PERFORMANCE_TOOLS : le mode sans humain doit le refuser
# sans l'executer. Lecture seule expres : un demon trop ancien pour connaitre `unattended`
# l'executerait, et le test doit alors echouer sans avoir rien change.
REFUSED_TOOL = "fedora.vm_status"
REFUSAL_TEXT = "sans presence humaine"


def check_ready(m: dict) -> str:
    return "" if m.get("type") == "ready" and m.get("status") == "ready" else f"etat du demon : {m.get('status', m.get('type'))}"


def check_pong(m: dict) -> str:
    return "" if m.get("type") == "pong" else f"reponse inattendue : {m.get('type')}"


def check_health(m: dict) -> str:
    return "" if m.get("type") == "health" and isinstance(m.get("data"), dict) else f"reponse inattendue : {m.get('type')}"


def check_analysis(m: dict) -> str:
    if m.get("type") != "analysis":
        return f"message analyze non reconnu (demon a redemarrer ?) : {m.get('type')} {m.get('text', '')}".strip()
    if not m.get("found") or m.get("tool") != KNOWN_TOOL:
        return f"« {KNOWN_PHRASE} » resolu en {m.get('tool') or 'rien'} au lieu de {KNOWN_TOOL}"
    return "" if m.get("performance") and not m.get("dangerous") else "classement de l'outil inattendu"


def check_refusal(replies: list[dict]) -> str:
    """Un outil hors liste, sans humain : une erreur puis un resultat en echec, jamais de question ni d'execution."""
    kinds = [(m.get("type"), m.get("kind")) for m in replies]
    if ("ask", "confirm") in kinds or any(k == "tool_result" for _, k in kinds):
        return "le demon a pose une question ou execute l'outil"
    result = next((m for m in replies if m.get("type") == "result"), None)
    if result is None or result.get("exit_code") == 0:
        return "outil hors liste accepte sans presence humaine"
    errors = [str(m.get("text", "")) for m in replies if m.get("type") == "error"]
    if not any(REFUSAL_TEXT in e for e in errors):
        # refuse, mais pour une autre raison (outil inconnu...) : la garde n'est pas prouvee
        return f"refus sans rapport avec le mode sans humain : {'; '.join(errors) or 'aucun message'}"
    return ""


STEPS = (
    ("hello", {"type": "hello", "session": "smoke", "client": "oneshot"}, check_ready),
    ("ping", {"type": "ping"}, check_pong),
    ("health", {"type": "health"}, check_health),
    ("analyze", {"type": "analyze", "text": KNOWN_PHRASE}, check_analysis),
)


def run(socket_path: Path = SOCKET_PATH) -> list[tuple[str, str]]:
    """-> [(etape, erreur ou "")]. Une etape en erreur n'empeche pas les suivantes."""
    try:
        channel = connect(socket_path)
    except OSError as e:
        return [("connexion", f"demon injoignable : {e}")]
    out: list[tuple[str, str]] = []
    try:
        for name, message, check in STEPS:
            channel.send(message)
            out.append((name, check(channel.recv(TIMEOUT))))
        channel.send({"type": "tool", "name": REFUSED_TOOL, "arguments": {}, "options": {"unattended": True}})
        replies: list[dict] = []
        while len(replies) < MAX_REPLIES:
            replies.append(channel.recv(TIMEOUT))
            if replies[-1].get("type") in ("result", "busy", "ask"):
                break
        out.append(("unattended", check_refusal(replies)))
    except (ChannelClosed, TimeoutError, ValueError) as e:
        out.append(("protocole", f"{type(e).__name__} : {e}"))
    finally:
        channel.close()
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--socket", type=Path, default=SOCKET_PATH)
    results = run(parser.parse_args().socket)
    for name, error in results:
        print(f"[{'FAIL' if error else ' OK '}] {name}{' : ' + error if error else ''}")
    return 1 if any(error for _, error in results) else 0


if __name__ == "__main__":
    sys.exit(main())
