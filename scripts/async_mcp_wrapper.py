#!/usr/bin/env python3
"""
Wrapper async pour execution MCP en arriere-plan.

Lance un outil MCP (directement via script shell pour les outils ASYNC_TOOLS,
ou via MCPManager pour les autres) et envoie une notification Discord a la fin.
"""

import sys
import json
import argparse
import os
import subprocess
import threading
import time
import urllib.request
import urllib.error
from pathlib import Path

# Ajouter le repertoire parent au path
sys.path.insert(0, str(Path(__file__).parent.parent))

from modules.n8n import send_discord_notification
import yaml


# Chemins de base vers les scripts shell
FEDORA_BASE = Path.home() / "dev/fedora-setup/scripts"
VM_CTRL = FEDORA_BASE / "agents/vm-controller"
KVM = FEDORA_BASE / "kvm"
BACKUP = FEDORA_BASE / "agents/backup-manager"

# Outils executes directement via script shell (bypass MCP JSON-RPC)
ASYNC_TOOLS = {
    "vm_export",
    "vm_import",
    "vm_clone",
    "vm_clone_system",
    "backup_create",
    "backup_restore",
}


# ==============================================
# Construction des arguments shell par outil
# ==============================================

def build_args_vm_export(args_dict):
    """Construit la commande pour vm-export.sh."""
    cmd = [str(VM_CTRL / "vm-export.sh"), args_dict["vm_name"],
           f"--mode={args_dict.get('mode', 'classic')}"]
    if args_dict.get("output_path"):
        cmd += [f"--output={args_dict['output_path']}"]
    if args_dict.get("force"):
        cmd.append("--force")
    if args_dict.get("dry_run"):
        cmd.append("--dry-run")
    return cmd


def build_args_vm_import(args_dict):
    """Construit la commande pour vm-import.sh."""
    cmd = [str(VM_CTRL / "vm-import.sh"), args_dict["archive_path"]]
    if args_dict.get("new_name"):
        cmd += [f"--name={args_dict['new_name']}"]
    if args_dict.get("pool_dir"):
        cmd += [f"--pool={args_dict['pool_dir']}"]
    if args_dict.get("start"):
        cmd.append("--start")
    if args_dict.get("dry_run"):
        cmd.append("--dry-run")
    return cmd


def build_args_vm_clone(args_dict):
    """Construit la commande pour kvm-clone.sh."""
    cmd = [str(KVM / "kvm-clone.sh"), args_dict["source_vm"], args_dict["new_vm_name"]]
    if args_dict.get("start"):
        cmd.append("--start")
    if args_dict.get("linked"):
        cmd.append("--linked")
    if args_dict.get("autostart"):
        cmd.append("--autostart")
    return cmd


def build_args_vm_clone_system(args_dict):
    """Construit la commande pour kvm-clone-system.sh."""
    cmd = [
        str(KVM / "kvm-clone-system.sh"),
        "-n", args_dict.get("name", "neutron-clone"),
        "-d", args_dict.get("disk_size", "60G"),
        "-m", str(args_dict.get("memory", 8192)),
        "-c", str(args_dict.get("cpus", 4)),
        "--yes",
    ]
    if args_dict.get("hostname"):
        cmd += ["--hostname", args_dict["hostname"]]
    if args_dict.get("username"):
        cmd += ["--username", args_dict["username"]]
    if args_dict.get("dry_run"):
        cmd.append("--dry-run")
    return cmd


def build_args_backup_create(args_dict):
    """Construit la commande pour backup-create.sh."""
    cmd = [str(BACKUP / "backup-create.sh"), args_dict["type"]]
    if args_dict.get("comment"):
        cmd += [f"--comment={args_dict['comment']}"]
    if args_dict.get("verify"):
        cmd.append("--verify")
    if args_dict.get("dry_run"):
        cmd.append("--dry-run")
    if args_dict.get("vm"):
        cmd += [f"--vm={args_dict['vm']}"]
    return cmd


