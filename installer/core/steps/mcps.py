"""Etape par MCP : clone du repo dedie + installation + extras.

Extras declares dans le catalogue (extra_steps) :
  npm_build    : npm install + npm run build (fedora-agents)
  sudoers      : /etc/sudoers.d/lyra NOPASSWD (virsh, scripts KVM/backup)
  pip_catt     : outils catt + yt-dlp dans le venv
  hue_pairing  : pairing bouton du bridge (username+clientkey -> secrets)
"""
from __future__ import annotations

import time
from pathlib import Path

import requests

from ..catalog import McpDef
from ..events import Output, Progress
from ..gitauth import resolve_repo_url
from ..pipeline import StepContext, StepFn
from ..runner import pip_detail, run

_SUDOERS_PATH = "/etc/sudoers.d/lyra"


def make_step(mcp: McpDef) -> StepFn:
    def _step(ctx: StepContext) -> None:
        _install_mcp(ctx, mcp)
    return _step


def _install_mcp(ctx: StepContext, mcp: McpDef) -> None:
    mapping = {"lyra": str(ctx.state.lyra_dir), "home": str(Path.home())}
    dest = Path(mcp.dest.format(**mapping))

    if (dest / ".git").exists():
        ctx.emit(Output(f"{mcp.name} : deja clone, mise a jour"))
        run(["git", "-C", str(dest), "pull", "--ff-only"], ctx.emit,
            step_id=ctx.step_id, check=False)
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        repo_url = resolve_repo_url(ctx, mcp.repo)
        run(["git", "clone", "--depth=1", repo_url, str(dest)], ctx.emit,
            step_id=ctx.step_id)

    pip = str(ctx.state.lyra_dir / ".venv" / "bin" / "pip")
    if mcp.runtime == "python":
        if (dest / "pyproject.toml").exists():
            run([pip, "install", "-e", str(dest)], ctx.emit,
                step_id=ctx.step_id, detail_fn=pip_detail)
        elif (dest / "requirements.txt").exists():
            run([pip, "install", "-r", str(dest / "requirements.txt")],
                ctx.emit, step_id=ctx.step_id, detail_fn=pip_detail)

    for extra in mcp.extra_steps:
        if extra == "npm_build":
            run(["npm", "install"], ctx.emit, step_id=ctx.step_id, cwd=dest)
            run(["npm", "run", "build"], ctx.emit, step_id=ctx.step_id, cwd=dest)
        elif extra == "pip_catt":
            run([pip, "install", "catt", "yt-dlp"], ctx.emit,
                step_id=ctx.step_id, detail_fn=pip_detail)
        elif extra == "sudoers":
            _write_sudoers(ctx)
        elif extra == "hue_pairing":
            _hue_pairing(ctx, mcp)


def _write_sudoers(ctx: StepContext) -> None:
    """Regles NOPASSWD pour les scripts VM/backup (install-lyra-mcp.sh)."""
    home = Path.home()
    rules = "\n".join([
        f"{home.name} ALL=(ALL) NOPASSWD: {home}/dev/fedora-setup/scripts/kvm/*.sh",
        f"{home.name} ALL=(ALL) NOPASSWD: {home}/dev/fedora-setup/scripts/agents/vm-controller/*.sh",
        f"{home.name} ALL=(ALL) NOPASSWD: {home}/dev/fedora-setup/scripts/agents/backup-manager/*.sh",
        f"{home.name} ALL=(ALL) NOPASSWD: /usr/bin/virsh",
        f"{home.name} ALL=(ALL) NOPASSWD: /usr/bin/virt-clone",
        f"{home.name} ALL=(ALL) NOPASSWD: /usr/bin/qemu-img",
    ]) + "\n"

    if not ctx.broker.confirm(
            f"Ecrire {_SUDOERS_PATH} (NOPASSWD virsh/scripts KVM, sudo) ?", True):
        ctx.emit(Output("sudoers saute — les operations VM demanderont un mot de passe"))
        return
    import subprocess
    try:
        proc = subprocess.run(["sudo", "-n", "tee", _SUDOERS_PATH],
                              input=rules, capture_output=True, text=True,
                              timeout=30)
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            "ecriture sudoers : sudo attend un mot de passe (cache expire) "
            "-- relance l'installeur")
    if proc.returncode != 0:
        raise RuntimeError(f"echec ecriture sudoers : {proc.stderr.strip()}")
    run(["sudo", "chmod", "440", _SUDOERS_PATH], ctx.emit, step_id=ctx.step_id)


def _hue_pairing(ctx: StepContext, mcp: McpDef, total: int = 30) -> None:
    """Pairing du bridge : polling POST /api pendant `total` secondes.

    Resultat (username + clientkey) depose dans state.secrets['hue'] —
    ecrit dans secrets.yaml par l'etape config, jamais dans config.yaml.
    """
    bridge_ip = (ctx.state.device_config.get(mcp.id) or {}).get("bridge_ip", "")
    if not bridge_ip:
        raise RuntimeError("IP du bridge Hue manquante")

    while True:
        ctx.broker.confirm(
            f"Appuie sur le bouton du bridge Hue ({bridge_ip}) puis valide",
            default=True)
        for remaining in range(total, 0, -1):
            ctx.emit(Progress(ctx.step_id,
                              f"pairing... {remaining}s restantes"))
            try:
                r = requests.post(
                    f"http://{bridge_ip}/api",
                    json={"devicetype": "lyra#installer",
                          "generateclientkey": True},
                    timeout=1.5)
                data = r.json()
                if isinstance(data, list) and data and "success" in data[0]:
                    success = data[0]["success"]
                    hue = dict(ctx.state.secrets.get("hue") or {})
                    hue["username"] = success.get("username", "")
                    hue["clientkey"] = success.get("clientkey", "")
                    ctx.state.secrets["hue"] = hue
                    ctx.emit(Output("Pairing Hue reussi"))
                    return
            except requests.RequestException:
                pass
            time.sleep(1)

        if not ctx.broker.confirm("Bouton non detecte. Reessayer ?", True):
            raise RuntimeError("pairing Hue abandonne")
