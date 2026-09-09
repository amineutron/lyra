#!/usr/bin/env bash
# Regenere docs/assets/lyra-intro.gif : l'animation jouee en fin d'installation (intro/lyra_intro.sh).
# Prerequis : asciinema (pip/uv tool), agg (https://github.com/asciinema/agg), une installation Lyra fonctionnelle.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
CAST=/tmp/lyra-intro.cast
asciinema rec --overwrite --cols 100 --rows 32 --idle-time-limit 2 \
  --command "bash $ROOT/intro/lyra_intro.sh --skip-video --skip-activation" "$CAST"
# Adresses IP privees remplacees par des adresses d'exemple, et l'effacement final retire pour que
# la boucle du GIF se termine sur l'ecran « tous les systemes sont nominaux ».
python3 - "$CAST" <<'PY'
import json, re, sys
p = sys.argv[1]; lines = open(p).read().splitlines()
ev = [json.loads(l) for l in lines[1:]]
for e in ev:
    e[2] = re.sub(r"\b192\.168\.\d+\.(\d+)\b", r"192.0.2.\1", e[2])
ev[-1][2] = ev[-1][2].replace("\x1b[2J\x1b[H", "")
ev.append([ev[-1][0] + 2.5, "o", ""])
open(p, "w").write("\n".join([lines[0]] + [json.dumps(e, ensure_ascii=False) for e in ev]) + "\n")
PY
agg --font-size 13 --cols 100 --rows 32 --fps-cap 12 --theme monokai "$CAST" "$ROOT/docs/assets/lyra-intro.gif"
ls -la "$ROOT/docs/assets/lyra-intro.gif"