def build_args_backup_restore(args_dict):
    """Construit la commande pour backup-restore.sh."""
    cmd = [str(BACKUP / "backup-restore.sh"), args_dict["type"], args_dict["identifier"]]
    if args_dict.get("dry_run"):
        cmd.append("--dry-run")
    if args_dict.get("force"):
        cmd.append("--force")
    return cmd


# Mapping outil -> fonction de construction d'arguments
TOOL_BUILDERS = {
    "vm_export":      build_args_vm_export,
    "vm_import":      build_args_vm_import,
    "vm_clone":       build_args_vm_clone,
    "vm_clone_system": build_args_vm_clone_system,
    "backup_create":  build_args_backup_create,
    "backup_restore": build_args_backup_restore,
}


# ==============================================
# Execution directe du script shell
# ==============================================

def _tracking_update(tracking_id: str, tracking_api: str,
                     processed: float = None, log: str = None, extra: dict = None) -> None:
    """Envoie une mise a jour a l'API tracking (silencieux si indisponible)."""
    if not tracking_id or not tracking_api:
        return
    body = {}
    if processed is not None:
        body["processed"] = processed
    if log is not None:
        body["log"] = log
    if extra is not None:
        body["extra"] = extra
    if not body:
        return
    try:
        data = json.dumps(body).encode()
        req = urllib.request.Request(
            f"{tracking_api}/sessions/{tracking_id}",
            data=data, method="PUT",
            headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req, timeout=1)
    except (urllib.error.URLError, OSError):
        pass


def _fmt_elapsed(seconds: float) -> str:
    """Formate un temps ecoule en string lisible."""
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m{s % 60:02d}s"
    return f"{s // 3600}h{(s % 3600) // 60:02d}m"


def _start_progress_poller(progress_file: str, tracking_id: str,
                            tracking_api: str, stop_event: threading.Event) -> threading.Thread:
    """Lance un thread qui lit le fichier .progress et met a jour le tracking."""
    start_time = time.time()
    _MILESTONES = [10, 25, 50, 75, 90]

    def _poll():
        last_pct = -1
        logged_milestones: set = set()
        while not stop_event.is_set():
            try:
                elapsed = _fmt_elapsed(time.time() - start_time)
                extra: dict = {"elapsed": elapsed}
                if os.path.exists(progress_file):
                    with open(progress_file) as f:
                        data = json.load(f)
                    pct = float(data.get("pct") or data.get("percentage") or 0)
                    phase = data.get("name", "")
                    gb_done = float(data.get("gb_done") or 0)
                    gb_total = float(data.get("gb_total") or 0)
                    step = int(data.get("step") or 0)
                    total_steps = int(data.get("total") or 0)

                    # Etape courante (ex: "2/5")
                    if step and total_steps:
                        extra["etape"] = f"{step}/{total_steps}"
                    # Nom de la phase
                    if phase:
                        extra["phase"] = phase
                    # Volume transfere (quand disponible)
                    if gb_total > 0:
                        extra["transfert"] = f"{gb_done:.1f} Go / {gb_total:.1f} Go"
                    elif gb_done > 0:
                        extra["transfert"] = f"{gb_done:.1f} Go"

                    # Log milestones de progression
                    for m in _MILESTONES:
                        if pct >= m and m not in logged_milestones:
                            logged_milestones.add(m)
                            step_label = f"etape {step}/{total_steps} " if step else ""
                            _tracking_update(tracking_id, tracking_api,
                                             log=f"[INFO] {step_label}{phase}: {m}% ({elapsed})")

                    # Log Go ecrits toutes les 5 Go quand pct=0 (gros disques COW)
                    if pct == 0 and gb_done > 0 and gb_total > 0:
                        gb_bucket = int(gb_done / 5)
                        attr = f"_last_gb_bucket_{tracking_id}"
                        prev = getattr(_poll, attr, -1)
                        if gb_bucket > prev:
                            setattr(_poll, attr, gb_bucket)
                            _tracking_update(tracking_id, tracking_api,
                                             log=f"[INFO] {phase}: {gb_done:.1f} Go / {gb_total:.1f} Go ({elapsed})")

                    if pct != last_pct:
                        last_pct = pct
                        _tracking_update(tracking_id, tracking_api, processed=pct, extra=extra)
                    else:
                        _tracking_update(tracking_id, tracking_api, extra=extra)
                else:
                    _tracking_update(tracking_id, tracking_api, extra=extra)
            except Exception:
                pass
            stop_event.wait(timeout=2)

    t = threading.Thread(target=_poll, daemon=True)
    t.start()
    return t


