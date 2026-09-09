#!/usr/bin/env bash
# Regenere docs/assets/lyra-demo.gif : une requete de lecture, puis une requete destructive refusee.
# Prerequis : asciinema (pip/uv tool), agg (https://github.com/asciinema/agg), pexpect, le demon Lyra actif.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
export LYRA_DIR="$ROOT"
asciinema rec --overwrite --cols 100 --rows 30 --idle-time-limit 2 \
  --command "python3 $HERE/demo_driver.py" /tmp/lyra-demo.cast
agg --font-size 15 --cols 100 --rows 30 --theme monokai /tmp/lyra-demo.cast "$ROOT/docs/assets/lyra-demo.gif"
ls -la "$ROOT/docs/assets/lyra-demo.gif"
