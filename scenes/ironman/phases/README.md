# Iron Man Scene - Phases

Experience immersive de ~33 secondes synchronisant TV Philips + lumieres Hue
+ ecrans PC (Hyprland), declenchee par trigger vocal.

## Phases Implementees

| Phase | Nom | Duree | Status |
|-------|-----|-------|--------|
| 0 | Detection & Validation | <2s | OK |
| 1 | Blackout (+ ecrans PC) | 3s | OK |
| 2 | Impact (flash + YouTube) | 3.5s | OK |
| 3 | Buildup (hue_beat) | 12s | OK |
| 4 | Transition | 7s | OK |
| 5 | TTS J.A.R.V.I.S. | 5.5s | OK |

**Duree totale: ~33s** (toutes phases implementees et testees)

---

## Phase 0 - Detection & Validation

Detecte les triggers vocaux et valide la disponibilite des devices.

### Triggers reconnus

| Trigger | Exemple |
|---------|---------|
| `je suis iron man` | "Lyra, je suis iron man" |
| `je suis tony stark` | "je suis tony stark" |
| `je suis tony` | "ok, je suis tony" |
| `mode iron man` | "active le mode iron man" |
| `scene iron man` | "lance la scene iron man" |

- Insensible a la casse et aux accents
- Fonctionne dans une phrase plus longue

### Validation

| Device | Test | Timeout |
|--------|------|---------|
| TV Philips | HTTP GET `/6/system` | 2s |
| Bridge Hue | HTTP GET `/api/{user}/lights` | 2s |

### Rollback

Sauvegarde l'etat actuel dans `/tmp/ironman_rollback.json` pour restauration
en cas d'erreur.

---

## Phase 1 - Blackout Dramatique

Extinction totale pendant 3 secondes pour creer la tension.

### Timeline

```
T+0.0s: Eteindre lumieres (groupe 81, instantane)
T+0.0s: Eteindre TV si allumee
T+0.0s: Eteindre ecrans PC (Hyprland DPMS, si pc_screens actif)
T+0.0s -> T+3.0s: Noir et silence total
T+1.0s: Sortie clavier armee (toute touche rallume les ecrans PC)
T+3.0s: Phase terminee
```

### Ecrans PC (pc_screens.py)

- Opt-in via `scenes.ironman.pc_screens: true` dans `config.yaml`
- Necessite Hyprland (`hyprctl dispatch dpms off`)
- Sortie: n'importe quelle touche clavier, armee 1s apres extinction
  (`misc:key_press_enables_dpms`, restaure apres reveil par un watcher
  bash detache qui survit au process Python)
- Mode sous-scene/test: rallumage automatique de secours apres 60s
- Rollback d'erreur: rallumage force immediat

### Specifications

| Parametre | Valeur |
|-----------|--------|
| Duree | 3.0s exactement |
| Latence extinction | <500ms |
| Transition Hue | 0ms (instantane) |

### Gestion erreurs

- Erreur Hue: Continue (non-bloquant)
- Erreur TV: Continue (non-bloquant)
- hyprctl absent: ecrans PC ignores (non-bloquant)

---

## Phase 2 - Premier Impact

Flash blanc aveuglant + transition bleu arc reactor + musique AC/DC.

### Timeline

```
T+0.0s:  Flash blanc pur (254 brightness)
T+0.2s:  Transition vers bleu arc reactor
T+0.5s:  Allumer TV
T+2.5s:  Lancer YouTube AC/DC (catt)
T+3.5s:  Phase terminee
```

### Couleurs

| Couleur | RGB | Usage |
|---------|-----|-------|
| Blanc pur | (255, 255, 255) | Flash initial 200ms |
| Bleu arc reactor | (0, 100, 255) | Stabilisation |

### YouTube

- Video: AC/DC - Back In Black (`pAgnJDJN4VA`)
- Methode: `catt cast_site` (device configure dans `catt.device`)
- Fallback: mode lights-only si echec (la phase reste un succes si le
  flash a fonctionne)

---

## Phase 3 - Buildup (12s)

Pulsations synchronisees sur la musique, brightness 0 -> 254.

- Si `hue_beat` tourne (PID file `/tmp/ironman_hue.pid`), les beats sont
  geres en temps reel par l'Entertainment API (DTLS, ~5ms de latence) --
  la phase se contente d'attendre
- Sinon fallback REST: alternance rouge/bleu a 120 BPM (limite par le
  bridge a ~1 commande groupe/s, moins fluide)
