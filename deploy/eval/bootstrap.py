"""Amorcage du chemin d'evaluation (roadmap #44) : conteneur ou Codespace, mode texte.

Au demarrage : config.yaml derivee de config.yaml.example (jamais recopiee a la
main, elle suivrait mal l'exemple), attente d'Ollama, telechargement des deux
modeles legers s'ils manquent, index RAG construit s'il est vide, puis
lancement du demon. Idempotent : un redemarrage ne refait que le necessaire.

Les fonctions pures (eval_config, missing_models, ...) sont testees dans
tests/unit/test_eval_bootstrap.py.
"""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[2]
DENON_MCP = "/opt/mcp/denon/bin/denon-mcp"
TRACKING_VENV = "/opt/tracking"


def eval_config(example: dict[str, Any], env: Mapping[str, str]) -> dict[str, Any]:
    """config.yaml d'evaluation : texte seul, CPU, un MCP d'exemple, aucun appareil."""
    cfg = copy.deepcopy(example)
    models = cfg.setdefault("models", {})
    ephaistos = models.setdefault("ephaistos", {}).get("name", "qwen2.5-coder:0.5b")
    llm = cfg.setdefault("llm", {})
    llm["base_url"] = "http://ollama:11434"  # OLLAMA_HOST prime au runtime (get_ollama_base_url)
    llm["model"] = ephaistos  # l'exemple vise un 14b de production : trop lourd ici
    for mode in (cfg.get("modes") or {}).values():
        if isinstance(mode, dict):
            mode["tts_response"] = False  # pas de haut-parleur dans un conteneur
    cfg["stt"] = {**(cfg.get("stt") or {}), "device": "cpu", "compute_type": "int8"}
    # Rien qui sorte vers un service tiers ou un appareil du proprietaire du depot.
    for section in ("n8n", "discord", "homeassistant", "notion"):
        if isinstance(cfg.get(section), dict):
            cfg[section]["enabled"] = False
    # Les sections d'appareils de l'exemple portent des adresses fictives
    # (203.0.113.X) que les MCP relisent dans config.yaml : un appel partait
    # alors en timeout au lieu de dire « appareil non configure ».
    for section, key in (("tv", "host"), ("denon", "host"), ("hue", "bridge_ip")):
        if isinstance(cfg.get(section), dict):
            cfg[section][key] = ""
    if env.get("DENON_HOST"):
        cfg.setdefault("denon", {})["host"] = env["DENON_HOST"]
    denon_env = {k: env[k] for k in ("DENON_HOST", "DENON_PORT", "DENON_MAC") if env.get(k)}
    cfg["mcp"] = {**(cfg.get("mcp") or {}), "servers": {
        "denon": {"enabled": True, "command": DENON_MCP, "args": [], "env": denon_env,
                  "timeout": 10, "keep_alive": True},
    }}
    cfg["tracking"] = {"api_url": "http://127.0.0.1:8765",
                       "server_script": f"{TRACKING_VENV}/lib/python3.12/site-packages/server.py",
                       "venv_python": f"{TRACKING_VENV}/bin/python"}
    return cfg


def wanted_models(cfg: Mapping[str, Any]) -> list[str]:
    models = cfg.get("models") or {}
    names = [(models.get(role) or {}).get("name") for role in ("ephaistos", "lyra")]
    return [n for n in dict.fromkeys(names) if n]


def _norm(name: str) -> str:
    return name if ":" in name else f"{name}:latest"


def missing_models(tags: Mapping[str, Any], wanted: list[str]) -> list[str]:
    """Modeles de `wanted` absents de la reponse GET /api/tags d'Ollama."""
    have = {_norm(m.get("name", "")) for m in tags.get("models", []) if isinstance(m, dict)}
    return [w for w in wanted if _norm(w) not in have]


def index_is_empty(chroma_dir: Path) -> bool:
    """Pas de base ChromaDB -> il faut indexer (premier demarrage)."""
    return not (chroma_dir / "chroma.sqlite3").exists()


def ollama_url(env: Mapping[str, str]) -> str:
    sys.path.insert(0, str(ROOT))
    from lyra.core.config import ollama_url_depuis_env
    return ollama_url_depuis_env(env.get("OLLAMA_HOST")) or "http://ollama:11434"


def _get_json(url: str, timeout: float = 5.0) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.load(r)


def wait_for_ollama(base: str, timeout_s: float = 300.0) -> dict:
    deadline = time.monotonic() + timeout_s
    while True:
        try:
            return _get_json(f"{base}/api/tags")
        except (urllib.error.URLError, OSError, ValueError) as exc:
            if time.monotonic() > deadline:
                raise SystemExit(f"Ollama injoignable sur {base} apres {timeout_s:.0f} s : {exc}")
            print(f"[eval] attente d'Ollama ({base})...", flush=True)
            time.sleep(3)


def pull(base: str, model: str) -> None:
    print(f"[eval] telechargement du modele {model} (une seule fois, garde dans le volume)", flush=True)
    req = urllib.request.Request(f"{base}/api/pull", data=json.dumps({"model": model}).encode(),
                                 headers={"Content-Type": "application/json"})
    last = ""
    with urllib.request.urlopen(req, timeout=3600) as r:
        for line in r:
            event = json.loads(line or b"{}")
            if "error" in event:
                raise SystemExit(f"echec du telechargement de {model} : {event['error']}")
            status = event.get("status", "")
            if status and status != last:
                print(f"[eval]   {model} : {status}", flush=True)
                last = status


def main() -> int:
    env = os.environ
    config_path = ROOT / "config.yaml"
    import yaml

    if not config_path.exists():
        example = yaml.safe_load((ROOT / "config.yaml.example").read_text(encoding="utf-8"))
        config_path.write_text(yaml.safe_dump(eval_config(example, env), allow_unicode=True, sort_keys=False),
                               encoding="utf-8")
        print("[eval] config.yaml d'evaluation ecrite (texte seul, MCP d'exemple : denon)", flush=True)
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    base = ollama_url(env)
    tags = wait_for_ollama(base)
    for model in missing_models(tags, wanted_models(cfg)):
        pull(base, model)

    if index_is_empty(ROOT / ".chromadb"):
        py = sys.executable
        for script, args in (("reindex_mcp_rag_optimized.py", []), ("index_rag_3tier.py", ["--clear"])):
            print(f"[eval] index RAG : {script}", flush=True)
            subprocess.run([py, str(ROOT / "scripts" / script), *args], cwd=ROOT, check=True)

    if "--no-daemon" in sys.argv:
        return 0
    os.execv(sys.executable, [sys.executable, "-m", "lyra.daemon"])
    return 0  # jamais atteint


if __name__ == "__main__":
    sys.exit(main())
