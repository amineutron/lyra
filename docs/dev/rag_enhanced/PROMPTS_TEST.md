# Prompts de Test LYRA

**Date**: 2026-02-14
**Objectif**: Tester LYRA avec RAG Enhanced + Context Injector

---

## Catégorie 1: Queries Claires (Score HIGH)

Ces queries devraient générer un score RAG >0.85 et **ne PAS** activer le Context Injector.

### VM/Backup (FEDORA)

```
démarre preprod-09
arrête la vm preprod-10
liste les machines virtuelles
crée un backup de preprod-09
restaure le dernier backup
clone preprod-09 en test-clone
fais un snapshot de preprod-10
vérifie l'état des VMs
```

### Domotique (HUE)

```
allume les lumières de la chambre
éteins toutes les lumières
tamise la lumière du salon
mets les lumières en bleu
active la scène romantique dans la chambre
```

### TV/Cast (CATT + TV)

```
allume la télé
monte le volume à 50
caste cette vidéo youtube https://youtu.be/dQw4w9WgXcQ
lance Netflix sur la TV
arrête le cast en cours
mets la TV en pause
```

### Home Cinema (DENON)

```
allume l'ampli
mets le volume à 44
passe la source en bluray
coupe le son du denon
éteins le home cinema
```

---

## Catégorie 2: Queries Ambiguës Multi-Tour (Context Injector)

Ces scénarios devraient **activer le Context Injector** si RAG génère un score MEDIUM (0.60-0.85) avec gap < 0.10.

### Scénario A: VM → Snapshot (Contexte VM)

**Objectif**: Après avoir démarré une VM, "fais un snapshot" devrait utiliser le contexte pour identifier la VM.

```
Tour 1: démarre preprod-09
Tour 2: fais un snapshot
        ↓
        ATTENDU: Context Injector détecte last_vm=preprod-09
                 Message: "D'après le contexte sur la VM preprod-09, je vais exécuter snapshot. C'est bien ça?"
```

### Scénario B: Cast → Arrête (Contexte CATT)

**Objectif**: Après avoir casté une vidéo, "arrête" est ambigu (TV/Cast/VM) → contexte aide.

```
Tour 1: caste cette vidéo youtube https://youtu.be/jNQXAC9IVRw
Tour 2: arrête
        ↓
        ATTENDU: Context Injector détecte last_mcp=catt.cast_youtube, last_server=CATT
                 Choix: catt.cast_stop (pas tv.power_off ou vm_stop)
                 Message: "D'après le contexte (dernier outil: cast youtube), je vais exécuter stop. C'est bien ça?"
```

### Scénario C: Backup → Sauvegarde (Contexte backup_create)

**Objectif**: "sauvegarde" est ambigu (backup_create vs vm_snapshot) → contexte backup récent aide.

```
Tour 1: crée un backup complet de preprod-09
Tour 2: fais une sauvegarde
        ↓
        ATTENDU: Context Injector détecte last_mcp=fedora.backup_create, frequent_mcp=backup_create
                 Choix: backup_create (pas vm_snapshot)
```

### Scénario D: Lumières → Éteins Tout (Contexte HUE)

**Objectif**: "éteins tout" est ambigu (HUE vs TV+Denon) → contexte lumières récent aide.

```
Tour 1: allume les lumières du salon
Tour 2: tamise à 30%
Tour 3: éteins tout
        ↓
        ATTENDU: Context Injector détecte last_server=HUE, frequent_mcp=hue.*
                 Choix: hue.turn_off_all (pas tv.power_off + denon.power_off)
```

---

## Catégorie 3: Queries Vagues (Score LOW → Fallback LYRA)

Ces queries devraient générer un score RAG <0.60 et **fallback** vers LYRA conversation.

```
fais quelque chose
aide-moi
c'est quoi ça
lance un truc
arrête ce machin
qu'est-ce qui se passe
montre-moi
```

**ATTENDU**: LYRA répond conversationnellement sans proposer d'outil MCP.

---

## Catégorie 4: Questions de Connaissance (QueryType.KNOWLEDGE)

Ces queries demandent des explications, pas des actions.

```
c'est quoi vm_clone ?
comment fonctionne le backup ?
quels sont les outils disponibles ?
explique-moi vm_snapshot
quelle est la différence entre backup et snapshot ?
comment restaurer un backup ?
```

**ATTENDU**: LYRA explique sans exécuter d'action.

---

## Catégorie 5: Edge Cases

### Requêtes avec Slang/Anglicismes

Tester la normalisation slang:

```
start preprod-09          → devrait normaliser en "démarre"
switch les lights         → "allume les lumières"
kill la vm                → "arrête la vm"
boot le serveur           → "démarre le serveur"
backup la machine         → "sauvegarde la machine"
```

### Requêtes avec Synonymes

Tester l'expansion synonymes:

```
lance la vm               → synonymes: "démarre", "boot"
coupe les lumières        → "éteins", "désactive"
diffuse cette vidéo       → "caste", "envoie"
```

### Multi-Step (Plusieurs Actions)

```
clone preprod-09 en test-01 et démarre-le
arrête toutes les VMs et crée un backup
allume les lumières et lance Netflix
```

**ATTENDU**: LYRA propose un plan séquentiel ou demande clarification.

---

## Catégorie 6: Mode Performance

Tester le skip de confirmation en mode performance:

```bash
./run.sh -p --rag-enhanced
```

Puis:

