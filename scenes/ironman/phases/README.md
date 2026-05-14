# Iron Man Scene - Phases

Experience immersive de ~33 secondes synchronisant TV Philips + lumieres Hue.

## Phases Implementees

| Phase | Nom | Duree | Status |
|-------|-----|-------|--------|
| 0 | Detection & Validation | <2s | OK |
| 1 | Blackout | 3s | OK |
| 2 | Impact | 3.5s | OK |
| 3 | Buildup | 12s | TODO |
| 4 | Transition | 7s | TODO |
| 5 | TTS J.A.R.V.I.S. | 5.5s | TODO |

**Duree totale actuelle: ~8.5s** (Phases 0-2)

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

Sauvegarde l'etat actuel dans `/tmp/ironman_rollback.json` pour restauration en cas d'erreur.

---

## Phase 1 - Blackout Dramatique

Extinction totale pendant 3 secondes pour creer la tension.

### Timeline

```
T+0.0s: Eteindre lumieres (groupe 81, instantane)
T+0.0s: Eteindre TV si allumee
T+0.0s → T+3.0s: Noir et silence total
T+3.0s: Phase terminee
```

### Specifications

| Parametre | Valeur |
|-----------|--------|
| Duree | 3.0s exactement |
| Latence extinction | <500ms |
| Transition Hue | 0ms (instantane) |

### Gestion erreurs

- Erreur Hue: Continue (non-bloquant)
- Erreur TV: Continue (non-bloquant)

---

## Phase 2 - Premier Impact

Flash blanc aveuglant + transition bleu arc reactor + musique AC/DC.

### Timeline

```
T+0.0s:  Flash blanc pur (254 brightness)
T+0.2s:  Transition vers bleu arc reactor
T+0.5s:  Allumer TV
T+2.5s:  Lancer YouTube AC/DC
T+3.0s:  Activer Ambilight follow_audio
T+3.5s:  Phase terminee
```

### Couleurs

| Couleur | RGB | Usage |
|---------|-----|-------|
| Blanc pur | (255, 255, 255) | Flash initial 200ms |
| Bleu arc reactor | (0, 100, 255) | Stabilisation |

### YouTube

- Video: AC/DC - Back In Black
- ID: `pAgnJDJN4VA`
- Methode: ADB (utilise compte YouTube Premium)
- Retry: 1 fois si echec
- Fallback: Mode lights-only si echec total

### Ambilight

- Mode: `follow_audio`
- Active seulement si musique demarre
- Skip si YouTube echoue

---

## Usage

### Lancer la scene complete

```bash
ironman              # Alias bash
# ou
/home/amineutron/dev/lyra/.venv/bin/python \
    /home/amineutron/dev/lyra/scenes/ironman/run_scene.py
```

### Options de test

```bash
ironman --test       # Validation seulement
ironman --phase1     # Arret apres blackout
ironman --phase2     # Arret apres impact
```

### En Python

```python
from scenes.ironman.phases import Phase0Detection, Phase1Blackout, Phase2Impact

# Phase 0
phase0 = Phase0Detection()
if phase0.is_trigger_detected("je suis iron man"):
    success, msg, state = phase0.validate_and_prepare()
    if success:
        # Phase 1
        phase1 = Phase1Blackout()
        result1 = phase1.execute()

        # Phase 2
        phase2 = Phase2Impact()
        result2 = phase2.execute()
```

---

## Tests

### Lancer tous les tests

```bash
cd /home/amineutron/dev/lyra
.venv/bin/python -m pytest scenes/ironman/phases/ -v
```

### Avec coverage

```bash
.venv/bin/python -m pytest scenes/ironman/phases/ -v \
    --cov=scenes/ironman/phases --cov-report=term-missing
```

### Tests par phase

```bash
# Phase 0
.venv/bin/python -m pytest scenes/ironman/phases/test_phase0.py -v

# Phase 1
.venv/bin/python -m pytest scenes/ironman/phases/test_phase1.py -v

# Phase 2
.venv/bin/python -m pytest scenes/ironman/phases/test_phase2.py -v
```

### Resultats actuels

```
78 tests passed
Coverage: 92%
```

---

## Configuration

Les phases lisent la configuration depuis `/home/amineutron/dev/lyra/config.yaml`:

```yaml
tv:
  host: "192.168.1.50"
  user: "***REMOVED***"
  pass: "***REMOVED***"

hue:
  bridge_ip: "192.168.1.51"
  username: "***REMOVED***"
```

---

## Troubleshooting

### TV ne repond pas

```bash
# Verifier connectivite
curl -k https://192.168.1.50:1926/6/system

# Verifier si en veille
curl -k https://192.168.1.50:1926/6/powerstate
```

### Hue ne repond pas

```bash
# Verifier bridge
curl http://192.168.1.51/api/***REMOVED***/lights
```

### YouTube ne demarre pas

1. Verifier ADB disponible: `ls /tmp/platform-tools/adb`
2. Verifier connexion: `/tmp/platform-tools/adb connect 192.168.1.50:5555`
3. Verifier autorisation sur TV (popup)

### Simuler devices offline

```bash
# Bloquer TV
sudo iptables -A OUTPUT -d 192.168.1.50 -j DROP

# Debloquer
sudo iptables -D OUTPUT -d 192.168.1.50 -j DROP
```

---

## Fichiers

```
scenes/ironman/phases/
├── __init__.py           # Exports
├── phase0_detection.py   # Detection + Validation
├── phase1_blackout.py    # Blackout 3s
├── phase2_impact.py      # Flash + YouTube
├── test_phase0.py        # 39 tests
├── test_phase1.py        # 17 tests
├── test_phase2.py        # 22 tests
└── README.md             # Cette documentation
```

---

## Prochaines phases (TODO)

### Phase 3 - Buildup (12s)
- 24 beats a 120 BPM
- Alternance rouge/bleu
- Progression brightness 0 → 254

### Phase 4 - Transition (7s)
- Ralentissement beats
- Fondu vers bleu stable
- Arret musique

### Phase 5 - TTS J.A.R.V.I.S. (5.5s)
- Voix synthetisee
- Phrase aleatoire
- Pulse confirmation
