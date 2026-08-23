#!/usr/bin/env bash
# Installeur Lyra — point d'entree unique.
#
# Usage :
#   git clone git@github.com:marouabah/lyra.git && cd lyra
#   ./installer/install.sh [--tui|--app] [--demo] [--repo URL]
#                          [--lyra-dir DIR] [--ollama-host HOST] [--skip-models]
#
# --tui (defaut) : installeur terminal (Rich)
# --app          : installeur graphique local (http://127.0.0.1:9877/ui/)
# --demo         : simulation complete, aucune commande reelle
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LYRA_ROOT="$(dirname "$HERE")"
MODE="tui"
PASSTHRU=()

for arg in "$@"; do
    case "$arg" in
        --tui) MODE="tui" ;;
        --app) MODE="app" ;;
        *) PASSTHRU+=("$arg") ;;
    esac
done

command -v python3 >/dev/null || { echo "[!] python3 requis" >&2; exit 1; }
command -v git >/dev/null || { echo "[!] git requis" >&2; exit 1; }

# Interpreteur : venv lyra si present (machine deja installee), sinon
# venv ephemere d'amorcage avec les 3 deps de l'installeur.
if [ -x "$LYRA_ROOT/.venv/bin/python" ]; then
    PY="$LYRA_ROOT/.venv/bin/python"
else
    BOOT="$LYRA_ROOT/.venv-installer"
    if [ ! -x "$BOOT/bin/python" ]; then
        echo "[i] Preparation de l'environnement d'amorcage..."
        python3 -m venv "$BOOT"
        "$BOOT/bin/pip" install -q --upgrade pip
        "$BOOT/bin/pip" install -q rich pyyaml requests
    fi
    PY="$BOOT/bin/python"
fi

cd "$LYRA_ROOT"
if [ "$MODE" = "app" ]; then
    exec "$PY" -m installer.app "${PASSTHRU[@]+"${PASSTHRU[@]}"}"
else
    exec "$PY" -m installer.tui "${PASSTHRU[@]+"${PASSTHRU[@]}"}"
fi
