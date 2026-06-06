"""
Lyra V1 - Interface Utilisateur

Gere l'affichage et les interactions utilisateur (confirmation, etc.).
"""

import sys
import os
import readline
import shutil
import threading
import time
from datetime import datetime
from typing import Optional
from dataclasses import dataclass
from pathlib import Path


# Etat du bandeau : None = auto (collapsed si >2 taches), True/False = force
_tasks_expanded: list = [None]


def _fmt_elapsed(seconds: int) -> str:
    """Formate un temps ecoule en string lisible (ex: 2m05s, 1h03m)."""
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    if s < 3600:
        return f"{s // 60}m{s % 60:02d}s"
    return f"{s // 3600}h{(s % 3600) // 60:02d}m"


def setup_readline():
    """Configure readline avec les raccourcis clavier."""
    # Bind Ctrl+L pour clear screen (fonction native readline)
    readline.parse_and_bind('"\\C-l": clear-screen')

# Couleurs ANSI
class Colors:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"

    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE = "\033[44m"
    BG_ORANGE = "\033[48;5;208m"
    FG_DARK = "\033[30m"


def colored(text: str, color: str) -> str:
    """Applique une couleur au texte."""
    return f"{color}{text}{Colors.RESET}"


def print_banner(mode="legacy"):
    """Affiche la banniere Lyra.

    Args:
        mode: "legacy" (V1 - défaut pour main.py), "v2", ou "enhanced"
    """
    if mode == "enhanced":
        title = "LYRA RAG ENHANCED v2.0"
        subtitle = "RAG + Slang + Synonym + Context"
    elif mode == "v2":
        title = "LYRA RAG v2.0"
        subtitle = "RAG + Dual Models"
    else:  # legacy
        title = "LYRA V1 (Legacy)"
        subtitle = "Human-in-the-Loop MCP"

    banner = f"""
    ╔═══════════════════════════════════════╗
    ║  {title:^37s}  ║
    ║  {subtitle:^37s}  ║
    ╚═══════════════════════════════════════╝
    """
    print(colored(banner, Colors.CYAN))


def print_info(message: str):
    """Affiche un message d'information."""
    print(colored(f"[i] {message}", Colors.BLUE))


def print_success(message: str):
    """Affiche un message de succes."""
    print(colored(f"[+] {message}", Colors.GREEN))


def print_error(message: str):
    """Affiche un message d'erreur."""
    print(colored(f"[!] {message}", Colors.RED))


def print_warning(message: str):
    """Affiche un avertissement."""
    print(colored(f"[!] {message}", Colors.YELLOW))


def format_value(value) -> str:
    """Formate une valeur pour l'affichage."""
    if isinstance(value, bool):
        return colored("oui" if value else "non", Colors.GREEN if value else Colors.RED)
    elif isinstance(value, (int, float)):
        return colored(str(value), Colors.MAGENTA)
    elif value is None:
        return colored("(vide)", Colors.DIM)
    else:
        return colored(str(value), Colors.WHITE)


def print_tool_call(tool_name: str, arguments: dict, vm_state: dict = None):
    """Affiche un appel d'outil propose."""
    print()
    print(colored("=" * 50, Colors.DIM))
    print(colored("  ACTION PROPOSEE", Colors.BOLD + Colors.YELLOW))
    print(colored("=" * 50, Colors.DIM))
    print()
    print(f"  {colored('Outil:', Colors.CYAN)} {colored(tool_name, Colors.BOLD + Colors.WHITE)}")

    if arguments:
        print(f"  {colored('Parametres:', Colors.CYAN)}")
        for key, value in arguments.items():
            print(f"    - {key}: {format_value(value)}")
    else:
        print(f"  {colored('Parametres:', Colors.CYAN)} (aucun)")

    # Afficher l'etat de la VM si disponible (Read-First)
    if vm_state:
        print()
        print(f"  {colored('Etat actuel:', Colors.CYAN)}")
        status_color = Colors.GREEN if vm_state.get("running") else Colors.RED
        status_text = "En cours d'execution" if vm_state.get("running") else "Arretee"
        print(f"    - Status: {colored(status_text, status_color)}")
        if vm_state.get("ip"):
            print(f"    - IP: {colored(vm_state['ip'], Colors.WHITE)}")

    print()
    print(colored("=" * 50, Colors.DIM))


