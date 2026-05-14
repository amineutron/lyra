#!/usr/bin/env bash
# Test rendu chafa sur la video Manim generee (lecture frame par frame)

VIDEO="/home/amineutron/dev/lyra/intro/media/videos/part3_manim/1080p60/LyraIntro.mp4"

if [ ! -f "$VIDEO" ]; then
    echo "Video introuvable : $VIDEO"
    exit 1
fi

COLS=$(tput cols)
ROWS=$(tput lines)
TMPDIR=$(mktemp -d /tmp/lyra_intro_XXXXXX)

# Extraction des frames en PNG
ffmpeg -i "$VIDEO" \
    -vf "fps=24,scale=$((COLS*2)):-1" \
    "$TMPDIR/frame_%04d.png" 2>/dev/null

# Lecture frame par frame avec protocole kitty (qualite maximale)
tput civis
tput clear
for frame in "$TMPDIR"/frame_*.png; do
    tput cup 0 0
    chafa --size="${COLS}x${ROWS}" -f kitty --stretch "$frame" 2>/dev/null
    sleep 0.042  # ~24fps
done
tput cnorm

rm -rf "$TMPDIR"
