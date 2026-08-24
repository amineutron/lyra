#!/bin/bash
# Lyra - Script de lancement
# Configure l'environnement et lance Lyra
#
# Usage:
#   ./run.sh                          # Mode RAG Enhanced (defaut)
#   ./run.sh --vocal                  # Mode vocal (STT/TTS)
#   ./run.sh -p                       # Mode performance (domotique)
#   ./run.sh --vocal -p               # Combinaison
#   ./run.sh --legacy                 # Mode classique (Lyra V1)
#   ./run.sh --legacy --vocal         # V1 + vocal
#
#   # Mode one-shot (requete directe, sans interface):
#   ./run.sh "demarre preprod-09"
#   ./run.sh "status des VMs" -v
#   ./run.sh -y "allume la lumiere"
#   ./run.sh -p "cast youtube" -v
#
# Alias: lyra (symlink vers ce script)
# Exemple alias shell: alias lyra="$HOME/dev/lyra/run.sh"

# Resoudre le chemin reel (supporte les symlinks)
SCRIPT_PATH="${BASH_SOURCE[0]}"
while [ -L "$SCRIPT_PATH" ]; do
    SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
    SCRIPT_PATH="$(readlink "$SCRIPT_PATH")"
    [[ $SCRIPT_PATH != /* ]] && SCRIPT_PATH="$SCRIPT_DIR/$SCRIPT_PATH"
done
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
cd "$SCRIPT_DIR"

# Activer le venv
source .venv/bin/activate

# Configurer les bibliotheques CUDA pour faster-whisper
export LD_LIBRARY_PATH="$SCRIPT_DIR/.venv/lib/python3.12/site-packages/nvidia/cublas/lib:$SCRIPT_DIR/.venv/lib/python3.12/site-packages/nvidia/cudnn/lib:$SCRIPT_DIR/.venv/lib64/python3.12/site-packages/nvidia/cublas/lib:$SCRIPT_DIR/.venv/lib64/python3.12/site-packages/nvidia/cudnn/lib:$LD_LIBRARY_PATH"

# Supprimer les warnings HuggingFace (pas besoin de token pour usage local)
export HF_HUB_DISABLE_IMPLICIT_TOKEN=1
export TOKENIZERS_PARALLELISM=false

# Detecter le mode legacy (V1)
if [[ "$*" == *"--legacy"* ]] || [[ "$*" == *"--v1"* ]]; then
    # Mode classique (Lyra V1) - enlever --legacy/--v1 des arguments
    ARGS="${@/--legacy/}"
    ARGS="${ARGS/--v1/}"
    exec python main.py $ARGS
else
    # Client leger : one-shot via le demon (relance auto), sinon il
    # delegue lui-meme a main_rag (interactif/vocal/--standalone)
    exec python -m lyra.client "$@"
fi
