#!/bin/bash
# cast-clipboard.sh - Caste l'URL du clipboard vers la TV
#
# Usage:
#   cast-clipboard.sh         # Caste sur le device par defaut
#   cast-clipboard.sh stop    # Arrete le cast
#   cast-clipboard.sh pause   # Met en pause
#   cast-clipboard.sh resume  # Reprend
#
# Configuration:
#   Raccourci Hyprland: bind = $mainMod, C, exec, ~/.local/bin/cast-clipboard.sh
#
# Prerequis:
#   - catt: pip install catt
#   - yt-dlp: pip install yt-dlp
#   - wl-clipboard: dnf install wl-clipboard
#   - libnotify: dnf install libnotify

DEVICE="55OLED705/12"
CATT="${HOME}/.local/bin/catt"

# Couleurs pour notifications
ICON_SUCCESS="video-x-generic"
ICON_ERROR="dialog-error"
ICON_INFO="dialog-information"

notify() {
    local title="$1"
    local message="$2"
    local icon="${3:-$ICON_INFO}"
    notify-send -i "$icon" -t 3000 "$title" "$message"
}

# Commandes speciales
case "$1" in
    stop)
        "$CATT" -d "$DEVICE" stop 2>/dev/null
        notify "Cast" "Arrete" "$ICON_INFO"
        exit 0
        ;;
    pause)
        "$CATT" -d "$DEVICE" pause 2>/dev/null
        notify "Cast" "Pause" "$ICON_INFO"
        exit 0
        ;;
    resume|play)
        "$CATT" -d "$DEVICE" play 2>/dev/null
        notify "Cast" "Lecture" "$ICON_INFO"
        exit 0
        ;;
    status)
        status=$("$CATT" -d "$DEVICE" status 2>&1)
        notify "Cast Status" "$status" "$ICON_INFO"
        exit 0
        ;;
esac

# Lire le clipboard
URL=$(wl-paste 2>/dev/null)

if [[ -z "$URL" ]]; then
    notify "Cast" "Clipboard vide" "$ICON_ERROR"
    exit 1
fi

# Verifier si c'est une URL YouTube
is_youtube() {
    [[ "$1" =~ youtube\.com/watch ]] || \
    [[ "$1" =~ youtu\.be/ ]] || \
    [[ "$1" =~ youtube\.com/shorts/ ]]
}

# Verifier si c'est une URL valide
is_url() {
    [[ "$1" =~ ^https?:// ]]
}

if ! is_url "$URL"; then
    notify "Cast" "Pas une URL valide" "$ICON_ERROR"
    exit 1
fi

# Notification de demarrage
if is_youtube "$URL"; then
    notify "Cast YouTube" "Envoi vers TV..." "$ICON_INFO"
else
    notify "Cast" "Envoi vers TV..." "$ICON_INFO"
fi

# Lancer le cast en background
output=$("$CATT" -d "$DEVICE" cast "$URL" 2>&1)
exit_code=$?

if [[ $exit_code -eq 0 ]]; then
    # Extraire le titre si disponible
    if [[ "$output" =~ Playing\ \"([^\"]+)\" ]]; then
        title="${BASH_REMATCH[1]}"
        notify "Cast" "Lecture: $title" "$ICON_SUCCESS"
    else
        notify "Cast" "Lecture demarree" "$ICON_SUCCESS"
    fi
else
    notify "Cast" "Erreur: $output" "$ICON_ERROR"
    exit 1
fi