- `hue_beat` est lance par l'orchestrateur au debut de la phase
  (`--mode=pulse --palette=ironman --bass-only`)

## Phase 4 - Transition (7s)

Ralentissement des beats, fondu vers bleu stable (brightness 150),
arret de la musique.

## Phase 5 - TTS J.A.R.V.I.S. (5.5s)

Voix synthetisee Piper (phrase aleatoire) + pulse de confirmation.
L'orchestrateur arrete `hue_beat` a la fin de cette phase.

---

## Usage

### Lancer la scene complete

```bash
cd /home/amineutron/dev/lyra
.venv/bin/python -m scenes.ironman.run_scene        # confirmation interactive
.venv/bin/python -m scenes.ironman.run_scene -y     # sans confirmation
```

### Sous-scenes independantes

```bash
.venv/bin/python -m scenes.ironman.run_scene --test           # validation seule
.venv/bin/python -m scenes.ironman.run_scene --phase 1        # une phase
.venv/bin/python -m scenes.ironman.run_scene --phases 2-4     # plage
.venv/bin/python -m scenes.ironman.run_scene --phases 1,3,5   # liste
.venv/bin/python -m scenes.ironman.run_scene --from-phase 3   # de N a la fin
```

Options: `--no-rollback` (ne pas restaurer Hue/TV a la fin),
`--no-validate` (ne pas prefixer la Phase 0).

Par defaut une sous-scene prefixe la Phase 0 (capture de l'etat pour le
rollback) et restaure l'etat Hue/TV a la fin. Les ecrans PC restent
eteints jusqu'a un appui clavier (auto-wake 60s en secours).

### En Python

```python
from scenes.ironman import IronManOrchestrator

orchestrator = IronManOrchestrator()
orchestrator.trigger("je suis iron man")      # scene complete
orchestrator.run_phases([2, 3])               # sous-scene impact+buildup
```

---

## Tests

```bash
cd /home/amineutron/dev/lyra
.venv/bin/python -m pytest scenes/ironman/ -v                 # tout
.venv/bin/python -m pytest scenes/ironman/phases/ -v          # phases seules
.venv/bin/python -m pytest scenes/ironman/phases/test_phase2.py -v
```

---

## Configuration

Les phases lisent `config.yaml` et fusionnent `secrets.yaml` (gitignore)
par-dessus. Ne jamais mettre de vraies cles dans un fichier versionne.

```yaml
tv:
  host: "192.168.1.50"
  user: "<user>"
  pass: "<64-hex depuis pairing JointSpace>"

hue:
  bridge_ip: "192.168.1.51"
  username: "<cle API Hue>"

catt:
  device: "55OLED705/12"

scenes:
  ironman:
    pc_screens: true   # extinction ecrans PC pendant le blackout
```

---

## Troubleshooting

### TV ne repond pas

```bash
curl -k https://192.168.1.50:1926/6/system
curl -k https://192.168.1.50:1926/6/powerstate
```

### Hue ne repond pas

```bash
curl http://192.168.1.51/api/<cle-api>/lights
```

### YouTube ne demarre pas

1. Verifier catt: `catt scan`
2. Verifier le nom du device dans `config.yaml` (`catt.device`)

### Ecrans PC ne se rallument pas

```bash
hyprctl dispatch dpms on
hyprctl keyword misc:key_press_enables_dpms 0   # restaurer l'option
```

### Simuler devices offline

```bash
sudo iptables -A OUTPUT -d 192.168.1.50 -j DROP   # bloquer TV
sudo iptables -D OUTPUT -d 192.168.1.50 -j DROP   # debloquer
```

---

## Fichiers

```
scenes/ironman/
├── orchestrator.py           # State machine + run_phases + rollback
├── run_scene.py              # CLI (scene complete + sous-scenes)
└── phases/
    ├── __init__.py           # Exports
    ├── pc_screens.py         # Ecrans PC Hyprland (DPMS + sortie clavier)
    ├── phase0_detection.py   # Detection + Validation
    ├── phase1_blackout.py    # Blackout 3s + ecrans PC
    ├── phase2_impact.py      # Flash + YouTube (catt)
    ├── phase3_buildup.py     # Pulsations (hue_beat ou fallback REST)
    ├── phase4_transition.py  # Ralentissement + stabilisation
    ├── phase5_tts.py         # Voix J.A.R.V.I.S. (Piper)
    └── test_phase*.py        # Tests unitaires par phase
```
