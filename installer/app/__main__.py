"""Point d'entree : python -m installer.app [--demo]."""
from __future__ import annotations

import sys

from .backend.server import main

if __name__ == "__main__":
    main(demo="--demo" in sys.argv[1:])
