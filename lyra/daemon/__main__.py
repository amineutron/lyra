"""Point d'entree du demon : python -m lyra.daemon [--config config.yaml]."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# Le demon doit tourner depuis la racine du repo (config.yaml, models/, .venv)
REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description="Lyra daemon")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    os.chdir(REPO_ROOT)
    sys.path.insert(0, str(REPO_ROOT))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        stream=sys.stderr,  # journald via systemd
    )

    from lyra.daemon.server import serve
    return serve(config_path=args.config)


if __name__ == "__main__":
    sys.exit(main())
