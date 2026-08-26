"""
Lyra Client - REPL interactif branche sur le demon.

Reprend l'experience de main_rag (banniere, live_input + bandeau de taches,
commandes internes, /setting) mais route les requetes vers le demon :
demarrage en <1s, pipeline deja chaud, session multi-tours cote demon.

Ce qui reste local au client : l'affichage, le bandeau de taches (lu depuis
le registre fichier partage ~/.lyra/active_tasks.json), les commandes
internes et la TUI /setting. Le vocal reste en mode standalone (phase
ulterieure du chantier demon).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from lyra.client.launcher import ensure_daemon
from lyra.client.render import answer_ask, render_output, render_progress
from lyra.daemon.protocol import ChannelClosed, LineChannel
from modules import ui

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _print_incomplete_integrations(cfg: dict) -> None:
    """Rappel des MCPs selectionnes a l'install mais restes incomplets
    (device injoignable, paquet casse...). Ecrit par installer/core/steps/
    config.py dans config.yaml (cle incomplete_integrations), jamais
    bloquant pour Lyra elle-meme."""
    incomplete = cfg.get("incomplete_integrations") or []
    if not incomplete:
        return
    print(f"{ui.Colors.YELLOW}[!] Integrations incompletes :{ui.Colors.RESET}")
    for item in incomplete:
        label = item.get("label", item.get("id", "?"))
        reason = item.get("reason", "raison inconnue")
        print(f"{ui.Colors.YELLOW}    - {label} : {reason}{ui.Colors.RESET}")
    print(f"{ui.Colors.YELLOW}    Cette partie ne fonctionnera pas tant que "
          f"non configuree. Relance ./installer/install.sh pour la "
          f"reconfigurer, ou complete config.yaml/secrets.yaml a la "
          f"main.{ui.Colors.RESET}")


def _print_banner() -> None:
    """Banniere v2 enhanced avec les noms de modeles (lecture yaml legere)."""
    try:
        import yaml
        with open(REPO_ROOT / "config.yaml") as f:
            cfg = yaml.safe_load(f)
        models = cfg.get("models", {})
        from main_rag import print_banner
        print_banner(mode="enhanced",
                     ephaistos_model=models.get("ephaistos", {}).get("name", "?"),
                     lyra_model=models.get("lyra", {}).get("name", "?"))
        _print_incomplete_integrations(cfg)
    except Exception:
        print(f"{ui.Colors.CYAN}LYRA (demon){ui.Colors.RESET}")


def _process_request(channel: LineChannel, text: str, mode: str,
                     verbose: bool) -> str:
    """Envoie une requete et deroule les messages jusqu'au result.

    Returns:
        "done"      : requete terminee, connexion propre et reutilisable
        "reconnect" : la connexion doit etre remplacee. C'est le cas apres
            TOUTE annulation : si on arretait de lire apres un cancel, le
            "result" tardif du demon resterait dans le tampon et serait lu
            comme premiere reponse de la requete SUIVANTE — toutes les
            requetes deviendraient silencieuses, decalees d'un cran
            (bug du 2026-08-11). Connexion neuve = flux garanti propre.
    """
    try:
        channel.send({
            "type": "request",
            "text": text,
            "options": {"mode": mode, "yes": False, "verbose": verbose,
                        "interactive": True},
        })
        while True:
            message = channel.recv(timeout=600)
            mtype = message.get("type")
            if mtype == "output":
                render_output(message)
            elif mtype == "progress":
                render_progress(message, verbose=verbose)
            elif mtype == "busy":
                ui.print_info(message.get("text", "Lyra est occupee..."))
            elif mtype == "ask":
                answer = answer_ask(message)
                if answer is None:
                    ui.print_warning("Annule.")
                    return "reconnect"
                channel.send({"type": "answer", "value": answer})
            elif mtype == "result":
                return "done"
            elif mtype == "error":
                ui.print_error(message.get("text", "erreur protocole"))
                return "done"
    except KeyboardInterrupt:
        print()
        ui.print_warning("Requete annulee.")
        return "reconnect"
    except (ChannelClosed, TimeoutError, ValueError) as e:
        ui.print_error(f"Connexion au demon perdue: {e}")
        return "reconnect"


def _connect(show_greeting: bool = True):
    """Connexion + hello. Retourne le channel pret, ou None si demon KO."""
    channel, greeting = ensure_daemon(on_wait=lambda: None)
    if greeting and show_greeting:
        ui.print_lyra(greeting)
    if channel is None:
        return None
    try:
        channel.send({"type": "hello", "session": "default", "client": "repl"})
        channel.recv(timeout=10)  # ready
        return channel
    except (ChannelClosed, TimeoutError, ValueError):
        channel.close()
        return None


def run_repl(args) -> int:
    """Boucle interactive cliente du demon."""
    from lyra.core.settings import UserSettings
    from lyra.core.settings_menu import SettingsCallbacks, SettingsMenu
    from lyra.hestia.background_tasks import BackgroundTaskManager

    user_settings = UserSettings()
    mode = "performance" if args.performance else user_settings.active_mode()

    _print_banner()

    channel, greeting = ensure_daemon(
        on_wait=lambda: None)
    if greeting:
        ui.print_lyra(greeting)
    if channel is None:
        return -1  # bascule standalone geree par l'appelant

    try:
        channel.send({"type": "hello", "session": "default", "client": "repl"})
        channel.recv(timeout=10)  # ready
        channel.send({"type": "health"})
        health = channel.recv(timeout=180).get("data", {})
        servers = health.get("mcp_servers", [])
        if servers:
            ui.print_success(f"MCP: {', '.join(servers)} ({len(servers)} serveurs)"
                             f" — demon pret (uptime {health.get('uptime_s', '?')}s)")
    except (ChannelClosed, TimeoutError, ValueError):
        return -1

    # Bandeau de taches : manager LOCAL alimente par le registre partage
    task_manager = BackgroundTaskManager()
    task_manager.restore_from_registry()

    def _set_mode(new_mode: str):
        nonlocal mode
        mode = new_mode

    settings_menu = SettingsMenu(
        settings=user_settings,
        models_dir=REPO_ROOT / "models",
        callbacks=SettingsCallbacks(get_mode=lambda: mode, set_mode=_set_mode),
    )

    last_interrupt = 0.0  # double Ctrl+C pour quitter

    while True:
        try:
            task_manager.restore_from_registry()  # taches lancees via le demon
            notifs = [n for n in task_manager.get_completed_notifications()
                      if n.get("success")]
            if notifs:
                ui.print_completed_task_notifications(notifs)
            task_manager.cleanup_completed(max_age_seconds=300)

            user_input = ui.live_input(">>> ", task_manager, mode=mode).strip()
            if not user_input:
                continue
            task_manager.clear_notifications()

            # Menu /setting ouvert : il consomme l'entree
            if settings_menu.active:
                ui.print_lyra(settings_menu.handle(user_input))
                continue

            cmd = user_input.lower().strip().lstrip("/")

            if cmd in ("setting", "settings", "reglages", "parametres"):
                if sys.stdin.isatty():
                    from lyra.core.settings_tui import run_settings_tui
                    run_settings_tui(settings_menu, println=ui.print_lyra)
                else:
                    ui.print_lyra(settings_menu.open())
                continue
            if cmd in ("quit", "stop", "exit", "q"):
                print("\nAu revoir!")
                return 0
            if cmd in ("clearscreen", "cls"):
                ui.clear_screen()
                continue
            if cmd == "mode":
                ui.print_info(f"Mode actuel: {mode}")
                continue
            if cmd == "mode performance":
                mode = "performance"
                ui.print_success("Mode performance active")
                continue
            if cmd in ("mode default", "mode normal"):
                mode = "default"
                ui.print_success("Mode default active")
                continue
            if cmd == "help":
                print("""
Commandes internes (avec ou sans prefixe "/"):
  quit, stop, exit  - Quitter Lyra
  clearscreen       - Effacer l'ecran
  /setting          - Reglages (voix TTS, vitesse, mode)
  mode [performance|default] - Mode actif
  help              - Cette aide
Le reste part au demon (pipeline chaud, session multi-tours conservee).
""")
                continue

            # Requete -> demon. Apres toute annulation ("reconnect"), on
            # remplace la connexion : un flux a moitie lu contaminerait
            # toutes les requetes suivantes (reponses decalees/silencieuses).
            status = _process_request(channel, user_input, mode, args.verbose)
            if status == "reconnect":
                channel.close()
                channel = _connect(show_greeting=False)
                if channel is None:
                    ui.print_error("Demon injoignable — relance lyra pour "
                                   "basculer en standalone.")
                    return 1

        except KeyboardInterrupt:
            # Double Ctrl+C (<1.5s) = quitter, comme le mode historique
            now = time.monotonic()
            if now - last_interrupt < 1.5:
                print("\nAu revoir!")
                return 0
            last_interrupt = now
            print()
            ui.print_info("Ctrl+C a nouveau pour quitter")
            continue
        except EOFError:
            print("\nAu revoir!")
            return 0