def print_tool_result(result: str, success: bool = True):
    """Affiche le resultat d'un outil."""
    print()
    if success:
        print(colored("+" + "-" * 48 + "+", Colors.GREEN))
        print(colored("|  RESULTAT", Colors.GREEN))
        print(colored("+" + "-" * 48 + "+", Colors.GREEN))
    else:
        print(colored("+" + "-" * 48 + "+", Colors.RED))
        print(colored("|  ERREUR", Colors.RED))
        print(colored("+" + "-" * 48 + "+", Colors.RED))
    print()
    # Nettoyer les codes ANSI du resultat MCP pour eviter les conflits
    clean_result = result
    # Indenter le resultat pour meilleure lisibilite
    for line in clean_result.split('\n'):
        print(f"  {line}")
    print()


def print_lyra(message: str):
    """Affiche une reponse de Lyra."""
    print()
    print(f'  {message}')
    print()


def print_lyra_tag(message: str):
    """Affiche un message Lyra court avec tag orange (confirmations, questions)."""
    tag = f'{Colors.BG_ORANGE}{Colors.FG_DARK} Lyra {Colors.RESET}'
    print(f'\n{tag} {message}')


def print_assistant(message: str):
    """Affiche la reponse de l'assistant (V1 legacy)."""
    print_lyra(message)


def confirm_action(tool_name: str, arguments: dict, vocal_mode: bool = False, voice=None):
    """Demande confirmation pour executer une action.

    Args:
        tool_name: Nom de l'outil a executer
        arguments: Arguments de l'outil
        vocal_mode: Si True, accepte aussi la confirmation vocale
        voice: Instance VoiceInterface pour la confirmation vocale

    Returns:
        True si l'utilisateur confirme
        False si l'utilisateur annule
        "modify" si l'utilisateur veut modifier les arguments
    """
    # Importer depuis la source unique de verite
    try:
        sys.path.insert(0, str(Path(__file__).parent.parent))
        from lyra.core.constants import DANGEROUS_TOOLS as _DANGEROUS_TOOLS
    except ImportError:
        _DANGEROUS_TOOLS = frozenset({"vm_destroy", "vm_stop", "backup_restore", "backup_clean", "vm_clone_system"})

    is_dangerous = tool_name in _DANGEROUS_TOOLS

    if is_dangerous:
        print(colored("\n  ⚠️  ACTION POTENTIELLEMENT DESTRUCTIVE", Colors.BG_RED + Colors.WHITE + Colors.BOLD))

    # En mode vocal, proposer les deux options
    if vocal_mode:
        prompt = colored("\n  Confirmer ? [O/n/d/m/v] ", Colors.YELLOW)
        hint = colored("(O=oui, n=non, d=details, m=modifier, v=vocal)", Colors.DIM)
    else:
        prompt = colored("\n  Executer ? [O/n/d/m] ", Colors.YELLOW)
        hint = colored("(O=oui, n=non, d=details, m=modifier)", Colors.DIM)

    while True:
        try:
            response = input(f"{prompt}{hint} ").strip().lower()

            if response in ("", "o", "oui", "y", "yes"):
                return True
            elif response in ("n", "non", "no"):
                return False
            elif response in ("d", "details"):
                print_tool_details(tool_name)
            elif response in ("m", "modifier", "mod", "edit", "modif"):
                return "modify"
            elif response == "v" and vocal_mode and voice:
                # Confirmation vocale
                return _vocal_confirm(voice, is_dangerous)
            else:
                print_warning("Reponse non reconnue. Utilisez O, n, d ou m.")

        except (KeyboardInterrupt, EOFError):
            print()
            return False


