"""
Lyra Client - Point d'entree CLI.

Route les invocations :
- one-shot texte  -> demon (relance auto si mort) puis fallback standalone
- interactif / vocal / legacy / --standalone -> main_rag historique (Phase 4
  du chantier demon : le REPL deviendra client a son tour)

Codes de sortie identiques a run_one_shot : 0=ok, 1=erreur, 2=annule, 3=args.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _exec_standalone(argv: list[str]) -> None:
    """Remplace le process par le main_rag historique (fallback ou interactif)."""
    os.chdir(REPO_ROOT)
    os.execv(sys.executable,
             [sys.executable, str(REPO_ROOT / "main_rag.py"), "--rag-enhanced",
              *argv])


def run_oneshot_via_daemon(request: str, args: argparse.Namespace) -> int:
    """Requete one-shot via le demon. Retourne un code de sortie, ou -1 si le
    demon est indisponible (le caller bascule en standalone)."""
    from lyra.client.launcher import ensure_daemon
    from lyra.client.render import answer_ask, render_output, render_progress
    from lyra.daemon.protocol import ChannelClosed
    from modules import ui

    waiting = {"shown": False}

    def on_wait():
        if not waiting["shown"]:
            print(f"{ui.Colors.DIM}  (re)demarrage du demon Lyra...{ui.Colors.RESET}",
                  flush=True)
            waiting["shown"] = True

    channel, greeting = ensure_daemon(on_wait=on_wait)
    if greeting:
        ui.print_lyra(greeting)
    if channel is None:
        return -1  # demon introuvable -> standalone

    print(f"{ui.Colors.CYAN}LYRA{ui.Colors.RESET}  {request}", flush=True)

    mode = "performance" if args.performance else "default"
    try:
        channel.send({"type": "hello", "session": "default", "client": "oneshot"})
        ready = channel.recv(timeout=10)
        if ready.get("type") != "ready":
            return -1
        channel.send({
            "type": "request",
            "text": request,
            "options": {"mode": mode, "yes": args.yes,
                        "verbose": args.verbose, "interactive": False},
        })
        while True:
            message = channel.recv(timeout=600)
            mtype = message.get("type")
            if mtype == "output":
                render_output(message)
            elif mtype == "progress":
                render_progress(message, verbose=args.verbose)
            elif mtype == "busy":
                ui.print_info(message.get("text", "Lyra est occupee..."))
            elif mtype == "ask":
                answer = answer_ask(message)
                if answer is None:
                    channel.send({"type": "cancel"})
                    ui.print_warning("Annule.")
                    return 2
                channel.send({"type": "answer", "value": answer})
            elif mtype == "result":
                return int(message.get("exit_code", 1))
            elif mtype == "error":
                ui.print_error(message.get("text", "erreur protocole"))
                return 1
    except (ChannelClosed, TimeoutError, ValueError) as e:
        ui.print_error(f"Connexion au demon perdue: {e}")
        return 1
    except KeyboardInterrupt:
        try:
            channel.send({"type": "cancel"})
        except Exception:
            pass
        print()
        ui.print_warning("Annule.")
        return 2
    finally:
        channel.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Lyra client", add_help=True)
    parser.add_argument("request", nargs="?", default=None)
    parser.add_argument("--vocal", action="store_true")
    parser.add_argument("-p", "--performance", action="store_true")
    parser.add_argument("--config", "-c", default="config.yaml")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--rag-enhanced", action="store_true")  # implicite
    parser.add_argument("--debug", "-d", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--yes", "-y", action="store_true")
    parser.add_argument("--standalone", action="store_true",
                        help="Forcer le mode historique sans demon")
    args, unknown = parser.parse_known_args()

    # Reconstituer les argv a transmettre au standalone (sans --standalone)
    passthrough = [a for a in sys.argv[1:] if a not in ("--standalone", "--rag-enhanced")]

    one_shot = args.request is not None
    daemon_capable = (
        not args.standalone and not args.vocal and not args.check
        and not args.debug and not unknown and args.config == "config.yaml"
    )

    if daemon_capable and one_shot:
        code = run_oneshot_via_daemon(args.request, args)
        if code >= 0:
            return code
        print("  [!] Demon indisponible, bascule en mode standalone (plus lent)",
              file=sys.stderr)
    elif daemon_capable and not one_shot:
        # REPL interactif branche sur le demon (vocal reste standalone)
        from lyra.client.repl import run_repl
        code = run_repl(args)
        if code >= 0:
            return code
        print("  [!] Demon indisponible, bascule en mode standalone (plus lent)",
              file=sys.stderr)

    _exec_standalone(passthrough)
    return 1  # jamais atteint (execv)


if __name__ == "__main__":
    sys.path.insert(0, str(REPO_ROOT))
    os.chdir(REPO_ROOT)
    sys.exit(main())
