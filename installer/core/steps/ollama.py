"""Etapes : Ollama (local ou distant) + modeles LLM legers."""
from __future__ import annotations

import shutil
from pathlib import Path

from ..events import Output
from ..pipeline import StepContext
from ..proxyenv import ollama_proxy_dropin, proxy_display
from ..runner import run

OLLAMA_DROPIN = "/etc/systemd/system/ollama.service.d/proxy.conf"

MODELS = ["qwen2.5-coder:0.5b", "llama3.2:1b"]


def _append_once(path: Path, marker: str, block: str) -> bool:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    if marker in text:
        return False
    with open(path, "a", encoding="utf-8") as f:
        f.write(block)
    return True


def run_ollama(ctx: StepContext) -> None:
    host = ctx.state.ollama_host

    # Le binaire client 'ollama' est requis meme en mode distant : 'ollama
    # pull' s'appuie dessus pour parler au serveur via OLLAMA_HOST.
    if shutil.which("ollama"):
        ctx.emit(Output("Ollama deja installe"))
    else:
        prompt = ("Installer le client Ollama (script officiel ollama.ai, "
                  "sudo) pour parler au serveur distant ?" if host else
                  "Installer Ollama (script officiel ollama.ai, sudo) ?")
        ok = ctx.broker.confirm(prompt, True)
        if not ok:
            raise RuntimeError("Ollama requis (ou relancer avec --ollama-host)")
        # Seul usage shell=True du projet : le script officiel s'installe
        # via curl | sh. Isole et volontaire.
        import subprocess
        proc = subprocess.run(
            "curl -fsSL https://ollama.ai/install.sh | sh",
            shell=True, capture_output=True, text=True)
        for line in (proc.stdout + proc.stderr).splitlines()[-10:]:
            ctx.emit(Output(line))
        if proc.returncode != 0:
            raise RuntimeError("echec installation Ollama")

    if host:
        bashrc = Path.home() / ".bashrc"
        added = _append_once(bashrc, "OLLAMA_HOST=",
                             f"\nexport OLLAMA_HOST={host}:11434\n")
        ctx.emit(Output(f"Ollama distant : {host}:11434"
                        + (" (export ajoute au .bashrc)" if added else "")))
        return

    _install_proxy_dropin(ctx)
    run(["sudo", "systemctl", "enable", "--now", "ollama"],
        ctx.emit, step_id=ctx.step_id, check=False)


def _install_proxy_dropin(ctx: StepContext) -> None:
    """Derriere un proxy, le service ollama doit le connaitre pour 'ollama pull'
    (il n'herite pas du shell). Rien a faire sans proxy."""
    import os
    import subprocess

    content = ollama_proxy_dropin(os.environ)
    if content is None:
        return
    ctx.emit(Output(f"Proxy detecte ({proxy_display(os.environ)}) : drop-in systemd pour le service ollama"))
    run(["sudo", "mkdir", "-p", str(Path(OLLAMA_DROPIN).parent)], ctx.emit, step_id=ctx.step_id)
    proc = subprocess.run(["sudo", "-n", "tee", OLLAMA_DROPIN], input=content,
                          capture_output=True, text=True, timeout=30)
    if proc.returncode != 0:
        raise RuntimeError(f"ecriture de {OLLAMA_DROPIN} impossible : {proc.stderr.strip()}")
    run(["sudo", "systemctl", "daemon-reload"], ctx.emit, step_id=ctx.step_id)
    # un service deja demarre doit relire son environnement
    run(["sudo", "systemctl", "try-restart", "ollama"], ctx.emit, step_id=ctx.step_id, check=False)


def run_models(ctx: StepContext) -> None:
    env = {}
    if ctx.state.ollama_host:
        env["OLLAMA_HOST"] = f"{ctx.state.ollama_host}:11434"
    for model in MODELS:
        ctx.emit(Output(f"Telechargement {model}..."))
        run(["ollama", "pull", model], ctx.emit, step_id=ctx.step_id, env=env)
