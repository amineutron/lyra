# Tests Scene Iron Man

Suite de tests pour la scene Iron Man de Lyra.

## Structure

```
scenes/ironman/
|-- test_orchestrator.py  Tests orchestrateur
|-- tests/
|   |-- test_integration.py
|   |-- test_edge_cases.py
|   |-- test_performance.py
|   |-- test_stress.py
|   |-- e2e/
|       |-- test_ironman_e2e.sh
|-- phases/
    |-- test_phase0..5.py
```

## Lancement rapide

```bash
cd /home/amineutron/dev/lyra

# Suite principale
python3 -m pytest scenes/ironman/tests/ -v

# Avec coverage
python3 -m pytest scenes/ironman/tests/ --cov=scenes/ironman --cov-report=term-missing

# Tests phases (0, 1, 2)
python3 -m pytest scenes/ironman/phases/test_phase0.py -v
python3 -m pytest scenes/ironman/phases/test_phase1.py -v
python3 -m pytest scenes/ironman/phases/test_phase2.py -v

# E2E (devices reels requis)
bash scenes/ironman/tests/e2e/test_ironman_e2e.sh
```

## Mocks utilises

Tous les tests sont mockes - aucun appel reel aux devices.

- Mock TV: patch(requests.put/get) - simule power/volume/youtube/ambilight
- Mock Hue: patch(requests.put) - simule set_color/brightness/group
- Mock TTS: patch(phase5._speak_jarvis_style)
- Mock Phases: Mock().execute.return_value = {success: True, duration: X}

## Interpretation des resultats

PASS: comportement code conforme a l attendu
FAIL: regression possible, verifier les logs

## Troubleshooting

### ImportError phases 3/4/5

Les tests tests_phase3/4/5.py utilisent des imports relatifs.
Lancer depuis la racine Lyra:

```bash
cd /home/amineutron/dev/lyra
python3 -m pytest scenes/ironman/tests/ -v
```

### Tests E2E echouent

Les tests E2E necessitent le reseau local (TV + Hue).
Hors reseau, les checks ping sont marques SKIP.