def run_direct(tool_short: str, arguments: dict, progress_file: str,
               tracking_id: str = "", tracking_api: str = "",
               done_file: str = "") -> tuple:
    """Execute le script shell directement avec la variable de progression.

    Returns:
        (success: bool, output: str)
    """
    builder = TOOL_BUILDERS.get(tool_short)
    if builder is None:
        return False, f"Outil ASYNC inconnu: {tool_short}"

    cmd = builder(arguments)
    print(f"[i] Execution directe: {' '.join(cmd)}", file=sys.stderr)

    env = {**os.environ, "LYRA_PROGRESS_FILE": progress_file}

    # Demarrer le poller de progression si tracking actif
    stop_event = threading.Event()
    if tracking_id and tracking_api and progress_file:
        _start_progress_poller(progress_file, tracking_id, tracking_api, stop_event)

    # Popen pour capturer les logs en temps reel
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )

    # Prefixes de log a transmettre au tracking
    _LOG_KW = ("[step]", "[info]", "[warn]", "[error]", "[ok]", "[!]", "erreur", "error", "echec", "fail")

    stdout_lines: list = []
    stderr_lines: list = []

    def _stream(pipe, bucket: list, send_tracking: bool = True):
        for raw in pipe:
            line = raw.rstrip()
            bucket.append(line)
            if line and send_tracking and tracking_id and tracking_api:
                lower = line.lower()
                if any(kw in lower for kw in _LOG_KW):
                    _tracking_update(tracking_id, tracking_api, log=line)

    t_out = threading.Thread(target=_stream, args=(process.stdout, stdout_lines, True), daemon=True)
    t_err = threading.Thread(target=_stream, args=(process.stderr, stderr_lines, True), daemon=True)
    t_out.start()
    t_err.start()

    # Timeouts par outil (secondes) : eviter un wait() indefini si le script se bloque
    _TOOL_TIMEOUTS = {
        "vm_export":       7200,   # 2h max
        "vm_import":       7200,   # 2h max
        "vm_clone":         300,   # 5 min max
        "vm_clone_system": 2700,   # 45 min max
        "backup_create":   3600,   # 1h max
        "backup_restore":  3600,   # 1h max
    }
    proc_timeout = _TOOL_TIMEOUTS.get(tool_short, 1800)

    try:
        process.wait(timeout=proc_timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
        stop_event.set()
        if done_file:
            try:
                Path(done_file).write_text("1")
            except Exception:
                pass
        return False, f"Timeout: {tool_short} a depasse {proc_timeout}s"

    t_out.join(timeout=5)
    t_err.join(timeout=5)

    # Arreter le poller
    stop_event.set()

    # Ecrire le fichier done avec le code de retour (pour detection succes cross-session)
    if done_file:
        try:
            Path(done_file).write_text(str(process.returncode))
        except Exception:
            pass

    output = "\n".join(stdout_lines).strip()
    if process.returncode != 0:
        error_msg = "\n".join(stderr_lines).strip() or output
        return False, error_msg

    return True, output


# ==============================================
# Execution via MCP pour les autres outils
# ==============================================

def run_via_mcp(tool_name: str, arguments: dict, config: dict) -> tuple:
    """Execute l'outil via MCPManager (comportement original).

    Returns:
        (success: bool, output: str)
    """
    from modules.mcp import MCPManager

    mcp = MCPManager(config, verbose=False)
    result = mcp.call_tool(tool_name, arguments)
    mcp.close()

    if result.success:
        return True, result.content
    else:
        return False, result.error


# ==============================================
# Notification Discord
# ==============================================

def send_notification(webhook_url: str, tool_short: str, arguments: dict, output: str, success: bool = True):
    """Envoie une notification Discord (succes ou echec)."""
    title_map = {
        "vm_clone":       "Clone VM",
        "vm_clone_system": "Clone System VM",
        "vm_export":      "Export VM",
        "vm_import":      "Import VM",
        "backup_create":  "Backup Create",
        "backup_restore": "Backup Restore",
    }

    title = title_map.get(tool_short, tool_short)
    status_label = "OK" if success else "ERREUR"
    prefix = "[OK]" if success else "[ERREUR]"
    color = 3066993 if success else 15158332  # Vert / Rouge

    fields = [
        {"name": "Outil", "value": tool_short, "inline": True},
        {"name": "Status", "value": status_label, "inline": True},
    ]

    for key, value in arguments.items():
        if value and key not in ("start", "verbose"):
            fields.append({"name": key, "value": str(value), "inline": True})

    description = output[:500]
    if len(output) > 500:
        description += "..."

    send_discord_notification(
        webhook_url=webhook_url,
        title=f"{prefix} {title}",
        description=f"```\n{description}\n```",
        fields=fields,
        color=color,
        footer="Lyra RAG v2.0 - DevOps Assistant"
    )


# ==============================================
# Point d'entree
# ==============================================

def main():
    """Point d'entree."""
    parser = argparse.ArgumentParser(description="Async MCP Wrapper")
    parser.add_argument("--tool", required=True, help="Nom de l'outil MCP")
    parser.add_argument("--arguments", required=True, help="Arguments JSON")
    parser.add_argument("--webhook", help="URL webhook Discord")
    parser.add_argument("--task-id", help="ID de la tache (pour fichier de progression)")
    parser.add_argument("--config", default="config.yaml", help="Fichier config")
    args = parser.parse_args()

    # Charger la config
    config_path = Path(args.config)
    if not config_path.exists():
        config_path = Path(__file__).parent.parent / args.config

    with open(config_path) as f:
        config = yaml.safe_load(f)

    # Parser les arguments
    try:
        arguments = json.loads(args.arguments)
    except json.JSONDecodeError:
        print(f"Erreur: Arguments invalides: {args.arguments}", file=sys.stderr)
        sys.exit(1)

    # Determiner le nom court de l'outil
    tool_short = args.tool.split(".")[-1] if "." in args.tool else args.tool

    # Fichier de progression et done
    progress_file = ""
    done_file = ""
    if args.task_id:
        progress_file = f"/tmp/lyra_task_{args.task_id}.progress"
        done_file = f"/tmp/lyra_task_{args.task_id}.done"
        # Ecrire l'etat initial
        try:
            with open(progress_file, "w") as f:
                f.write('{"step":0,"total":1,"name":"Demarrage","pct":0,"percentage":0,"gb_done":0,"gb_total":0}\n')
        except Exception:
            pass

    # Lire le tracking_id depuis l'env (injecte par background_tasks.launch_task)
    tracking_id = os.environ.get("LYRA_TRACKING_ID", "")
    tracking_api = config.get("tracking", {}).get("api_url", "http://127.0.0.1:8765")

    # Choisir le mode d'execution
    if tool_short in ASYNC_TOOLS:
        print(f"[i] Mode direct (bypass MCP): {tool_short}", file=sys.stderr)
        success, output = run_direct(tool_short, arguments, progress_file,
                                     tracking_id=tracking_id, tracking_api=tracking_api,
                                     done_file=done_file)
    else:
        print(f"[i] Mode MCP: {args.tool}", file=sys.stderr)
        success, output = run_via_mcp(args.tool, arguments, config)
        # Ecrire done_file aussi pour les outils non-ASYNC_TOOLS
        if done_file:
            try:
                Path(done_file).write_text("0" if success else "1")
            except Exception:
                pass

    # Supprimer le fichier de progression
    if progress_file and os.path.exists(progress_file):
        try:
            os.remove(progress_file)
        except Exception:
            pass

    # Envoyer notification Discord si webhook fourni (succes ou echec)
    if args.webhook:
        try:
            send_notification(args.webhook, tool_short, arguments, output, success=success)
        except Exception as e:
            print(f"[!] Erreur notification Discord: {e}", file=sys.stderr)

    # Afficher le resultat et quitter
    if success:
        print(output)
        sys.exit(0)
    else:
        print(output, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
