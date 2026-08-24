#!/usr/bin/env python3
"""Smoke test des serveurs MCP de Lyra + metriques vers le tracking.

Pour chaque serveur de config.yaml (mcp.servers) :
  1. spawn du process (stdio)
  2. handshake JSON-RPC initialize
  3. tools/list
  4. mesure des latences (spawn->init, init->tools)

Resultats reportes dans une session tracking (template machine) visible dans
neutroncore/le dashboard TUI : un serveur KO = session en erreur.

Le smoke s'adapte a l'installation : seuls les serveurs presents dans
config.yaml (mcp.servers) sont testes. Zero serveur configure = rien a
verifier, sortie 0 (une installation minimale de Lyra reste valide).

Usage:
  .venv/bin/python scripts/smoke_mcps.py                 # tous les serveurs configures
  .venv/bin/python scripts/smoke_mcps.py --only tv,hue   # sous-ensemble
  .venv/bin/python scripts/smoke_mcps.py --no-track      # sans rapport tracking

Sortie : code 0 si tous OK, 1 sinon. Seuils ajustables par variables
d'environnement : LYRA_SMOKE_TIMEOUT (defaut 15s), LYRA_SMOKE_SLOW (defaut 10s).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
TRACKING_API = "http://127.0.0.1:8765"
INIT_TIMEOUT = float(os.environ.get("LYRA_SMOKE_TIMEOUT", "15"))
SLOW_THRESHOLD_S = float(os.environ.get("LYRA_SMOKE_SLOW", "10"))  # au-dela : WARN


def _jsonrpc_line(msg_id: int, method: str, params: dict | None = None) -> bytes:
    payload = {"jsonrpc": "2.0", "id": msg_id, "method": method,
               "params": params or {}}
    return (json.dumps(payload) + "\n").encode()


def _read_response(proc: subprocess.Popen, want_id: int, deadline: float) -> dict:
    """Lit les lignes stdout jusqu'a la reponse want_id (ignore les notifs)."""
    while time.monotonic() < deadline:
        line = proc.stdout.readline()
        if not line:
            raise RuntimeError("stdout ferme (le serveur a probablement crashe)")
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue  # log parasite sur stdout
        if msg.get("id") == want_id:
            if "error" in msg:
                raise RuntimeError(f"erreur JSON-RPC: {msg['error']}")
            return msg.get("result", {})
    raise TimeoutError(f"pas de reponse id={want_id} en {INIT_TIMEOUT}s")


def smoke_one(name: str, spec: dict) -> dict:
    """Smoke un serveur : retourne {ok, init_s, tools_s, tool_count, error}."""
    cmd = [spec["command"], *spec.get("args", [])]
    # meme PATH que le daemon (install/lyra-daemon.service) : .venv/bin en
    # tete pour que "command: python" resolve le venv lyra
    env = {**os.environ, **spec.get("env", {})}
    env["PATH"] = f"{ROOT}/.venv/bin:" + env.get("PATH", "")
    t0 = time.monotonic()
    try:
        proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, env=env,
        )
    except OSError as e:
        return {"ok": False, "init_s": 0.0, "tools_s": 0.0,
                "tool_count": 0, "error": f"spawn impossible: {e}"}
    try:
        deadline = time.monotonic() + INIT_TIMEOUT
        proc.stdin.write(_jsonrpc_line(1, "initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "lyra-smoke", "version": "1.0"},
        }))
        proc.stdin.flush()
        _read_response(proc, 1, deadline)
        init_s = time.monotonic() - t0

        proc.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
        proc.stdin.write(_jsonrpc_line(2, "tools/list"))
        proc.stdin.flush()
        t1 = time.monotonic()
        result = _read_response(proc, 2, deadline)
        tools = result.get("tools", [])
        if not tools:
            raise RuntimeError("tools/list vide")
        return {"ok": True, "init_s": round(init_s, 2),
                "tools_s": round(time.monotonic() - t1, 2),
                "tool_count": len(tools), "error": ""}
    except Exception as e:  # noqa: BLE001 - tout echec = serveur KO
        return {"ok": False, "init_s": round(time.monotonic() - t0, 2),
                "tools_s": 0.0, "tool_count": 0, "error": str(e)[:180]}
    finally:
        proc.kill()
        proc.wait(timeout=5)


def report_tracking(results: dict[str, dict]) -> None:
    """Cree une session tracking avec un item par serveur (best-effort)."""
    try:
        import requests
    except ImportError:
        return
    all_ok = all(r["ok"] for r in results.values())
    items = [{"name": f"{n} ({r['tool_count']} outils, init {r['init_s']}s)"
              if r["ok"] else f"{n} — {r['error'][:60]}",
              "status": "done" if r["ok"] else "error"}
             for n, r in results.items()]
    try:
        resp = requests.post(f"{TRACKING_API}/sessions", timeout=3, json={
            "name": f"[SMOKE] MCP servers ({sum(r['ok'] for r in results.values())}"
                    f"/{len(results)} OK)",
            "template": "machine",
            "total": len(results),
            "items": items,
        })
        resp.raise_for_status()
        # l'API ignore status/processed au POST : cloture via PUT
        sid = resp.json().get("id")
        if sid:
            requests.put(f"{TRACKING_API}/sessions/{sid}", timeout=3, json={
                "status": "done" if all_ok else "error",
                "processed": sum(r["ok"] for r in results.values()),
            })
    except Exception:  # noqa: BLE001 - le tracking est optionnel, jamais bloquant
        pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-track", action="store_true",
                        help="ne pas reporter au tracking")
    parser.add_argument("--only", default="",
                        help="serveurs a tester, separes par des virgules (defaut: tous)")
    args = parser.parse_args()

    config = yaml.safe_load(open(ROOT / "config.yaml"))
    servers = config.get("mcp", {}).get("servers", {})
    if args.only:
        wanted = {s.strip() for s in args.only.split(",") if s.strip()}
        unknown = wanted - servers.keys()
        if unknown:
            print(f"Serveurs inconnus dans config.yaml: {', '.join(sorted(unknown))}")
            print(f"Configures: {', '.join(servers) or 'aucun'}")
            return 1
        servers = {n: s for n, s in servers.items() if n in wanted}
    if not servers:
        # Installation sans MCP : rien a smoker, ce n'est pas un echec
        print("Aucun serveur MCP configure (config.yaml mcp.servers) — rien a verifier.")
        return 0

    results: dict[str, dict] = {}
    for name, spec in servers.items():
        r = smoke_one(name, spec)
        results[name] = r
        if r["ok"]:
            slow = " [LENT]" if r["init_s"] > SLOW_THRESHOLD_S else ""
            print(f"[OK]   {name:8} {r['tool_count']:3} outils | "
                  f"init {r['init_s']}s | tools/list {r['tools_s']}s{slow}")
        else:
            print(f"[FAIL] {name:8} {r['error']}")

    if not args.no_track:
        report_tracking(results)

    failed = [n for n, r in results.items() if not r["ok"]]
    slow = [n for n, r in results.items() if r["ok"] and r["init_s"] > SLOW_THRESHOLD_S]
    if slow:
        print(f"\nLatence anormale (> {SLOW_THRESHOLD_S}s): {', '.join(slow)}")
    if failed:
        print(f"\nServeurs KO: {', '.join(failed)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
