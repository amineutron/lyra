"""Etape par MCP : clone du repo dedie + installation + extras.

Extras declares dans le catalogue (extra_steps) :
  npm_build    : npm install + npm run build (fedora-agents)
  sudoers      : copie root:root des scripts dans /usr/local/lib/lyra/scripts
                 + /etc/sudoers.d/lyra NOPASSWD par script (visudo -cf)
  pip_catt     : outils catt + yt-dlp dans le venv
  hue_pairing  : pairing bouton du bridge (username+clientkey -> secrets)
"""
from __future__ import annotations

import getpass
import subprocess
import tempfile
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
            targets = _install_system_scripts(ctx, dest / "scripts")
            _write_sudoers(ctx, targets)
        elif extra == "hue_pairing":
            _hue_pairing(ctx, mcp)


# --- Scripts systeme + sudoers -------------------------------------------
#
# Les scripts bash de fedora-agents (vm-controller, backup-manager, kvm) sont
# copies en root:root 0755 dans SYSTEM_SCRIPTS_DIR, et SEULE cette copie est
# citee dans /etc/sudoers.d/lyra, script par script. Jamais de glob, jamais
# un chemin sous $HOME : un dossier inscriptible par l'utilisateur cite dans
# une regle NOPASSWD equivaut a NOPASSWD: ALL (n'importe quel processus de son
# uid y depose un .sh et obtient root).

SYSTEM_SCRIPTS_DIR = Path("/usr/local/lib/lyra/scripts")
SUDOERS_SUBDIRS = ("agents/vm-controller", "agents/backup-manager", "kvm")
SUDOERS_BINARIES = ("/usr/bin/virsh", "/usr/bin/virt-clone", "/usr/bin/qemu-img")
_GLOB_CHARS = set("*?[]")


def _sudo(cmd: list[str], *, input: str | None = None,
          timeout: int = 30) -> "subprocess.CompletedProcess[str]":
    """sudo -n : echoue immediatement si le cache sudo n'est pas amorce
    (voir sudoprime.py) au lieu d'attendre un mot de passe illisible."""
    try:
        return subprocess.run(["sudo", "-n", *cmd], input=input,
                              capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"{cmd[0]} : sudo attend un mot de passe (cache expire) "
            "-- relance l'installeur")


def _sudo_checked(cmd: list[str], what: str) -> None:
    proc = _sudo(cmd)
    if proc.returncode != 0:
        raise RuntimeError(f"echec {what} : {proc.stderr.strip() or proc.stdout.strip()}")


def sudoers_targets(src: Path, system_dir: Path = SYSTEM_SCRIPTS_DIR) -> list[Path]:
    """Scripts d'entree (dans SUDOERS_SUBDIRS) -> chemins de la copie systeme.

    Exclus : common.sh (source, pas execute) et les helpers prefixes '_'.
    Logique pure, testable sans sudo.
    """
    targets: list[Path] = []
    for sub in SUDOERS_SUBDIRS:
        d = src / sub
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.sh")):
            if f.name == "common.sh" or f.name.startswith("_"):
                continue
            targets.append(system_dir / sub / f.name)
    return targets


def build_sudoers_rules(user: str, targets: list[Path],
                        binaries: tuple[str, ...] = SUDOERS_BINARIES) -> str:
    """Une regle NOPASSWD par chemin absolu, sans aucun glob. Logique pure."""
    lines = []
    for t in [*targets, *map(Path, binaries)]:
        p = str(t)
        if not p.startswith("/") or _GLOB_CHARS & set(p) or any(c.isspace() for c in p):
            raise ValueError(f"chemin sudoers refuse : {p!r}")
        lines.append(f"{user} ALL=(ALL) NOPASSWD: {p}")
    header = ("# Genere par l'installeur Lyra -- regles par script, copie systeme "
              "root:root uniquement. Ne pas ajouter de glob ni de chemin sous /home.\n")
    return header + "\n".join(lines) + "\n"


def _install_system_scripts(ctx: StepContext, src: Path) -> list[Path]:
    """Copie src/ (scripts/ du clone fedora-agents) vers SYSTEM_SCRIPTS_DIR
    en root:root, 0755 pour les .sh, 0644 pour le reste."""
    if not src.is_dir():
        raise RuntimeError(f"scripts introuvables : {src} (fedora-agents trop ancien ?)")
    ctx.emit(Output(f"Installation des scripts dans {SYSTEM_SCRIPTS_DIR} (root:root)"))
    _sudo_checked(["install", "-d", "-o", "root", "-g", "root", "-m", "0755",
                   str(SYSTEM_SCRIPTS_DIR)], "creation du dossier systeme")
    n = 0
    for path in sorted(src.rglob("*")):
        rel = path.relative_to(src)
        dest = SYSTEM_SCRIPTS_DIR / rel
        if path.is_dir():
            _sudo_checked(["install", "-d", "-o", "root", "-g", "root", "-m", "0755",
                           str(dest)], f"creation de {dest}")
        elif path.is_file():
            mode = "0755" if path.suffix == ".sh" else "0644"
            _sudo_checked(["install", "-o", "root", "-g", "root", "-m", mode,
                           str(path), str(dest)], f"copie de {rel}")
            n += 1
    ctx.emit(Output(f"{n} fichiers installes"))
    return sudoers_targets(src)


def _write_sudoers(ctx: StepContext, targets: list[Path]) -> None:
    """Ecrit /etc/sudoers.d/lyra : validation visudo -cf AVANT activation."""
    rules = build_sudoers_rules(getpass.getuser(), targets)

    if not ctx.broker.confirm(
            f"Ecrire {_SUDOERS_PATH} ({len(targets)} scripts systeme + virsh, "
            "NOPASSWD, sans glob) ?", True):
        ctx.emit(Output("sudoers saute — les operations VM demanderont un mot de passe"))
        return

    with tempfile.NamedTemporaryFile("w", suffix=".sudoers", delete=False) as tmp:
        tmp.write(rules)
        tmp_path = tmp.name
    try:
        check = _sudo(["visudo", "-cf", tmp_path])
        if check.returncode != 0:
            raise RuntimeError(
                "sudoers invalide, fichier NON installe : "
                f"{check.stderr.strip() or check.stdout.strip()}")
        _sudo_checked(["install", "-o", "root", "-g", "root", "-m", "0440",
                       tmp_path, _SUDOERS_PATH], "installation de " + _SUDOERS_PATH)
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    ctx.emit(Output(f"{_SUDOERS_PATH} ecrit et valide (visudo -cf)"))


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