```
allume les lumières        → exécution directe (domotique autorisée)
monte le volume            → exécution directe
démarre preprod-09         → CONFIRMATION requise (VM/backup jamais skip)
arrête preprod-10          → CONFIRMATION requise
```

**ATTENDU**: Domotique sans confirmation, VM/Backup avec confirmation.

---

## Catégorie 7: Context Injector avec Confirmation Forcée

Si le Context Injector injecte du contexte, **confirmation TOUJOURS requise** même en mode performance:

```bash
./run.sh -p --rag-enhanced
```

Puis:

```
Tour 1: allume les lumières
Tour 2: éteins tout
        ↓
        ATTENDU: Contexte injecté (ambiguïté HUE vs TV)
                 CONFIRMATION REQUISE même en mode performance
                 Message: "D'après le contexte sur les lumières, je vais exécuter turn off all. C'est bien ça?"
```

---

## Workflow de Test Recommandé

### Test 1: RAG Enhanced Basique

```bash
./run.sh --rag-enhanced --debug
```

Tester catégories 1, 3, 4 (queries claires, vagues, connaissance).

**Vérifier**:
- Scores RAG affichés
- Classification correcte (HIGH/MEDIUM/LOW)
- Pas d'activation Context Injector (queries claires)

### Test 2: Context Injector Multi-Tour

```bash
./run.sh --rag-enhanced --debug
```

Tester scénarios A, B, C, D (catégorie 2).

**Vérifier**:
- Contexte injecté (affichage "💡 [Context Injector]")
- Message de confirmation expliquant le contexte
- Bon outil choisi grâce au contexte

### Test 3: Mode Performance + Context

```bash
./run.sh -p --rag-enhanced
```

Tester catégorie 6 + 7.

**Vérifier**:
- Domotique skip confirmation
- VM/Backup toujours confirmation
- Context Injector force confirmation même en mode performance

### Test 4: Vocal + Context

```bash
./run.sh --vocal --rag-enhanced
```

Tester scénarios multi-tour (catégorie 2).

**Vérifier**:
- Message contexte prononcé à l'oral
- Confirmation vocale claire
- UX fluide

---

## Métriques à Observer (Mode Debug)

En mode `--debug`, observer:

```
[1] Slang Normalization: (inchangé) ou "start" → "démarre"
[2] Synonym Expansion: +3 tokens ou (inchangé)
[3] RAG Retrieval: Score 0.900 (HIGH/MEDIUM/LOW)
[4] Confidence Cascade: Action execute/propose/fallback
[5] Context Injection: OUI/NON
[6] Tool Final: fedora.vm_start, args {...}

📊 Performance Metrics:
    slang_latency_ms        :   0.50ms
    synonym_latency_ms      :   1.20ms
    rag_latency_ms          :  25.00ms
    cascade_latency_ms      :   0.30ms
    context_latency_ms      :   8.00ms
    TOTAL                   :  35.00ms
    ✅ Overhead <50ms (objectif)
```

**Objectif**: Total overhead <50ms (hors LLM/MCP).

---

## Bugs Potentiels à Surveiller

### Bug 1: Context Injector ne s'active jamais

**Symptôme**: Toujours "Context Injection: NON" même pour queries ambiguës.

**Cause probable**: Scores RAG trop polarisés (toujours HIGH ou LOW, jamais MEDIUM).

**Solution**: Créer queries plus ambiguës OU ajuster seuils MEDIUM (actuellement 0.60-0.85).

### Bug 2: Mauvais outil choisi malgré contexte

**Symptôme**: Contexte injecté mais outil final incorrect.

**Cause probable**: EPHAISTOS ignore le contexte `[ctx: ...]` dans enriched_query.

**Solution**: Vérifier prompt EPHAISTOS comprend format contexte.

### Bug 3: Confirmation en boucle

**Symptôme**: Demande confirmation multiple fois pour la même action.

**Cause probable**: `requires_confirmation` mal géré.

**Solution**: Vérifier que confirmation se fait 1 seule fois.

### Bug 4: Crash sur EnhancedPipelineResult

**Symptôme**: `AttributeError: 'PipelineResult' object has no attribute 'context_injected'`

**Cause probable**: Mode `--rag-enhanced` pas activé, utilise Pipeline V2 classique.

**Solution**: Toujours lancer avec `./run.sh --rag-enhanced`.

---

## Checklist de Validation

- [ ] **Queries claires** → Score HIGH, pas de contexte
- [ ] **Queries vagues** → Score LOW, fallback LYRA
- [ ] **Multi-tour VM** → Contexte injecté, VM détectée
- [ ] **Multi-tour Cast** → Contexte injecté, CATT prioritaire
- [ ] **Multi-tour Backup** → Contexte injecté, backup_create vs snapshot
- [ ] **Multi-tour Lumières** → Contexte injecté, HUE prioritaire
- [ ] **Slang normalization** → "start" → "démarre"
- [ ] **Synonym expansion** → Tokens ajoutés
- [ ] **Mode performance** → Domotique skip, VM/Backup toujours confirmation
- [ ] **Context force confirmation** → Même en mode performance
- [ ] **Vocal** → Message contexte prononcé
- [ ] **Performance** → Overhead <50ms

---

## Notes

- **Context Injector** est rare en pratique car RAG optimisé génère scores polarisés
- Pour forcer activation Context Injector, créer queries **vraiment ambiguës** après actions claires
- Le message de confirmation doit être **LYRA-friendly** (pas de jargon technique)
- En mode vocal, le message doit être **court et clair** (<15 mots)

---

Bonne chance pour les tests! 🚀
