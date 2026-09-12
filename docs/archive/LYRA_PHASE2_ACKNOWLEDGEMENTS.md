# Phase 2 : Acknowledgements - Documentation

**Date** : 2026-02-06
**Statut** : ✅ Terminée

---

## Objectif

Ajouter un **feedback immédiat** de LYRA pour créer une expérience fluide et immersive (J.A.R.V.I.S.-like).

**Avant** :
```
User: "démarre preprod-09"
[SILENCE 2-3s]
LYRA: "C'est fait, preprod-09 est démarrée."
```

**Après** :
```
User: "démarre preprod-09"
LYRA (immédiat): "D'accord, je regarde ça..."  ← Nouveau !
[Travail en arrière-plan : RAG → EPHAISTOS → HESTIA]
LYRA: "Parfait ! La VM preprod-09 est démarrée..."
```

---

## Changements Apportés

### 1. Nouvelle Méthode : `generate_acknowledgement()`

```python
def generate_acknowledgement(self, intent: str, query: str = "") -> str:
    """Genere un acknowledgement immédiat selon l'intention.

    Permet un feedback instantané avant le traitement (immersion J.A.R.V.I.S.-like).

    Args:
        intent: Type d'intention (Intent.DEMANDE, Intent.INFO, Intent.DISCUSSION)
        query: Requête utilisateur (optionnel, pour contexte)

    Returns:
        Message d'acknowledgement ou "" si pas pertinent
    """
```

