# Phase 3 : Pipeline Callback - Documentation

**Date** : 2026-02-06
**Statut** : ✅ Terminée

---

## Objectif

Intégrer les acknowledgements dans le pipeline pour permettre un **affichage progressif** (ack immédiat → résultat final).

**Flux cible** :
```
User: "démarre preprod-09"
    ↓
Pipeline.process(query, callback=on_progress)
    ↓
IntentClassifier → Intent.DEMANDE
    ↓
callback("acknowledgement", "D'accord, je regarde ça...")  ← Immédiat !
    ↓
[RAG → EPHAISTOS → HESTIA]
    ↓
Return PipelineResult("Parfait ! La VM est démarrée...")
```

---

## Changements Apportés

### 1. Pipeline.__init__() - Nouveau param `tts_mode`

**Avant** :
```python
def __init__(self, config: RAGConfig):
    self.config = config
    self._initialized = False
```

**Après** :
```python
def __init__(self, config: RAGConfig, tts_mode: bool = False):
    """Initialise le pipeline.

    Args:
        config: Configuration RAG
        tts_mode: Mode TTS (True = vocal court, False = texte detaille)
    """
    self.config = config
    self.tts_mode = tts_mode  # ← Nouveau !
    self._initialized = False
```

**Utilité** :
- Permet de spécifier le mode TTS/TEXT dès l'initialisation du pipeline
- Passé à LYRA lors de l'initialisation

---

### 2. Pipeline.initialize() - Passage `tts_mode` à LYRA

**Avant** :
```python
self._lyra = LyraVoice(self._model_manager)
```

**Après** :
```python
self._lyra = LyraVoice(self._model_manager, tts_mode=self.tts_mode)
```

**Impact** :
- LYRA adaptée au mode (vocal court vs texte détaillé)
- Réponses LYRA cohérentes avec le mode d'utilisation

---

### 3. Pipeline.process() - Nouveau param `callback`

**Avant** :
```python
def process(self, query: str) -> PipelineResult:
    """Traite une requete utilisateur."""
    # ...
    return self._route_query(query)
```

**Après** :
```python
def process(self, query: str, callback: Optional[callable] = None) -> PipelineResult:
    """Traite une requete utilisateur.

    Args:
        query: Requete en francais
        callback: Fonction callback optionnelle pour feedback progressif.
                 Signature: callback(step: str, message: str)
                 Steps possibles: "acknowledgement", "progress", "result"

    Returns:
        PipelineResult avec la reponse
    """
    # ...
    return self._route_query(query, callback=callback)
```

**Signature callback** :
```python
def callback(step: str, message: str) -> None:
    """Callback pour feedback progressif.

    Args:
        step: Type de step ("acknowledgement", "progress", "result")
        message: Message à afficher
    """
```

---

### 4. Pipeline._route_query() - Appel acknowledgement immédiat

**Avant** :
```python
def _route_query(self, query: str) -> PipelineResult:
    # Classifier l'intention via l'agent LYRA
    if self._intent_classifier is not None:
        classification = self._intent_classifier.classify(query)

        if classification.intent == Intent.INFO:
            return self._process_knowledge(query)
        # ...
```

**Après** :
```python
def _route_query(self, query: str, callback: Optional[callable] = None) -> PipelineResult:
    # Classifier l'intention via l'agent LYRA
    if self._intent_classifier is not None:
        classification = self._intent_classifier.classify(query)

        # ACKNOWLEDGEMENT IMMÉDIAT (Nouveau !)
        if callback and self._lyra:
            ack = self._lyra.generate_acknowledgement(
                intent=classification.intent,
                query=query
            )
            if ack:
                callback("acknowledgement", ack)

        if classification.intent == Intent.INFO:
            return self._process_knowledge(query)
        # ...
```

**Impact** :
- Acknowledgement généré **immédiatement** après classification (< 100ms)
- Callback appelé avant le traitement (RAG, EPHAISTOS, HESTIA)
- User reçoit feedback instantané

---

## Flux Complet

### Exemple : Démarrage VM

```
[T+0ms]    User input: "démarre preprod-09"
              ↓
[T+10ms]   Pipeline.process(query, callback=on_progress)
              ↓
[T+50ms]   IntentClassifier.classify()
              → Intent.DEMANDE
              ↓
[T+60ms]   LYRA.generate_acknowledgement(Intent.DEMANDE)
              → "D'accord, je regarde ça..."
              ↓
           callback("acknowledgement", "D'accord, je regarde ça...")
              ↓
           [AFFICHAGE IMMÉDIAT]
           >>> LYRA: "D'accord, je regarde ça..."

[T+100ms]  RAG.search("démarre preprod-09")
              → Specs vm_start
              ↓
[T+500ms]  EPHAISTOS.analyze()
              → {"name": "vm_start", "arguments": {"vm_name": "preprod-09"}}
              ↓
[T+1s]     HESTIA.confirm()
              → User confirme "O"
              ↓
[T+3s]     HESTIA.execute()
              → Success
              ↓
[T+5s]     LYRA.format_result()
              → "Parfait ! La VM preprod-09 est démarrée..."
              ↓
           [AFFICHAGE FINAL]
           >>> LYRA: "Parfait ! La VM preprod-09 est démarrée. Son IP est 192.168.122.146."
```

---

## Utilisation

### Initialisation du Pipeline

```python
from lyra.core.pipeline import Pipeline
from lyra.core.config import RAGConfig

config = RAGConfig.from_yaml('config.yaml')

# Mode TEXT (par défaut)
pipeline_text = Pipeline(config, tts_mode=False)
pipeline_text.initialize()

# Mode TTS (vocal)
pipeline_tts = Pipeline(config, tts_mode=True)
pipeline_tts.initialize()
```

