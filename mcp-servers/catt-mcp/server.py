#!/usr/bin/env python3
"""
MCP Server pour catt - Cast vers TV Philips/Chromecast.

Ce serveur expose les commandes catt via le protocole MCP pour
permettre a Lyra de caster des videos YouTube et autres contenus
vers la TV Philips via Chromecast/DLNA.

Usage:
    python server.py

Configuration:
    Les settings sont lus depuis config.yaml:
    - catt.device: Nom du device (ex: "55OLED705/12")
"""

import asyncio
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

try:
    import lz4.block
    HAS_LZ4 = True
except ImportError:
    HAS_LZ4 = False

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent
except ImportError:
    print("Error: mcp package not installed. Run: pip install mcp", file=sys.stderr)
    sys.exit(1)


def load_config() -> dict:
    """Charge la configuration depuis config.yaml."""
    config = {
        "device": os.environ.get("CATT_DEVICE", "55OLED705/12"),
        "tv_host": os.environ.get("TV_HOST", "192.168.1.50"),
        "adb_path": "/tmp/platform-tools/adb",
    }

    # Essayer de charger depuis config.yaml de Lyra
    config_path = Path(__file__).parent.parent.parent / "config.yaml"
    if config_path.exists():
        try:
            import yaml
            with open(config_path) as f:
                cfg = yaml.safe_load(f)
            catt_cfg = cfg.get("catt", {})
            config["device"] = catt_cfg.get("device", config["device"])
            # Recuperer l'IP de la TV pour ADB
            tv_cfg = cfg.get("tv", {})
            config["tv_host"] = tv_cfg.get("host", config["tv_host"])
        except Exception as e:
            print(f"Warning: Could not load config.yaml: {e}", file=sys.stderr)

    return config