def _vocal_confirm(voice, is_dangerous: bool = False) -> bool:
    """Demande une confirmation vocale.

    Args:
        voice: Instance VoiceInterface
        is_dangerous: Si True, demande une confirmation plus explicite

    Returns:
        True si l'utilisateur confirme vocalement, False sinon.
    """
    if is_dangerous:
        voice.speak("Cette action est potentiellement destructive. Dis 'oui je confirme' pour continuer, ou 'non' pour annuler.")
    else:
        voice.speak("Dis 'oui' pour confirmer ou 'non' pour annuler.")

    print(colored("  [En attente de confirmation vocale...]", Colors.DIM))

    try:
        response = voice.listen(with_beep=True)
        if response:
            response = response.lower().strip()
            print(f"  Entendu: \"{response}\"")

            # Mots cles de confirmation
            confirm_words = ["oui", "yes", "ok", "d'accord", "confirme", "vas-y", "go", "execute"]
            cancel_words = ["non", "no", "annule", "stop", "arrete", "cancel"]

            if any(word in response for word in confirm_words):
                # Pour les actions dangereuses, verifier "je confirme"
                if is_dangerous and "confirme" not in response:
                    print_warning("Pour une action destructive, dis 'oui je confirme'.")
                    return _vocal_confirm(voice, is_dangerous)
                return True
            elif any(word in response for word in cancel_words):
                return False
            else:
                print_warning("Je n'ai pas compris. Reponds par 'oui' ou 'non'.")
                return _vocal_confirm(voice, is_dangerous)
        else:
            print_warning("Aucune reponse detectee.")
            return False
    except Exception as e:
        print_error(f"Erreur de reconnaissance vocale: {e}")
        return False


def print_tool_details(tool_name: str):
    """Affiche les details d'un outil."""
    # Description detaillee des outils
    details = {
        "vm_status": "Lecture seule - Affiche l'etat des VMs (IP, SSH, ressources)",
        "vm_start": "Demarre une VM - Action reversible avec vm_stop",
        "vm_stop": "Arrete une VM - Les donnees non sauvegardees seront perdues",
        "vm_destroy": "SUPPRIME une VM - Action IRREVERSIBLE !",
        "vm_snapshot": "Gere les snapshots - create/list/restore/delete",
        "vm_exec": "Execute une commande dans la VM via SSH",
        "backup_status": "Lecture seule - Dashboard des backups",
        "backup_list": "Lecture seule - Liste les backups disponibles",
        "backup_create": "Cree un nouveau backup",
        "backup_restore": "RESTAURE un backup - Ecrase les donnees actuelles !",
        "backup_clean": "SUPPRIME les anciens backups selon la retention",
        "backup_verify": "Lecture seule - Verifie l'integrite des backups",
    }

    detail = details.get(tool_name, "Aucun detail disponible")
    print(colored(f"\n  Detail: {detail}\n", Colors.CYAN))


def get_user_input() -> str:
    """Recupere l'input utilisateur."""
    try:
        prompt = colored("\nToi: ", Colors.BOLD + Colors.GREEN)
        user_input = input(prompt)
        return user_input.strip()
    except (KeyboardInterrupt, EOFError):
        raise KeyboardInterrupt


def print_thinking():
    """Affiche un indicateur de reflexion."""
    print(colored("\n  Reflexion en cours...", Colors.DIM), end="", flush=True)


def clear_thinking():
    """Efface l'indicateur de reflexion."""
    print("\r" + " " * 30 + "\r", end="", flush=True)


def clear_screen():
    """Efface le terminal."""
    import os
    os.system('clear' if os.name != 'nt' else 'cls')


def print_help():
    """Affiche l'aide."""
    help_text = """
    Commandes disponibles:
    ----------------------
    help, ?        - Affiche cette aide
    clear, cls     - Efface l'historique de conversation
    clearscreen    - Efface le terminal
    quit, exit     - Quitte Lyra
    mode           - Affiche le mode actuel
    mode default   - Mode normal (confirmations)
    mode performance - Mode rapide (sans confirmations)

    Raccourcis clavier:
    -------------------
    Ctrl+L         - Efface le terminal
    Ctrl+C (2x)    - Quitte Lyra

    Exemples de commandes:
    ----------------------
    "liste mes VMs"
    "demarre la VM preprod"
    "quel est le status des backups ?"
    "cree un snapshot de preprod"
    "allume la TV"
    "lumieres en rouge"
    """
    print(colored(help_text, Colors.CYAN))


