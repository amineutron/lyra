#!/usr/bin/env bash
# Demarrage du devcontainer / Codespace (roadmap #44) : API tracking puis Lyra
# en arriere-plan. Mode texte seul : ni micro, ni haut-parleur, ni GPU.
set -euo pipefail
cd "$(dirname "$0")/../.."
# Interpreteur explicite : un shell de connexion reinitialise le PATH de l'image
PY=/opt/lyra/.venv/bin/python

nohup /opt/tracking/bin/mcp-tracking-api >/tmp/tracking-api.log 2>&1 &

if [ -z "${OLLAMA_HOST:-}" ]; then
    echo "[eval] OLLAMA_HOST absent : ajoute le secret Codespaces OLLAMA_HOST (URL d'un Ollama"
    echo "[eval] joignable depuis GitHub), puis « Rebuild Container ». Voir deploy/eval/README.md."
    exit 0
fi

nohup "$PY" deploy/eval/bootstrap.py >/tmp/lyra-eval.log 2>&1 &
echo "[eval] Lyra demarre en arriere-plan (1re fois : modeles + index RAG, quelques minutes)."
echo "[eval] Suivi : tail -f /tmp/lyra-eval.log   Essai : lyra \"liste les taches\""
