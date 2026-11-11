# Capsule vocale de Lyra (Quickshell)

Pilule (mascotte + etat + texte) et bulle interactive alimentee par le payload
`display` du demon (`lyra/daemon/display.py`). Instance Quickshell autonome : elle ne
touche pas a la configuration de la barre.

## Installer

```bash
# 1. feuilles de sprites des mascottes (une fois, Chrome/Chromium requis)
python3 scripts/render_mascots.py --out "${XDG_DATA_HOME:-$HOME/.local/share}/lyra/mascots"
# 2. composant (cp -rL suit le lien mascots.json vers installer/assets)
cp -rL quickshell/lyra-capsule "${XDG_CONFIG_HOME:-$HOME/.config}/quickshell/lyra-capsule"
# 3. lancer (ou exec-once dans la config du compositeur)
quickshell -c lyra-capsule
```

Tester sans demon : `quickshell/lyra-capsule/demo` (fenetre normale, payloads factices ;
`DEMO_SCENARIO=0..3`, `DEMO_MASCOT=random|ascii|ascii:owl|<nom>`, `DEMO_SELFTEST=1`).

## Reglages

- `capsule.mascot` dans config.yaml (ou `LYRA_CAPSULE_MASCOT`) : `random` (tirage a chaque
  session), `<nom>` (fixe), `ascii` ou `ascii:<nom>` (creature ASCII).
- Variables : `LYRA_MASCOTS_DIR`, `LYRA_MASCOTS_ASCII`, `LYRA_CAPSULE_TOP`, `LYRA_SOCKET`,
  `LYRA_CONFIG`, `LYRA_PYTHON`.

## Architecture

- `components/` : `SpriteSheet` (lecteur de feuilles), `MascotCatalog`, `MascotView`
  (sprite ou ASCII, etat vocal -> etat de feuille), `DisplayView` (liste, badges, curseur),
  `LyraCapsule` (pilule + bulle, signal `answered(id, value)`, premier arrive gagne).
- `shell.qml` : fenetre layer-shell (overlay, clics traversants hors pilule/bulle) + pont.
- `bridge/lyra_capsule_bridge.py` : client du socket du demon, traduit les messages du
  protocole en evenements de capsule (JSON-lines) et les clics en `answer`. Il s'abonne au
  demon (`subscribe`) : le demon diffuse un `state` par changement d'etat et un `answer_ack`
  quand une confirmation est tranchee ; chaque `answer` renvoie l'`ask_id` diffuse. Sans
  `subscribed` sous 1,5 s (demon ancien), repli sur l'ancien protocole ask/output. Reconnexion
  avec backoff (2 s a 30 s) ; erreur `limit` : nouvel essai toutes les 30 s.