def beep_short(frequency: int = 880, duration: float = 0.05):
    """Joue un bip court pour feedback minimal (mode performance).

    Args:
        frequency: Frequence en Hz (defaut: 880 = La5)
        duration: Duree en secondes (defaut: 0.05s = 50ms)
    """
    try:
        import numpy as np
        import sounddevice as sd

        # Generer le bip
        sample_rate = 48000  # Compatible PipeWire
        t = np.linspace(0, duration, int(sample_rate * duration), False)
        wave = np.sin(2 * np.pi * frequency * t) * 0.3

        # Appliquer un fade pour eviter les clics
        fade_samples = int(sample_rate * 0.005)  # 5ms fade
        if fade_samples > 0 and len(wave) > fade_samples * 2:
            wave[:fade_samples] *= np.linspace(0, 1, fade_samples)
            wave[-fade_samples:] *= np.linspace(1, 0, fade_samples)

        # Utiliser OutputStream pour eviter les bugs de callback
        with sd.OutputStream(samplerate=sample_rate, channels=1, dtype='float32') as stream:
            stream.write(wave.astype(np.float32))
    except Exception:
        # Fallback: utiliser le terminal bell
        print("\a", end="", flush=True)


def print_mode_status(mode: str, performance_tools_count: int = 0):
    """Affiche le statut du mode actuel.

    Args:
        mode: Nom du mode ("default" ou "performance")
        performance_tools_count: Nombre d'outils en mode performance
    """
    if mode == "performance":
        print(colored(f"[i] Mode: {mode.upper()} - execution instantanee", Colors.MAGENTA))
        if performance_tools_count > 0:
            print(colored(f"    {performance_tools_count} outils domotique sans confirmation", Colors.DIM))
    else:
        print(colored(f"[i] Mode: {mode} - confirmations actives", Colors.BLUE))


def print_quick_result(tool_name: str, success: bool = True, use_beep: bool = True):
    """Affiche un resultat rapide pour le mode performance.

    Args:
        tool_name: Nom de l'outil execute
        success: True si succes, False si echec
        use_beep: Jouer un bip sonore
    """
    if success:
        # Affichage minimal
        short_name = tool_name.split(".")[-1] if "." in tool_name else tool_name
        print(colored(f"  OK: {short_name}", Colors.GREEN))
        if use_beep:
            beep_short(880, 0.05)  # Bip aigu = succes
    else:
        print(colored(f"  FAIL: {tool_name}", Colors.RED))
        if use_beep:
            beep_short(220, 0.1)  # Bip grave = echec


def _resolve_expanded(n_tasks: int) -> bool:
    """Retourne l'etat expanded resolue (auto ou force par l'utilisateur)."""
    if _tasks_expanded[0] is None:
        return n_tasks <= 2
    return _tasks_expanded[0]


