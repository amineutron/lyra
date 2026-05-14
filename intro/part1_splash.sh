#!/usr/bin/env bash
# Lyra Intro - Partie 1 : Splash statique figlet + lolcat
# Duree : ~2 secondes d'affichage

clear

# Logo LYRA en ASCII avec la police "big"
figlet -f big -c "LYRA" | lolcat -h 0.3

echo ""

# Sous-titre centre
COLS=$(tput cols)
SUBTITLE="Assistant DevOps Vocal"
PADDING=$(( (COLS - ${#SUBTITLE}) / 2 ))
printf "%${PADDING}s" ""
echo "$SUBTITLE" | lolcat -h 0.2

echo ""

# Version centree
VERSION="v1.0"
PADDING_V=$(( (COLS - ${#VERSION}) / 2 ))
printf "%${PADDING_V}s" ""
echo "$VERSION" | lolcat -h 0.1

echo ""
sleep 1.5