---

### Callback Personnalisé

```python
from colorama import Fore, Style

def on_progress(step: str, message: str):
    """Callback pour affichage progressif."""
    if step == "acknowledgement":
        # Afficher en bleu clair (immédiat)
        print(f"{Fore.LIGHTBLUE_EX}{message}{Style.RESET_ALL}")

        # Optionnel: TTS immédiat en mode vocal
        if pipeline.tts_mode:
            import piper_tts
            piper_tts.speak(message)

    elif step == "progress":
        # Afficher progression (optionnel)
        print(f"{Fore.YELLOW}{message}{Style.RESET_ALL}")

    elif step == "result":
        # Résultat final (optionnel, déjà géré par PipelineResult)
        pass
```

---

### Appel du Pipeline

```python
# Avec callback (affichage progressif)
result = pipeline.process(
    query="démarre preprod-09",
    callback=on_progress
)

# Sans callback (comportement classique)
result = pipeline.process("démarre preprod-09")
```

---

### Exemple Complet

```python
from lyra.core.pipeline import Pipeline
from lyra.core.config import RAGConfig
from colorama import Fore, Style, init

init(autoreset=True)

# Configuration
config = RAGConfig.from_yaml('config.yaml')
pipeline = Pipeline(config, tts_mode=False)
pipeline.initialize()

# Callback
def on_progress(step: str, message: str):
    if step == "acknowledgement":
        print(f"{Fore.LIGHTBLUE_EX}LYRA: {message}{Style.RESET_ALL}")

# Requête utilisateur
user_input = input(">>> ")

# Traitement avec feedback progressif
result = pipeline.process(user_input, callback=on_progress)

# Affichage résultat final
if result.response:
    print(f"{Fore.LIGHTGREEN_EX}LYRA: {result.response}{Style.RESET_ALL}")
```

**Output** :
```
>>> démarre preprod-09
LYRA: D'accord, je regarde ça...           ← Immédiat (<100ms)
[ACTION PROPOSÉE: vm_start]
[...confirmation...]
LYRA: Parfait ! La VM preprod-09 est démarrée. Son IP est 192.168.122.146.
```

---

## Tests

### Test syntaxe Python

```bash
python -m py_compile lyra/core/pipeline.py
# ✅ Syntaxe OK
```

### Test callback

```python
from lyra.core.pipeline import Pipeline
from lyra.core.config import RAGConfig

config = RAGConfig.from_yaml('config.yaml')
pipeline = Pipeline(config, tts_mode=False)
pipeline.initialize()

# Callback simple
ack_received = []
def test_callback(step: str, message: str):
    if step == "acknowledgement":
        ack_received.append(message)

# Test
result = pipeline.process("démarre preprod-09", callback=test_callback)

# Vérifier qu'un ack a été reçu
assert len(ack_received) > 0
assert ack_received[0] in [
    "D'accord, je regarde ça...",
    "Compris, je lance ça...",
    # ... etc
]
```

---

## Avantages

### Expérience Utilisateur

✅ **Feedback immédiat** : User sait que LYRA travaille (< 100ms)
✅ **Transparence** : User comprend l'état du traitement
✅ **Fluidité** : Pas de silence gênant
✅ **Immersion** : Sensation J.A.R.V.I.S.-like

### Technique

✅ **Non-bloquant** : Ack affiché pendant le traitement
✅ **Optionnel** : Callback optionnel, rétrocompatible
✅ **Extensible** : Peut ajouter d'autres steps ("progress", "result")
✅ **Adaptatif** : Mode TTS/TEXT intégré

---

## Comparaison Avant/Après

### Avant (Sans Callback)

```python
result = pipeline.process("démarre preprod-09")
print(result.response)
```

**Output** :
```
>>> démarre preprod-09
[Attente 2-3s sans feedback]
LYRA: C'est fait, preprod-09 est démarrée.
```

**Problèmes** :
- ❌ Pas de feedback avant le résultat
- ❌ User ne sait pas si LYRA travaille
- ❌ Impression de lag/bug

---

### Après (Avec Callback)

```python
result = pipeline.process("démarre preprod-09", callback=on_progress)
print(result.response)
```

**Output** :
```
>>> démarre preprod-09
LYRA: D'accord, je regarde ça...  ← Immédiat !
[Traitement en arrière-plan]
LYRA: Parfait ! La VM preprod-09 est démarrée.
```

**Avantages** :
- ✅ Feedback immédiat (<100ms)
- ✅ User sait que LYRA travaille
- ✅ Expérience fluide et immersive

---

## Extensions Possibles

### Step "progress"

```python
# Dans Pipeline._process_action()
if callback:
    callback("progress", "Analyse des specs MCP...")

# Plus tard
if callback:
    callback("progress", "Extraction des arguments...")
```

---

### Step "result"

```python
# À la fin de Pipeline.process()
if callback and result.response:
    callback("result", result.response)
```

---

## Prochaine Étape

➡️ **Phase 4 : Main Integration**
- Modifier `main_rag.py` pour utiliser le callback
- Détecter mode vocal (`--vocal`) → `tts_mode=True`
- Affichage progressif (ack bleu → résultat vert)
- TTS immédiat pour l'ack en mode vocal

---

## Fichiers Modifiés

- ✅ `lyra/core/pipeline.py`

---

## Références

- **Issue** : Communication progressive LYRA
- **Phase précédente** : Phase 2 - Acknowledgements
- **Phase suivante** : Phase 4 - Main Integration
- **Date** : 2026-02-06
- **Auteur** : Claude Sonnet 4.5
