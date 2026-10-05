"""Alerte ntfy quand le smoke test MCP echoue.

Lance par systemd via `OnFailure=` de lyra-mcp-smoke.service : relit la
sortie de l'invocation en echec dans le journal et publie un resume sur ntfy.

Optionnel : sans NTFY_URL dans l'environnement, ne fait rien (exit 0).
Variables : NTFY_URL, NTFY_TOPIC (defaut lyra-alerts), NTFY_TOKEN (Bearer,
facultatif). On les fournit par EnvironmentFile= dans un drop-in local, jamais
en dur dans l'unite.
"""
from __future__ import annotations

import os
import subprocess
import sys
import urllib.request

UNIT = "lyra-mcp-smoke.service"
MAX_MESSAGE = 1000
_TAIL = 8


def build_alert(lines: list[str]) -> dict:
    """Resume ntfy (title, message, priority) a partir de la sortie du smoke."""
    lines = [ln.rstrip() for ln in lines if ln.strip()]
    fails = [ln for ln in lines if ln.startswith("[FAIL]")]
    names = [ln.split()[1] for ln in fails if len(ln.split()) > 1]
    if names:
        title = f"Smoke MCP : {', '.join(names)} KO"
        body = "\n".join(fails)
    else:
        title = "Smoke MCP en echec"
        body = "\n".join(lines[-_TAIL:]) or "Aucune sortie dans le journal (voir journalctl --user -u lyra-mcp-smoke)."
    if len(body) > MAX_MESSAGE:
        body = body[: MAX_MESSAGE - 3] + "..."
    return {"title": title, "message": body, "priority": 4}


def read_journal() -> list[str]:
    """Sortie de l'invocation en echec.

    systemd fournit MONITOR_INVOCATION_ID, sauf s'il voit plusieurs unites
    declencheuses ("multiple trigger source candidates") : on lit alors la
    derniere invocation de l'unite (-I, systemd >= 257).
    """
    cmd = ["journalctl", "--user", "-o", "cat", "--no-pager"]
    invocation = os.environ.get("MONITOR_INVOCATION_ID", "")
    cmd += [f"_SYSTEMD_INVOCATION_ID={invocation}"] if invocation else ["-u", UNIT, "-I"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=10, check=False).stdout
    except (OSError, subprocess.TimeoutExpired) as e:
        return [f"journal illisible : {e}"]
    return out.splitlines()


def publish(url: str, topic: str, token: str, alert: dict) -> None:
    """POST ntfy (titre et priorite en en-tetes, message en corps)."""
    headers = {"Title": alert["title"].encode("utf-8"), "Priority": str(alert["priority"]),
               "Tags": "warning"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{url.rstrip('/')}/{topic}", data=alert["message"].encode("utf-8"),
                                 headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        resp.read()


def main() -> int:
    url = os.environ.get("NTFY_URL", "")
    if not url:
        print("NTFY_URL absent : alerte desactivee.")
        return 0
    alert = build_alert(read_journal())
    try:
        publish(url, os.environ.get("NTFY_TOPIC", "lyra-alerts"), os.environ.get("NTFY_TOKEN", ""), alert)
    except OSError as e:
        print(f"Echec de publication ntfy : {e}", file=sys.stderr)
        return 1
    print(f"Alerte envoyee : {alert['title']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