class CattController:
    """Controleur pour catt - Cast vers Chromecast/DLNA."""

    def __init__(self, device: str, tv_host: str = "192.168.1.50", adb_path: str = "/tmp/platform-tools/adb"):
        self.device = device
        self.tv_host = tv_host
        self.adb_path = adb_path
        self.catt_path = shutil.which("catt") or os.path.expanduser("~/.local/bin/catt")

    def _run_catt(self, *args, timeout: int = 30) -> tuple[bool, str]:
        """Execute une commande catt."""
        if not os.path.exists(self.catt_path):
            return False, "Erreur: catt non installe"

        cmd = [self.catt_path, "-d", self.device] + list(args)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )

            output = result.stdout.strip()
            error = result.stderr.strip()

            if result.returncode == 0:
                return True, output or error or "OK"
            else:
                return False, error or output or f"Code retour: {result.returncode}"

        except subprocess.TimeoutExpired:
            return False, "Timeout"
        except Exception as e:
            return False, str(e)

    def _extract_video_id(self, url: str) -> Optional[str]:
        """Extrait l'ID YouTube d'une URL."""
        patterns = [
            r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)([a-zA-Z0-9_-]{11})',
            r'^([a-zA-Z0-9_-]{11})$'
        ]

        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def _youtube_via_adb(self, url: str, start_time: int = 0) -> tuple[bool, str]:
        """Lance YouTube via ADB (utilise le compte Premium connecte sur la TV).

        Args:
            url: URL YouTube ou ID de video
            start_time: Position de depart en secondes (0 = debut)
        """
        if not os.path.exists(self.adb_path):
            return False, "ADB non disponible"

        # Valider et extraire l'ID - toujours obligatoire pour eviter l'injection ADB
        video_id = self._extract_video_id(url)
        if not video_id:
            return False, f"URL YouTube invalide ou non reconnue: {url[:80]!r}"

        safe_url = f"https://www.youtube.com/watch?v={video_id}"
        if start_time > 0:
            safe_url += f"&t={int(start_time)}"

        try:
            # Connecter a la TV via ADB
            subprocess.run(
                [self.adb_path, "connect", f"{self.tv_host}:5555"],
                capture_output=True,
                timeout=10
            )

            # Lancer YouTube avec des arguments separes (pas de shell=True)
            result = subprocess.run(
                [self.adb_path, "-s", f"{self.tv_host}:5555", "shell",
                 "am", "start", "-a", "android.intent.action.VIEW",
                 "-d", safe_url, "com.google.android.youtube.tv"],
                capture_output=True,
                text=True,
                timeout=15
            )

            if result.returncode == 0:
                pos_str = f" @{start_time}s" if start_time > 0 else ""
                return True, f"YouTube Premium: {video_id}{pos_str}"
            else:
                error = result.stderr or result.stdout
                return False, error[:100]

        except subprocess.TimeoutExpired:
            return False, "Timeout ADB"
        except Exception as e:
            return False, str(e)

    def cast_youtube(self, url: str, use_premium: bool = True) -> str:
        """Caste une video YouTube sur la TV.

        Args:
            url: URL YouTube ou ID de video
            use_premium: Si True, utilise ADB pour beneficier de YouTube Premium (pas de pubs)
        """
        # Essayer d'abord via ADB pour YouTube Premium (pas de pubs)
        if use_premium:
            success, output = self._youtube_via_adb(url)
            if success:
                return output

        # Fallback sur catt (avec pubs)
        video_id = self._extract_video_id(url)
        if video_id:
            url = f"https://www.youtube.com/watch?v={video_id}"

        success, output = self._run_catt("cast", url, timeout=60)

        if success:
            title_match = re.search(r'Playing "([^"]+)"', output)
            if title_match:
                return f"Lecture (Cast): {title_match.group(1)}"
            return f"Cast demarre: {video_id or url}"
        else:
            return f"Erreur: {output}"

    _ALLOWED_SCHEMES = ("https://", "http://")
    _BLOCKED_HOSTS = ("localhost", "127.", "0.", "::1", "192.168.", "10.", "172.16.", "172.17.",
                      "172.18.", "172.19.", "172.20.", "172.21.", "172.22.", "172.23.", "172.24.",
                      "172.25.", "172.26.", "172.27.", "172.28.", "172.29.", "172.30.", "172.31.",
                      "169.254.", "metadata.", "metadata.google")

    def _validate_cast_url(self, url: str) -> Optional[str]:
        """Valide une URL de cast. Retourne un message d'erreur ou None si OK."""
        from urllib.parse import urlparse
        if not any(url.startswith(s) for s in self._ALLOWED_SCHEMES):
            return f"Scheme non autorise. Utiliser http:// ou https://"
        try:
            host = urlparse(url).hostname or ""
        except Exception:
            return "URL malformee"
        if any(host.startswith(b) for b in self._BLOCKED_HOSTS):
            return f"Host bloque: {host}"
        return None

    def cast_url(self, url: str) -> str:
        """Caste une URL (video, audio, etc.) sur la TV."""
        err = self._validate_cast_url(url)
        if err:
            return f"URL refusee: {err}"
        success, output = self._run_catt("cast", url, timeout=60)

        if success:
            return f"Cast demarre: {url[:50]}..."
        else:
            return f"Erreur: {output}"

    def cast_stop(self) -> str:
        """Arrete le cast en cours."""
        success, output = self._run_catt("stop")

        if success:
            return "Cast arrete"
        else:
            return f"Erreur: {output}"

    def cast_pause(self) -> str:
        """Met en pause le cast."""
        success, output = self._run_catt("pause")

        if success:
            return "Pause"
        else:
            return f"Erreur: {output}"

    def cast_resume(self) -> str:
        """Reprend le cast."""
        success, output = self._run_catt("play")

        if success:
            return "Lecture"
        else:
            return f"Erreur: {output}"

    def cast_volume(self, level: int) -> str:
        """Regle le volume du cast (0-100)."""
        level = max(0, min(100, level))
        success, output = self._run_catt("volume", str(level))

        if success:
            return f"Volume: {level}"
        else:
            return f"Erreur: {output}"

    def cast_seek(self, seconds: int) -> str:
        """Avance ou recule dans la video (en secondes, negatif pour reculer)."""
        if seconds >= 0:
            success, output = self._run_catt("seek", str(seconds))
        else:
            success, output = self._run_catt("rewind", str(abs(seconds)))

        if success:
            direction = "Avance" if seconds >= 0 else "Recul"
            return f"{direction} de {abs(seconds)}s"
        else:
            return f"Erreur: {output}"

    def cast_status(self) -> str:
        """Retourne le statut du cast en cours."""
        success, output = self._run_catt("status")

        if success:
            return output or "Aucun cast en cours"
        else:
            # "No media" n'est pas une erreur, juste pas de cast
            if "No media" in output or "Idle" in output:
                return "Aucun cast en cours"
            return f"Erreur: {output}"

    def cast_scan(self) -> str:
        """Scanne les devices disponibles."""
        cmd = [self.catt_path, "scan"]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=15
            )

            if result.returncode == 0:
                output = result.stdout.strip()
                if output:
                    lines = output.split("\n")
                    # Filtrer la ligne "Scanning..."
                    devices = [l for l in lines if l and "Scanning" not in l]
                    if devices:
                        return "Devices:\n" + "\n".join(devices)
                return "Aucun device trouve"
            else:
                return f"Erreur: {result.stderr.strip()}"

        except subprocess.TimeoutExpired:
            return "Timeout pendant le scan"
        except Exception as e:
            return f"Erreur: {e}"

    def cast_info(self) -> str:
        """Retourne les infos du media en cours."""
        success, output = self._run_catt("info")

        if success:
            return output or "Aucune info disponible"
        else:
            return f"Erreur: {output}"

    def _get_firefox_window_title(self) -> Optional[str]:
        """Recupere le titre de la fenetre Firefox via Hyprland."""
        try:
            result = subprocess.run(
                ["hyprctl", "clients", "-j"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode != 0:
                return None

            clients = json.loads(result.stdout)
            for client in clients:
                if 'firefox' in client.get('class', '').lower():
                    title = client.get('title', '')
                    # Enlever le suffixe " — Mozilla Firefox"
                    if ' — Mozilla Firefox' in title:
                        title = title.replace(' — Mozilla Firefox', '')
                    elif ' - Mozilla Firefox' in title:
                        title = title.replace(' - Mozilla Firefox', '')
                    return title
            return None
        except Exception:
            return None

    def _get_firefox_active_url(self) -> tuple[Optional[str], Optional[str]]:
        """Recupere l'URL et le titre de l'onglet actif de Firefox.

        Utilise le titre de la fenetre Hyprland pour matcher avec les onglets
        dans le fichier de session Firefox (plus fiable que l'index selected).

        Retourne (url, title) ou (None, error_message).
        """
        if not HAS_LZ4:
            return None, "Module lz4 non installe (pip install lz4)"

        # Recuperer le titre de la fenetre Firefox via Hyprland
        window_title = self._get_firefox_window_title()

        # Trouver le fichier de session Firefox
        home = os.path.expanduser("~")
        patterns = [
            f"{home}/.mozilla/firefox/*.default-release/sessionstore-backups/recovery.jsonlz4",
            f"{home}/.mozilla/firefox/*.default/sessionstore-backups/recovery.jsonlz4",
        ]

        recovery_file = None
        for pattern in patterns:
            matches = glob.glob(pattern)
            if matches:
                recovery_file = matches[0]
                break

        if not recovery_file:
            return None, "Fichier de session Firefox non trouve"

        try:
            # Lire le fichier jsonlz4 (header Mozilla: "mozLz40\0" + data)
            with open(recovery_file, 'rb') as f:
                magic = f.read(8)
                if magic[:8] != b'mozLz40\0':
                    return None, "Format de fichier Firefox invalide"
                compressed = f.read()

            # Decompresser
            data = lz4.block.decompress(compressed)
            session = json.loads(data)

            # Si on a le titre de la fenetre, chercher l'onglet correspondant
            if window_title:
                for window in session.get('windows', []):
                    for tab in window.get('tabs', []):
                        entries = tab.get('entries', [])
                        if entries:
                            current_entry = entries[-1]
                            tab_title = current_entry.get('title', '')
                            url = current_entry.get('url', '')
                            # Ignorer les titres vides et les pages internes
                            if not tab_title or url.startswith('about:'):
                                continue
                            # Matcher le titre (peut avoir des prefixes comme "(17) ")
                            if window_title in tab_title or tab_title in window_title:
                                return url, tab_title

            # Fallback: utiliser l'onglet marque comme selectionne
            for window in session.get('windows', []):
                selected_tab_index = window.get('selected', 1) - 1
                tabs = window.get('tabs', [])
                if 0 <= selected_tab_index < len(tabs):
                    tab = tabs[selected_tab_index]
                    entries = tab.get('entries', [])
                    if entries:
                        current_entry = entries[-1]
                        url = current_entry.get('url', '')
                        title = current_entry.get('title', '')
                        return url, title

            return None, "Aucun onglet actif trouve"

        except Exception as e:
            return None, f"Erreur lecture session Firefox: {e}"

    def cast_browser(self) -> str:
        """Caste la video de l'onglet actif de Firefox sur la TV."""
        url, title_or_error = self._get_firefox_active_url()

        if url is None:
            return f"Erreur: {title_or_error}"

        # Verifier si c'est une URL YouTube
        if 'youtube.com' in url or 'youtu.be' in url:
            result = self.cast_youtube(url)
            return f"{result} (depuis Firefox: {title_or_error[:50]}...)" if title_or_error else result

        # Verifier si c'est une URL video/stream connue
        video_domains = ['twitch.tv', 'vimeo.com', 'dailymotion.com', 'netflix.com']
        is_video = any(domain in url for domain in video_domains)

        if is_video or url.endswith(('.mp4', '.webm', '.m3u8')):
            return self.cast_url(url)

        # Pour les autres URLs, tenter quand meme
        return self.cast_url(url)

    # =========================================================================
    # Dual Cast (PC + TV synchronise) pour LightBeat
    # =========================================================================

    def _tv_media_control(self, action: str) -> bool:
        """Controle media sur la TV via ADB keycodes.

        Actions: 'pause', 'play', 'play_pause'
        """
        if not os.path.exists(self.adb_path):
            return False

        keycodes = {
            'pause': '127',        # KEYCODE_MEDIA_PAUSE
            'play': '126',         # KEYCODE_MEDIA_PLAY
            'play_pause': '85',    # KEYCODE_MEDIA_PLAY_PAUSE
            'stop': '86',          # KEYCODE_MEDIA_STOP
        }

        keycode = keycodes.get(action)
        if not keycode:
            return False

        try:
            result = subprocess.run(
                [self.adb_path, "-s", f"{self.tv_host}:5555", "shell", "input", "keyevent", keycode],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False

    def _firefox_media_control(self, action: str) -> bool:
        """Controle media sur Firefox via playerctl.

        Actions: 'pause', 'play', 'play_pause'
        """
        playerctl = shutil.which("playerctl")
        if not playerctl:
            return False

        try:
            result = subprocess.run(
                [playerctl, "-p", "firefox", action],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False

    def _firefox_get_status(self) -> tuple[Optional[str], Optional[float]]:
        """Recupere le status et la position de Firefox.

        Retourne (status, position_seconds) ou (None, None).
        Status: 'Playing', 'Paused', 'Stopped'
        """
        playerctl = shutil.which("playerctl")
        if not playerctl:
            return None, None

        try:
            # Status
            status_result = subprocess.run(
                [playerctl, "-p", "firefox", "status"],
                capture_output=True,
                text=True,
                timeout=5
            )
            status = status_result.stdout.strip() if status_result.returncode == 0 else None

            # Position (en microsecondes)
            pos_result = subprocess.run(
                [playerctl, "-p", "firefox", "position"],
                capture_output=True,
                text=True,
                timeout=5
            )
            position = None
            if pos_result.returncode == 0:
                try:
                    # playerctl retourne la position en secondes (float)
                    position = float(pos_result.stdout.strip())
                except ValueError:
                    pass

            return status, position
        except Exception:
            return None, None

    def _firefox_seek(self, position: float) -> bool:
        """Seek Firefox a une position donnee (en secondes)."""
        playerctl = shutil.which("playerctl")
        if not playerctl:
            return False

        try:
            result = subprocess.run(
                [playerctl, "-p", "firefox", "position", str(position)],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False

    def _firefox_open_url(self, url: str) -> bool:
        """Ouvre une URL dans Firefox."""
        try:
            subprocess.Popen(
                ["firefox", "--new-tab", url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            return True
        except Exception:
            return False

    def _get_firefox_url_playerctl(self) -> Optional[str]:
        """Recupere l'URL de Firefox via playerctl (temps reel)."""
        try:
            result = subprocess.run(
                ["playerctl", "-p", "firefox", "metadata", "xesam:url"],
                capture_output=True, text=True, timeout=5
            )
            return result.stdout.strip() if result.returncode == 0 else None
        except Exception:
            return None

    def _get_firefox_title_playerctl(self) -> Optional[str]:
        """Recupere le titre de Firefox via playerctl (temps reel)."""
        try:
            result = subprocess.run(
                ["playerctl", "-p", "firefox", "metadata", "xesam:title"],
                capture_output=True, text=True, timeout=5
            )
            return result.stdout.strip() if result.returncode == 0 else None
        except Exception:
            return None

    def cast_browser_dual(self) -> str:
        """Lance la video sur PC (Firefox) ET TV simultanement avec synchronisation.

        Workflow:
        1. Recuperer l'URL via playerctl (temps reel)
        2. Lancer sur TV via ADB a la meme position
        3. Demarrer le watcher pour sync bidirectionnelle
        """
        log = []

        # 1. Recuperer l'URL et titre via playerctl (temps reel)
        url = self._get_firefox_url_playerctl()
        title = self._get_firefox_title_playerctl()

        log.append(f"Fenetre: {title[:50] if title else 'N/A'}...")

        if not url:
            return "Erreur: Aucune video en cours sur Firefox (playerctl)"

        if 'youtube.com' not in url and 'youtu.be' not in url:
            return "Erreur: Dual cast supporte uniquement YouTube pour l'instant"

        video_id = self._extract_video_id(url)
        if not video_id:
            return "Erreur: Impossible d'extraire l'ID de la video"

        # Recuperer la position actuelle de Firefox
        ff_status, ff_position = self._firefox_get_status()
        if ff_position is None:
            ff_position = 0

        log.append(f"Video: {title[:40]}...")
        log.append(f"Position Firefox: {int(ff_position)}s ({int(ff_position//60)}:{int(ff_position%60):02d})")

        # 2. Lancer sur TV via ADB a la meme position
        log.append(f"Lancement TV @{int(ff_position)}s...")
        success, tv_result = self._youtube_via_adb(url, start_time=int(ff_position))
        if not success:
            return f"Erreur TV: {tv_result}"
        log.append(f"TV: {tv_result}")

        # 3. Demarrer le watcher pour sync bidirectionnelle
        log.append("Demarrage watcher sync...")
        watcher_result = self._start_sync_watcher(video_id)
        log.append(watcher_result)

        return "Dual Cast lance!\n" + "\n".join(log)

    def _start_sync_watcher(self, video_id: str, offset: float = 3.3) -> str:
        """Demarre le watcher de synchronisation en background."""
        watcher_script = Path(__file__).parent / "sync_watcher.py"

        # Toujours recreer le script (pour avoir la derniere version)
        self._create_sync_watcher_script(watcher_script)

        # Arreter l'ancien watcher s'il existe
        self._stop_sync_watcher()

        try:
            # Lancer le watcher en background avec l'offset
            log_file = open("/tmp/sync_watcher.log", "w")
            process = subprocess.Popen(
                ["python3", str(watcher_script), self.tv_host, self.adb_path, video_id, str(offset)],
                stdout=log_file,
                stderr=log_file,
                start_new_session=True
            )

            # Sauvegarder le PID
            pid_file = Path(__file__).parent / ".sync_watcher.pid"
            pid_file.write_text(str(process.pid))

            return f"Watcher demarre (PID: {process.pid}, offset: {offset}s)"
        except Exception as e:
            return f"Erreur watcher: {e}"

    def _stop_sync_watcher(self) -> str:
        """Arrete le watcher de synchronisation."""
        pid_file = Path(__file__).parent / ".sync_watcher.pid"

        if pid_file.exists():
            try:
                pid = int(pid_file.read_text().strip())
                os.kill(pid, 9)  # SIGKILL
                pid_file.unlink()
                return f"Watcher arrete (PID: {pid})"
            except (ProcessLookupError, ValueError):
                pid_file.unlink()
                return "Watcher deja arrete"
            except Exception as e:
                return f"Erreur arret watcher: {e}"
        return "Pas de watcher actif"

    def _create_sync_watcher_script(self, script_path: Path):
        """Cree le script de synchronisation."""
        script_content = '''#!/usr/bin/env python3
"""
Sync Watcher - Synchronise Firefox et TV YouTube avec precision <0.3s.

Methode "Pause-Play calibre":
- Les deux sont mis en pause
- Play TV, attendre delai calibre, Play Firefox
- Le delai compense la latence ADB
"""

import glob
import json
import os
import re
import subprocess
import sys
import time

try:
    import lz4.block
    HAS_LZ4 = True
except ImportError:
    HAS_LZ4 = False

TV_HOST = sys.argv[1] if len(sys.argv) > 1 else "192.168.1.50"
ADB_PATH = sys.argv[2] if len(sys.argv) > 2 else "/tmp/platform-tools/adb"
VIDEO_ID = sys.argv[3] if len(sys.argv) > 3 else ""
OFFSET = float(sys.argv[4]) if len(sys.argv) > 4 else 3.3

# Seuil pour detecter un seek (en secondes) - reduit pour capter les fleches
SEEK_THRESHOLD = 1.5

# Delai de latence ADB calibre (ajuster si PC en avance/retard)
# Augmenter si PC en avance, diminuer si PC en retard
TV_LATENCY = 1.2  # 1200ms (calibre pour TV Philips)

# Delai de chargement TV apres relancement
TV_LOAD_DELAY = 4.0

# Toujours resync au play apres pause
RESYNC_ON_PLAY = True

def tv_control(action):
    """Controle media TV via ADB."""
    # Note: Sur certaines TV Philips, les keycodes peuvent etre inverses
    # On utilise play_pause (85) qui toggle, plus fiable
    keycodes = {
        'pause': '85',      # KEYCODE_MEDIA_PLAY_PAUSE - toggle
        'play': '85',       # KEYCODE_MEDIA_PLAY_PAUSE - toggle
        'play_pause': '85'  # KEYCODE_MEDIA_PLAY_PAUSE
    }
    keycode = keycodes.get(action)
    if not keycode:
        return False
    try:
        subprocess.run(
            [ADB_PATH, "-s", f"{TV_HOST}:5555", "shell", "input", "keyevent", keycode],
            capture_output=True, timeout=5
        )
        return True
    except:
        return False

def tv_launch_at_position(video_id, position):
    """Relance la TV a une position donnee."""
    url = f"https://www.youtube.com/watch?v={video_id}&t={int(position)}"
    try:
        subprocess.run(
            [ADB_PATH, "-s", f"{TV_HOST}:5555", "shell",
             f"am start -a android.intent.action.VIEW -d \\'{url}\\' com.google.android.youtube.tv"],
            capture_output=True, timeout=15
        )
        return True
    except:
        return False

def get_firefox_status():
    """Retourne (status, position) de Firefox."""
    try:
        status = subprocess.run(
            ["playerctl", "-p", "firefox", "status"],
            capture_output=True, text=True, timeout=5
        ).stdout.strip()

        pos = subprocess.run(
            ["playerctl", "-p", "firefox", "position"],
            capture_output=True, text=True, timeout=5
        ).stdout.strip()

        return status, float(pos) if pos else 0
    except:
        return None, 0

def get_firefox_window_title():
    """Recupere le titre de la fenetre Firefox via Hyprland."""
    try:
        result = subprocess.run(
            ["hyprctl", "clients", "-j"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            return None
        import json
        clients = json.loads(result.stdout)
        for client in clients:
            if 'firefox' in client.get('class', '').lower():
                title = client.get('title', '')
                # Nettoyer le suffixe Firefox
                for suffix in [' — Mozilla Firefox', ' - Mozilla Firefox']:
                    if title.endswith(suffix):
                        title = title[:-len(suffix)]
                        break
                return title
        return None
    except:
        return None

def get_youtube_video_id():
    """Recupere l'ID de la video YouTube via playerctl (temps reel)."""
    try:
        result = subprocess.run(
            ["playerctl", "-p", "firefox", "metadata", "xesam:url"],
            capture_output=True, text=True, timeout=5
        )
        url = result.stdout.strip()
        if not url:
            return None

        # Extraire l'ID de l'URL YouTube
        match = re.search(r'(?:youtube\\.com/watch\\?v=|youtu\\.be/|youtube\\.com/shorts/)([a-zA-Z0-9_-]{11})', url)
        if match:
            return match.group(1)
        return None
    except Exception:
        return None

def firefox_control(action):
    """Controle Firefox via playerctl."""
    try:
        subprocess.run(
            ["playerctl", "-p", "firefox", action],
            capture_output=True, timeout=5
        )
        return True
    except:
        return False

def firefox_seek(position):
    """Seek Firefox a une position donnee."""
    try:
        subprocess.run(
            ["playerctl", "-p", "firefox", "position", str(position)],
            capture_output=True, timeout=5
        )
        return True
    except:
        return False

def sync_play():
    """Synchronise le play des deux avec compensation de latence."""
    print("-> Sync Play: TV...", file=sys.stderr)
    tv_control('play')
    time.sleep(TV_LATENCY)
    print(f"-> Sync Play: Firefox (apres {TV_LATENCY*1000:.0f}ms)", file=sys.stderr)
    firefox_control('play')

def sync_pause():
    """Met en pause les deux."""
    print("-> Sync Pause: Firefox...", file=sys.stderr)
    firefox_control('pause')
    print("-> Sync Pause: TV...", file=sys.stderr)
    tv_control('pause')
    time.sleep(0.3)  # Attendre que les deux soient stables

def resync_after_seek(video_id, target_position):
    """Resync complet apres un seek."""
    print(f"=== RESYNC @{target_position:.1f}s ===", file=sys.stderr)

    # 1. Pause Firefox
    print("1. Pause Firefox", file=sys.stderr)
    firefox_control('pause')

    # 2. Relancer TV a la position cible
    print(f"2. Relance TV @{target_position:.1f}s", file=sys.stderr)
    tv_launch_at_position(video_id, target_position)

    # 3. Attendre chargement TV
    print(f"3. Attente chargement TV ({TV_LOAD_DELAY}s)...", file=sys.stderr)
    time.sleep(TV_LOAD_DELAY)

    # 4. Pause TV (elle joue apres chargement)
    print("4. Pause TV", file=sys.stderr)
    tv_control('pause')
    time.sleep(0.3)

    # 5. Seek Firefox a la meme position + temps ecoule
    ff_position = target_position + TV_LOAD_DELAY
    print(f"5. Seek Firefox @{ff_position:.1f}s", file=sys.stderr)
    firefox_seek(ff_position)
    time.sleep(0.2)

    # 6. Play synchronise
    print("6. Play synchronise", file=sys.stderr)
    sync_play()

    print("=== RESYNC OK ===", file=sys.stderr)
    return ff_position

def main():
    global VIDEO_ID

    print(f"Sync Watcher v2 - Precision <0.3s", file=sys.stderr)
    print(f"TV: {TV_HOST}, Video: {VIDEO_ID}", file=sys.stderr)
    print(f"TV_LATENCY: {TV_LATENCY*1000:.0f}ms, SEEK_THRESHOLD: {SEEK_THRESHOLD}s", file=sys.stderr)

    last_status = None
    last_position = 0
    last_time = time.time()
    last_window_title = get_firefox_window_title()

    while True:
        try:
            current_time = time.time()
            status, position = get_firefox_status()
            elapsed = current_time - last_time

            # Detecter changement de video via titre de fenetre
            current_window_title = get_firefox_window_title()
            if current_window_title and last_window_title:
                if current_window_title != last_window_title and "YouTube" in current_window_title:
                    print(f"CHANGEMENT VIDEO detecte!", file=sys.stderr)
                    print(f"  Ancien: {last_window_title[:50]}", file=sys.stderr)
                    print(f"  Nouveau: {current_window_title[:50]}", file=sys.stderr)

                    # Attendre que la video demarre
                    print("  Attente demarrage (0.5s)...", file=sys.stderr)
                    time.sleep(0.5)

                    # Obtenir le nouvel ID via playerctl (temps reel)
                    new_video_id = get_youtube_video_id()
                    print(f"  playerctl ID: {new_video_id}", file=sys.stderr)

                    if new_video_id and new_video_id != VIDEO_ID:
                        VIDEO_ID = new_video_id
                        print(f"  -> Nouvel ID: {VIDEO_ID}", file=sys.stderr)
                    else:
                        print(f"  -> ID inchange: {VIDEO_ID}", file=sys.stderr)

                    # Position actuelle (sans toucher Firefox)
                    _, new_pos = get_firefox_status()
                    new_pos = new_pos if new_pos and new_pos > 0 else 0

                    # Lancer sur TV SANS resync (Firefox continue)
                    print(f"-> TV: nouvelle video @{new_pos:.1f}s", file=sys.stderr)
                    tv_launch_at_position(VIDEO_ID, new_pos)

                    last_position = new_pos
                    last_time = time.time()
                    last_status = status
                    last_window_title = current_window_title
                    continue
            last_window_title = current_window_title

            # Detecter un seek (changement de position anormal)
            if last_status == "Playing" and status == "Playing" and last_position > 0:
                expected_position = last_position + elapsed
                position_diff = abs(position - expected_position)

                if position_diff > SEEK_THRESHOLD:
                    print(f"SEEK detecte! {last_position:.1f}s -> {position:.1f}s", file=sys.stderr)
                    new_position = resync_after_seek(VIDEO_ID, position)
                    last_position = new_position
                    last_time = time.time()
                    last_status = "Playing"
                    continue

            # Detecter changement de status (pause/play)
            if status != last_status:
                print(f"Firefox: {last_status} -> {status} @{position:.1f}s", file=sys.stderr)

                if status == "Paused" and last_status == "Playing":
                    # Firefox pause -> pause TV
                    print("-> Pause TV", file=sys.stderr)
                    tv_control('pause')

                elif status == "Playing" and last_status == "Paused":
                    # Firefox play -> RESYNC COMPLET pour corriger tout decalage
                    if RESYNC_ON_PLAY:
                        print("-> Resync complet au play", file=sys.stderr)
                        # Pause Firefox le temps du resync
                        firefox_control('pause')
                        new_position = resync_after_seek(VIDEO_ID, position)
                        last_position = new_position
                        last_time = time.time()
                    else:
                        sync_play()

                last_status = status

            last_position = position
            last_time = current_time
            time.sleep(0.2)

        except KeyboardInterrupt:
            print("Watcher arrete", file=sys.stderr)
            break
        except Exception as e:
            print(f"Erreur: {e}", file=sys.stderr)
            time.sleep(1)

if __name__ == "__main__":
    main()
'''
        script_path.write_text(script_content)
        script_path.chmod(0o755)

    def cast_dual_resync(self) -> str:
        """Resynchronise PC et TV en relancant la TV a la position Firefox."""
        log = []

        # Recuperer la position Firefox
        ff_status, ff_position = self._firefox_get_status()
        if ff_position is None:
            return "Erreur: Impossible de lire la position Firefox"

        log.append(f"Position Firefox: {int(ff_position)}s")

        # Recuperer l'URL actuelle
        url, title = self._get_firefox_active_url()
        if url is None:
            return f"Erreur: {title}"

        video_id = self._extract_video_id(url)
        if not video_id:
            return "Erreur: Pas de video YouTube active"

        # Relancer TV a la position Firefox
        log.append(f"Relance TV @{int(ff_position)}s...")
        success, result = self._youtube_via_adb(url, start_time=int(ff_position))

        if success:
            log.append("Resync OK!")
        else:
            log.append(f"Erreur: {result}")

        return "\n".join(log)

    def cast_dual_stop(self) -> str:
        """Arrete le dual cast et le watcher de synchronisation."""
        log = []

        # Arreter le watcher
        result = self._stop_sync_watcher()
        log.append(result)

        # Pause Firefox
        self._firefox_media_control('pause')
        log.append("Firefox en pause")

        # Pause TV
        self._tv_media_control('pause')
        log.append("TV en pause")

        return "\n".join(log)

    def cast_dual_offset(self, offset: float) -> str:
        """Ajuste le decalage TV par rapport a Firefox.

        Args:
            offset: Decalage en secondes
                    Positif = TV en avance -> on recule la TV
                    Negatif = TV en retard -> on avance la TV

        Exemple:
            Si la TV est 2s en avance sur l'audio casque: offset=2
            Si la TV est 2s en retard sur l'audio casque: offset=-2
        """
        log = []

        # Recuperer la position Firefox
        ff_status, ff_position = self._firefox_get_status()
        if ff_position is None:
            return "Erreur: Impossible de lire la position Firefox"

        # Calculer la nouvelle position TV
        tv_position = ff_position - offset

        log.append(f"Firefox: {int(ff_position)}s")
        log.append(f"Offset: {offset:+.1f}s")
        log.append(f"Nouvelle position TV: {int(tv_position)}s")

        # Recuperer l'URL actuelle
        url, title = self._get_firefox_active_url()
        if url is None:
            return f"Erreur: {title}"

        video_id = self._extract_video_id(url)
        if not video_id:
            return "Erreur: Pas de video YouTube active"

        # Relancer TV a la position ajustee
        success, result = self._youtube_via_adb(url, start_time=max(0, int(tv_position)))

        if success:
            log.append("TV relancee avec offset!")
        else:
            log.append(f"Erreur: {result}")

        return "\n".join(log)


# Instance globale du serveur
app = Server("catt-mcp")
catt: CattController = None


@app.list_tools()
async def list_tools() -> list[Tool]:
    """Liste les outils disponibles."""
    return [
        Tool(
            name="cast_youtube",
            description="Caste une video YouTube sur la TV (URL ou ID de video)",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL YouTube (youtube.com/watch?v=xxx, youtu.be/xxx) ou ID de video"
                    }
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="cast_url",
            description="Caste une URL quelconque (video, audio, stream) sur la TV",
            inputSchema={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL du contenu a caster"
                    }
                },
                "required": ["url"]
            }
        ),
        Tool(
            name="cast_stop",
            description="Arrete le cast en cours sur la TV",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        Tool(
            name="cast_pause",
            description="Met en pause le cast en cours",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        Tool(
            name="cast_resume",
            description="Reprend la lecture du cast",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        Tool(
            name="cast_volume",
            description="Regle le volume du cast (0-100)",
            inputSchema={
                "type": "object",
                "properties": {
                    "level": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 100,
                        "description": "Niveau de volume (0-100)"
                    }
                },
                "required": ["level"]
            }
        ),
        Tool(
            name="cast_seek",
            description="Avance ou recule dans la video",
            inputSchema={
                "type": "object",
                "properties": {
                    "seconds": {
                        "type": "integer",
                        "description": "Secondes (positif = avancer, negatif = reculer)"
                    }
                },
                "required": ["seconds"]
            }
        ),
        Tool(
            name="cast_status",
            description="Retourne le statut du cast en cours",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        Tool(
            name="cast_scan",
            description="Scanne les devices Chromecast/DLNA disponibles sur le reseau",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        Tool(
            name="cast_info",
            description="Retourne les infos detaillees du media en cours",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        Tool(
            name="cast_browser",
            description="Caste la video de l'onglet actif de Firefox sur la TV (YouTube, Twitch, etc.)",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        Tool(
            name="cast_browser_dual",
            description="Lance la video sur PC (Firefox) ET TV simultanement avec synchronisation (pour LightBeat)",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        Tool(
            name="cast_dual_resync",
            description="Resynchronise PC et TV en relancant la TV a la position Firefox",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        Tool(
            name="cast_dual_stop",
            description="Arrete le dual cast et le watcher de synchronisation",
            inputSchema={"type": "object", "properties": {}, "required": []}
        ),
        Tool(
            name="cast_dual_offset",
            description="Ajuste le decalage TV (positif=TV en avance, negatif=TV en retard)",
            inputSchema={
                "type": "object",
                "properties": {
                    "offset": {
                        "type": "number",
                        "description": "Decalage en secondes (ex: 2 si TV en avance, -2 si TV en retard)"
                    }
                },
                "required": ["offset"]
            }
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Execute un outil."""
    global catt

    if catt is None:
        return [TextContent(type="text", text="Erreur: catt non configure")]

    try:
        if name == "cast_youtube":
            url = arguments.get("url", "")
            result = catt.cast_youtube(url)
        elif name == "cast_url":
            url = arguments.get("url", "")
            result = catt.cast_url(url)
        elif name == "cast_stop":
            result = catt.cast_stop()
        elif name == "cast_pause":
            result = catt.cast_pause()
        elif name == "cast_resume":
            result = catt.cast_resume()
        elif name == "cast_volume":
            level = arguments.get("level", 50)
            result = catt.cast_volume(level)
        elif name == "cast_seek":
            seconds = arguments.get("seconds", 0)
            result = catt.cast_seek(seconds)
        elif name == "cast_status":
            result = catt.cast_status()
        elif name == "cast_scan":
            result = catt.cast_scan()
        elif name == "cast_info":
            result = catt.cast_info()
        elif name == "cast_browser":
            result = catt.cast_browser()
        elif name == "cast_browser_dual":
            result = catt.cast_browser_dual()
        elif name == "cast_dual_resync":
            result = catt.cast_dual_resync()
        elif name == "cast_dual_stop":
            result = catt.cast_dual_stop()
        elif name == "cast_dual_offset":
            offset = arguments.get("offset", 0)
            result = catt.cast_dual_offset(offset)
        else:
            result = f"Outil inconnu: {name}"

        return [TextContent(type="text", text=result)]
    except Exception as e:
        return [TextContent(type="text", text=f"Erreur: {e}")]


async def main():
    """Point d'entree principal."""
    global catt

    # Charger la configuration
    config = load_config()

    catt = CattController(
        device=config["device"],
        tv_host=config["tv_host"],
        adb_path=config["adb_path"]
    )
    print(f"catt-mcp: Device: {config['device']}, TV: {config['tv_host']}", file=sys.stderr)

    # Demarrer le serveur MCP
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
