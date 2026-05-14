#!/usr/bin/env python3
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
             f"am start -a android.intent.action.VIEW -d \'{url}\' com.google.android.youtube.tv"],
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
        match = re.search(r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)([a-zA-Z0-9_-]{11})', url)
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
