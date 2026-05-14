#!/usr/bin/env bash
# =============================================================================
# LYRA INTRO -- Sequence complete de demarrage
# Enchaine :
#   1. Intro video HUD LYRA    (mpv fullscreen, qualite native)
#   2. Splash figlet + lolcat
#   3. Boot screen installation (rich Python)
#   4. Glitch de transition
#   5. Activation finale WOW   (mpv fullscreen, qualite native)
# Usage : ./lyra_intro.sh [--skip-video] [--skip-splash] [--skip-boot] [--skip-activation]
# =============================================================================

INTRO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LYRA_PYTHON="$INTRO_DIR/../.venv/bin/python"
VIDEO_INTRO="$INTRO_DIR/media/videos/part3_manim/1080p60/LyraIntro.mp4"
VIDEO_ACTIVATION="$INTRO_DIR/media/videos/part4_activation/1080p60/LyraActivation.mp4"

SKIP_VIDEO=false
SKIP_SPLASH=false
SKIP_BOOT=false
SKIP_ACTIVATION=false

for arg in "$@"; do
    case $arg in
        --skip-video)      SKIP_VIDEO=true      ;;
        --skip-splash)     SKIP_SPLASH=true     ;;
        --skip-boot)       SKIP_BOOT=true       ;;
        --skip-activation) SKIP_ACTIVATION=true ;;
    esac
done

# -- Fonction lecture video native via mpv (qualite parfaite) -----------------
play_video() {
    local video="$1"
    MANGOHUD=0 mpv \
        --fs \
        --no-border \
        --really-quiet \
        --no-terminal \
        --loop=no \
        --keep-open=no \
        "$video"
}

# -- Partie 1 : Video intro HUD LYRA -----------------------------------------
if [ "$SKIP_VIDEO" = false ] && command -v mpv &>/dev/null && [ -f "$VIDEO_INTRO" ]; then
    play_video "$VIDEO_INTRO"
fi

# -- Partie 2 : Splash figlet + lolcat ----------------------------------------
if [ "$SKIP_SPLASH" = false ] && command -v figlet &>/dev/null && command -v lolcat &>/dev/null; then
    bash "$INTRO_DIR/part1_splash.sh"
fi

# -- Partie 3 : Boot screen installation (rich) --------------------------------
if [ "$SKIP_BOOT" = false ] && [ -f "$LYRA_PYTHON" ]; then
    "$LYRA_PYTHON" "$INTRO_DIR/part2_boot.py"
fi

# -- Transition : effet glitch ------------------------------------------------
"$LYRA_PYTHON" "$INTRO_DIR/part3_glitch.py"

# -- Partie 4 : Animation d'activation finale (WOW) ---------------------------
if [ "$SKIP_ACTIVATION" = false ] && command -v mpv &>/dev/null && [ -f "$VIDEO_ACTIVATION" ]; then
    play_video "$VIDEO_ACTIVATION"
fi