def _build_banner_lines(active_tasks: list, task_manager=None, expanded: bool = True,
                         failed_tasks: list = None) -> list:
    """Construit les lignes du bandeau (sans les afficher).

    Args:
        active_tasks: Liste de BackgroundTask en cours
        task_manager: BackgroundTaskManager pour progression (optionnel)
        expanded: True = details complets, False = juste le compteur
        failed_tasks: Liste de BackgroundTask terminées en erreur (persistantes)

    Returns:
        Liste de chaines colorees representant le bandeau
    """
    failed_tasks = failed_tasks or []
    n_active = len(active_tasks)
    n_failed = len(failed_tasks)
    n_total = n_active + n_failed

    lines = []
    if not expanded:
        hints = [colored("  Ctrl+T: details", Colors.DIM)]
        if n_failed:
            hints.append(colored("  Ctrl+E: nettoyer erreurs", Colors.DIM))
        lines.append(colored("=" * 60, Colors.DIM))
        title = f"  Taches ({n_active} en cours"
        if n_failed:
            title += f", {n_failed} en erreur"
        title += ")"
        lines.append(colored(title, Colors.CYAN + Colors.BOLD) + "".join(hints))
        lines.append(colored("=" * 60, Colors.DIM))
        return lines

    lines.append(colored("=" * 60, Colors.DIM))
    hints = [colored("  Ctrl+T: reduire", Colors.DIM)]
    if n_failed:
        hints.append(colored("  Ctrl+E: nettoyer erreurs", Colors.DIM))
    title = f"  Taches ({n_active} en cours"
    if n_failed:
        title += f", {n_failed} en erreur"
    title += ")"
    lines.append(colored(title, Colors.CYAN + Colors.BOLD) + "".join(hints))
    lines.append(colored("=" * 60, Colors.DIM))

    for task in active_tasks:
        elapsed_s = int((datetime.now() - task.started_at).total_seconds())
        elapsed_str = _fmt_elapsed(elapsed_s)
        progress = task_manager.get_task_progress(task.task_id) if task_manager else None

        lines.append(
            colored(f"  [{task.task_id[-6:]}]", Colors.DIM) + " " +
            colored(task.description, Colors.WHITE) +
            colored(f"  ({elapsed_str})", Colors.DIM)
        )

        if progress and "percentage" in progress:
            pct = progress["percentage"]
            step = progress.get("step", 0)
            total = progress.get("total", 1)
            name = progress.get("name", "")
            gb_done = progress.get("gb_done", 0)
            gb_total = progress.get("gb_total", 0)

            bar_length = 25
            filled = int(bar_length * pct / 100)
            bar = "#" * filled + "-" * (bar_length - filled)

            step_str = f"Etape {step}/{total}: " if step and total else ""
            progress_line = f"  [{colored(bar, Colors.CYAN)}] {colored(f'{pct}%', Colors.GREEN)}  {step_str}{colored(name, Colors.YELLOW)}"
            lines.append(progress_line)

            if gb_total and gb_total > 0:
                lines.append(f"  {gb_done:.1f} Go / {gb_total:.1f} Go")
        else:
            lines.append(f"  {colored(f'(~{task.estimated_time})', Colors.YELLOW)}")

    for task in failed_tasks:
        elapsed_s = int((datetime.now() - task.started_at).total_seconds())
        elapsed_str = _fmt_elapsed(elapsed_s)
        err_msg = (task.error or "Echec").split('\n')[-1][:55]
        lines.append(
            colored(f"  [{task.task_id[-6:]}]", Colors.DIM) + " " +
            colored(f"[ERREUR] {task.description}", Colors.RED + Colors.BOLD) +
            colored(f"  ({elapsed_str})", Colors.DIM)
        )
        lines.append(colored(f"    {err_msg}", Colors.RED))

    lines.append(colored("=" * 60, Colors.DIM))
    return lines


def print_background_tasks(tasks: list, task_manager=None):
    """Affiche les taches en arriere-plan.

    Args:
        tasks: Liste de BackgroundTask en cours
        task_manager: BackgroundTaskManager pour progression (optionnel)
    """
    failed = getattr(task_manager, 'persistent_errors', []) if task_manager else []
    if not tasks and not failed:
        return

    print()
    for line in _build_banner_lines(tasks, task_manager,
                                     expanded=_resolve_expanded(len(tasks) + len(failed)),
                                     failed_tasks=failed):
        print(line)
    print()