**Caractéristiques** :
- ✅ Accepte `Intent` enum ou string
- ✅ Import Intent géré (évite import circulaire)
- ✅ Retourne "" pour DISCUSSION (pas d'ack nécessaire)

---

### 2. Templates d'Acknowledgements

#### Intent : DEMANDE (Action MCP)

```python
acks = [
    "D'accord, je regarde ça...",
    "Compris, je lance ça...",
    "OK, un instant...",
    "C'est parti...",
    "Je m'en occupe...",
    "Laisse-moi voir...",
]
```

**Utilisation** :
- User : "démarre preprod-09"
- LYRA (immédiat) : "D'accord, je regarde ça..."
- [RAG → EPHAISTOS → HESTIA]
- LYRA : "Parfait ! La VM preprod-09 est démarrée..."

---

#### Intent : INFO (Question de connaissance)

```python
acks = [
    "Laisse-moi vérifier...",
    "Je cherche l'info...",
    "Voyons voir...",
    "Je regarde dans les specs...",
    "Un instant, je vérifie...",
]
```

**Utilisation** :
- User : "c'est quoi vm_clone ?"
- LYRA (immédiat) : "Laisse-moi vérifier..."
- [RAG → Recherche specs]
- LYRA : "vm_clone crée une copie complète d'une VM..."

---

#### Intent : DISCUSSION (Conversation)

```python
return ""  # Pas d'ack, réponse directe
```

**Raison** :
- Les conversations (salut, merci, ok) ne nécessitent pas de traitement long
- Réponse immédiate suffit
- Pas besoin d'ack intermédiaire

**Utilisation** :
- User : "salut"
- LYRA (immédiat) : "Bonjour ! Comment puis-je t'aider ?"
- (Pas d'ack avant, réponse directe)

---

## Gestion Import Circulaire

### Problème

`lyra_voice.py` doit utiliser `Intent` de `intent_classifier.py`, mais :
- `lyra_voice.py` importé par `model_manager.py`
- `model_manager.py` importé par `intent_classifier.py`
- → Import circulaire !

### Solution

**Import local** dans la méthode :

```python
def generate_acknowledgement(self, intent: str, query: str = "") -> str:
    # Import Intent ici pour éviter import circulaire
    try:
        from .intent_classifier import Intent
    except ImportError:
        # Fallback si Intent pas disponible
        Intent = None

    # Normaliser l'intent (accepte string ou enum)
    if Intent and hasattr(intent, 'value'):
        intent_str = intent.value
    else:
        intent_str = str(intent).lower()
```

**Avantages** :
- ✅ Évite import circulaire (import local)
- ✅ Accepte `Intent` enum ou string
- ✅ Fallback si Intent pas disponible

---

## Exemples de Flux

### Exemple 1 : Démarrage VM

```
[T+0ms]   User: "démarre preprod-09"

[T+50ms]  IntentClassifier → Intent.DEMANDE
          ↓
          LYRA.generate_acknowledgement(Intent.DEMANDE)
          ↓
          [AFFICHAGE IMMÉDIAT]
          LYRA: "D'accord, je regarde ça..."

[T+100ms] RAG → Specs vm_start
[T+500ms] EPHAISTOS → {"name": "vm_start", "arguments": {"vm_name": "preprod-09"}}
[T+1s]    HESTIA → Confirmation → User confirme "O"
[T+3s]    HESTIA → Exécution MCP
[T+5s]    LYRA.format_result()
          ↓
          [AFFICHAGE FINAL]
          LYRA: "Parfait ! La VM preprod-09 est démarrée. Son IP est 192.168.122.146."
```

---

### Exemple 2 : Question de connaissance

```
[T+0ms]   User: "c'est quoi vm_clone ?"

[T+50ms]  IntentClassifier → Intent.INFO
          ↓
          LYRA.generate_acknowledgement(Intent.INFO)
          ↓
          [AFFICHAGE IMMÉDIAT]
          LYRA: "Laisse-moi vérifier..."

[T+100ms] RAG → Specs vm_clone
[T+500ms] LYRA.answer_knowledge()
          ↓
          [AFFICHAGE FINAL]
          LYRA: "vm_clone crée une copie complète d'une VM existante. Ephaistos
                 m'indique que tous les disques sont dupliqués..."
```

---

### Exemple 3 : Discussion

```
[T+0ms]   User: "salut"

[T+50ms]  IntentClassifier → Intent.DISCUSSION
          ↓
          LYRA.generate_acknowledgement(Intent.DISCUSSION)
          ↓
          return ""  # Pas d'ack
          ↓
          LYRA.chat("salut")
          ↓
          [AFFICHAGE IMMÉDIAT]
          LYRA: "Bonjour ! Comment puis-je t'aider avec tes VMs et backups ?"
```

---

## Utilisation

### Dans le Pipeline

```python
from lyra.models.intent_classifier import Intent, IntentClassifier
from lyra.models.lyra_voice import LyraVoice

# Classification intention
classification = intent_classifier.classify(user_query)

# Générer ack immédiat
ack = lyra.generate_acknowledgement(
    intent=classification.intent,
    query=user_query
)

if ack:
    # Afficher immédiatement (callback)
    callback("acknowledgement", ack)

# Continuer traitement normal
result = pipeline.process(user_query)
```

---

### Avec Callback

```python
def on_progress(step: str, message: str):
    """Callback pour affichage progressif."""
    if step == "acknowledgement":
        print(f"{Fore.LIGHTBLUE_EX}{message}{Style.RESET_ALL}")
        # Optionnel: Piper TTS immédiat en mode vocal

# Appel pipeline
result = pipeline.process(user_query, callback=on_progress)
```

---

## Tests

### Test syntaxe Python

```bash
python -m py_compile lyra/models/lyra_voice.py
# ✅ Syntaxe OK
```

### Test acknowledgements

```python
from lyra.models.lyra_voice import LyraVoice
from lyra.models.intent_classifier import Intent

lyra = LyraVoice(manager, tts_mode=False)

# Test DEMANDE
ack_demande = lyra.generate_acknowledgement(Intent.DEMANDE)
assert ack_demande in [
    "D'accord, je regarde ça...",
    "Compris, je lance ça...",
    # ... etc
]

# Test INFO
ack_info = lyra.generate_acknowledgement(Intent.INFO)
assert ack_info in [
    "Laisse-moi vérifier...",
    "Je cherche l'info...",
    # ... etc
]

# Test DISCUSSION
ack_discussion = lyra.generate_acknowledgement(Intent.DISCUSSION)
assert ack_discussion == ""
```

---

## Avantages

### Expérience Utilisateur

✅ **Feedback immédiat** : User sait que LYRA a compris
✅ **Pas de silence** : Sensation de fluidité (comme J.A.R.V.I.S.)
✅ **Immersion** : LYRA semble "vivante" et réactive
✅ **Transparence** : User comprend que LYRA travaille en arrière-plan

### Technique

✅ **Non-bloquant** : Ack affiché pendant le traitement
✅ **Léger** : Pas d'appel LLM (templates pré-définis)
✅ **Adaptatif** : Ack différent selon intention
✅ **Optionnel** : Retourne "" si pas pertinent

---

## Comparaison Avant/Après

### Avant (Sans Acknowledgements)

```
User: "démarre preprod-09"
[Attente 2-3s sans feedback]
LYRA: "C'est fait, preprod-09 est démarrée."
```

**Problèmes** :
- ❌ Silence → impression de lag/bug
- ❌ User ne sait pas si LYRA a compris
- ❌ Pas immersif

---

### Après (Avec Acknowledgements)

```
User: "démarre preprod-09"
LYRA: "D'accord, je regarde ça..."  ← Immédiat (<100ms)
[Travail en arrière-plan]
LYRA: "Parfait ! La VM preprod-09 est démarrée."
```

**Avantages** :
- ✅ Feedback immédiat (<100ms)
- ✅ User sait que LYRA travaille
- ✅ Immersif (J.A.R.V.I.S.-like)

---

## Prochaine Étape

➡️ **Phase 3 : Pipeline Callback**
- Ajouter param `callback` à `Pipeline.process()`
- Appeler `generate_acknowledgement()` après classification
- Permettre affichage progressif (ack → résultat)

---

## Fichiers Modifiés

- ✅ `lyra/models/lyra_voice.py`

---

## Références

- **Issue** : Communication progressive LYRA
- **Phase précédente** : Phase 1 - Mode TTS
- **Phase suivante** : Phase 3 - Pipeline Callback
- **Date** : 2026-02-06
- **Auteur** : Claude Sonnet 4.5
