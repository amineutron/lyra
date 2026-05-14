"""
Configuration pytest pour les tests Lyra.
"""

import sys
from pathlib import Path

# Ajouter le repertoire racine au path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