def live_input(prompt: str, task_manager=None, loading: "threading.Event | None" = None) -> str:
    """Input colle en bas du terminal avec bandeau de taches optionnel.

    La barre d'input (separateur + fond bleu) est toujours dessinee aux deux
    dernieres lignes visibles du terminal via positionnement absolu ANSI.
    Gere le resize, Ctrl+L, et le plein ecran correctement.

    Args:
        prompt: Ignore (garde pour compatibilite), le prompt est toujours 'Lyra >> '
        task_manager: BackgroundTaskManager (optionnel)
        loading: Event set() quand le chargement est termine (optionnel)

    Returns:
        Ligne saisie par l'utilisateur
    """
    _CTRL_L_SENTINEL = '__lyra_ctrl_l__'
    _TOGGLE_SENTINEL = '__lyra_toggle_tasks__'
    _CLEAR_ERR_SENTINEL = '__lyra_clear_errors__'

    readline.parse_and_bind(r'"\C-l": "\C-a\C-k' + _CTRL_L_SENTINEL + r'\C-m"')
    readline.parse_and_bind(r'"\C-t": "\C-a\C-k' + _TOGGLE_SENTINEL + r'\C-m"')
    readline.parse_and_bind(r'"\C-e": "\C-a\C-k' + _CLEAR_ERR_SENTINEL + r'\C-m"')

    _STYLED_PROMPT = '\001\033[44;30m\002 Vous >> \001\033[0m\002'
    _HINT_NORMAL   = "  /help  Ctrl+C: quitte  "
    _HINT_LOADING  = "  chargement...  "

    def _get_failed():
        return getattr(task_manager, 'persistent_errors', []) if task_manager else []

    def _ts():
        t = shutil.get_terminal_size((80, 24))
        return t.lines, t.columns

    def _draw_footer(rows: int, cols: int, hint: str):
        """Dessine hint (rows-2) + separateur (rows-1) + barre bleue (rows)."""
        out = [
            f'\033[{rows - 2};1H\033[2K\033[2m{hint}\033[0m',
            f'\033[{rows - 1};1H\033[2K\033[2m{"-" * cols}\033[0m',
            f'\033[{rows};1H\033[2K\033[44;30m{" " * cols}\033[0m',
            f'\033[{rows};1H',
        ]
        sys.stdout.write(''.join(out))
        sys.stdout.flush()

    def _update_hint(rows: int, cols: int, hint: str):
        """Met a jour uniquement la zone hint sans perturber l'input en cours."""
        sys.stdout.write(
            f'\033[s\033[{rows - 2};1H\033[2K\033[2m{hint}\033[0m\033[u'
        )
        sys.stdout.flush()

    try:
        while True:
            rows, cols = _ts()
            tasks   = task_manager.get_active_tasks() if task_manager else []
            failed  = _get_failed()
            is_loading = loading is not None and not loading.is_set()

            # ----------------------------------------------------------------
            # Cas simple : pas de taches actives
            # ----------------------------------------------------------------
            if not tasks and not failed:
                hint = _HINT_LOADING if is_loading else _HINT_NORMAL
                _draw_footer(rows, cols, hint)

                if is_loading:
                    _chars = '|/-\\'
                    _i = [0]
                    _stop = threading.Event()

                    def _spinner(stop=_stop):
                        while not stop.wait(0.15):
                            r, c = _ts()
                            if loading is None or loading.is_set():
                                _update_hint(r, c, _HINT_NORMAL)
                                return
                            ch = _chars[_i[0] % len(_chars)]
                            _i[0] += 1
                            _update_hint(r, c, f"  {ch} chargement  ")
                        r, c = _ts()
                        _update_hint(r, c, _HINT_NORMAL)

                    _t = threading.Thread(target=_spinner, daemon=True)
                    _t.start()
                    try:
                        result = input(_STYLED_PROMPT).strip()
                    finally:
                        _stop.set()
                else:
                    result = input(_STYLED_PROMPT).strip()

                if result == _CTRL_L_SENTINEL:
                    sys.stdout.write('\033[2J\033[H')
                    sys.stdout.flush()
                    continue
                if result in (_TOGGLE_SENTINEL, _CLEAR_ERR_SENTINEL):
                    continue
                return result

            # ----------------------------------------------------------------
            # Cas avec taches actives : banner + footer fixes en bas
            # ----------------------------------------------------------------
            expanded     = _resolve_expanded(len(tasks) + len(failed))
            banner_lines = _build_banner_lines(tasks, task_manager, expanded=expanded,
                                               failed_tasks=failed)
            n_banner = len(banner_lines)

            # Dessiner le banner a position absolue au-dessus du footer
            # Banner occupe rows [rows-n-3 .. rows-3], hint=rows-2, sep=rows-1, bar=rows
            def _draw_banner(r: int, c: int, lines: list):
                out = []
                top = r - len(lines) - 3
                for i, line in enumerate(lines):
                    row = max(1, top + 1 + i)
                    out.append(f'\033[{row};1H\033[2K{line}')
                sys.stdout.write(''.join(out))

            _draw_banner(rows, cols, banner_lines)
            _draw_footer(rows, cols, _HINT_NORMAL)

            stop_event = threading.Event()

            def _refresh(n=n_banner):
                while not stop_event.wait(1.0):
                    r, c = _ts()
                    active = task_manager.get_active_tasks() if task_manager else []
                    errs   = _get_failed()

                    if not active and not errs:
                        # Effacer la zone banner (hint/sep redessines par _draw_footer)
                        out = ['\033[s']
                        for row in range(max(1, r - n - 3), r - 2):
                            out.append(f'\033[{row};1H\033[2K')
                        out.append('\033[u')
                        sys.stdout.write(''.join(out))
                        sys.stdout.flush()
                        return

                    exp       = _resolve_expanded(len(active) + len(errs))
                    new_lines = _build_banner_lines(active, task_manager,
                                                    expanded=exp, failed_tasks=errs)
                    m   = len(new_lines)
                    out = ['\033[s']
                    # Effacer la zone la plus large (ancienne ou nouvelle)
                    for row in range(max(1, r - max(n, m) - 3), r - 2):
                        out.append(f'\033[{row};1H\033[2K')
                    # Redessiner
                    top = r - m - 3
                    for i, line in enumerate(new_lines):
                        row = max(1, top + 1 + i)
                        out.append(f'\033[{row};1H{line}')
                    out.append('\033[u')
                    sys.stdout.write(''.join(out))
                    sys.stdout.flush()

            t = threading.Thread(target=_refresh, daemon=True)
            t.start()

            try:
                result = input(_STYLED_PROMPT).strip()
            finally:
                stop_event.set()

            if result == _CTRL_L_SENTINEL:
                sys.stdout.write('\033[2J\033[H')
                sys.stdout.flush()
                continue

            if result == _TOGGLE_SENTINEL:
                _tasks_expanded[0] = not _resolve_expanded(len(tasks) + len(failed))
                sys.stdout.write('\033[2J\033[H')
                sys.stdout.flush()
                continue

            if result == _CLEAR_ERR_SENTINEL:
                if task_manager and hasattr(task_manager, 'clear_errors'):
                    task_manager.clear_errors()
                sys.stdout.write('\033[2J\033[H')
                sys.stdout.flush()
                continue

            return result
    finally:
        readline.parse_and_bind(r'"\C-l": clear-screen')
        readline.parse_and_bind(r'"\C-t": self-insert')
        readline.parse_and_bind(r'"\C-e": self-insert')


def print_completed_task_notifications(notifications: list):
    """Affiche les notifications de taches terminees.

    Args:
        notifications: Liste de notifications de completion
    """
    if not notifications:
        return

    for notif in notifications:
        print()
        print(colored("=" * 60, Colors.DIM))

        if notif["success"]:
            print(colored(f"  [OK] Tache terminee: {notif['description']}", Colors.GREEN + Colors.BOLD))
        else:
            print(colored(f"  [!] Tache echouee: {notif['description']}", Colors.RED + Colors.BOLD))

        print(colored("=" * 60, Colors.DIM))

        # Arguments resume
        if notif["args_summary"]:
            print(f"  {notif['args_summary']}")

        print(f"  Duree: {notif['duration']}")

        if notif["success"]:
            result = notif.get("result") or ""
            if len(result) > 200:
                result = result[:200] + "..."
            if result:
                print(f"  Resultat: {result}")
        else:
            error = notif.get("result") or "Echec (aucun detail disponible)"
            if len(error) > 200:
                error = error[:200] + "..."
            print(colored(f"  Erreur: {error}", Colors.RED))

        print(colored("=" * 60, Colors.DIM))
        print()
