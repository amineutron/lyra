# Phase 1 : Mode TTS - Documentation

**Date** : 2026-02-06
**Statut** : ✅ Terminée

---

## Objectif

Adapter les réponses de LYRA selon le mode d'utilisation :
- **Mode TTS (vocal)** : Réponses courtes (1-2 phrases), sans acronymes, optimisées pour Piper TTS
- **Mode TEXT (texte)** : Réponses détaillées (2-4 phrases), expressives, immersives

---

## Changements Apportés

### 1. Nouveaux System Prompts

#### `LYRA_SYSTEM_PROMPT_TTS` (Mode Vocal)

```python
LYRA_SYSTEM_PROMPT_TTS = """Tu es LYRA, une assistante vocale DevOps amicale.

PERSONNALITE:
- Chaleureuse et professionnelle, jamais robotique
- Reponds en francais avec un ton naturel et conversationnel
- Tu travailles avec EPHAISTOS et HESTIA

REGLES TTS:
- ZERO emoji
- Phrases courtes et claires
- Evite les acronymes: "machine virtuelle" pas "VM"
- Maximum 2 phrases par reponse

EXEMPLES:
- "C'est fait, preprod-09 est demarree. Son IP est 192.168.122.146."
- "Il y a eu un souci avec la connexion. On peut reessayer si tu veux."
"""
```

**Caractéristiques** :
- ✅ Court et direct
- ✅ Facile à prononcer (Piper TTS)
- ✅ Sans acronymes
- ✅ 1-2 phrases max

---

#### `LYRA_SYSTEM_PROMPT_TEXT` (Mode Texte)

```python
LYRA_SYSTEM_PROMPT_TEXT = """Tu es LYRA, une assistante DevOps chaleureuse et expressive.

PERSONNALITE:
- Naturelle et conviviale, jamais robotique
- Reponds en francais avec un ton conversationnel et immersif
- Mentionne EPHAISTOS/HESTIA pour creer de l'immersion (comme J.A.R.V.I.S.)
- Utilise expressions naturelles: "Super !", "Parfait !", "Pas de souci", "Ah mince"

REGLES TEXTE:
- ZERO emoji (toujours)
- Reponses detaillees: 2-4 phrases OK
- Acronymes OK: VM, IP, SSH, etc.
- Donne du contexte et infos supplementaires

EXEMPLES:
- "Parfait ! La VM preprod-09 est demarree. Son IP est 192.168.122.146,
   elle a 4 Go de RAM et 2 vCPUs. Tu peux t'y connecter via SSH."
- "Ah mince, j'ai rencontre un souci avec la connexion. L'erreur dit que
   le timeout est expire (le reseau repond pas). Hestia suggere de verifier
   que la VM est bien allumee, ou on peut reessayer si tu veux?"

MENTIONS DES COLLEGUES (FREQUENT pour immersion):
- "Ephaistos m'indique que..." (30% du temps)
- "Hestia vient de terminer..." (20% du temps)
- "Hestia a rencontre un souci..." (40% sur erreur)
"""
```

**Caractéristiques** :
- ✅ Détaillé et informatif
- ✅ Expressif et immersif
- ✅ Acronymes autorisés
- ✅ 2-4 phrases
- ✅ Mentionne EPHAISTOS/HESTIA plus souvent

---

### 2. Propriétés Adaptatives

#### `__init__(self, model_manager, tts_mode=False)`

Nouveau paramètre `tts_mode` pour activer le mode vocal.

```python
def __init__(self, model_manager: ModelManager, tts_mode: bool = False):
    self.model_manager = model_manager
    self.tts_mode = tts_mode
```

---

#### `max_sentences` (property)

```python
@property
def max_sentences(self) -> int:
    """Nombre max de phrases selon le mode.

    TTS: 2 phrases max (clair et rapide)
    TEXT: 4 phrases max (detaille et immersif)
    """
    return 2 if self.tts_mode else 4
```

**Utilisation** :
- Mode TTS : "Resume en 2 phrases"
- Mode TEXT : "Resume en 4 phrases"

---

#### `system_prompt` (property)

```python
@property
def system_prompt(self) -> str:
    """System prompt adaptatif selon le mode."""
    return LYRA_SYSTEM_PROMPT_TTS if self.tts_mode else LYRA_SYSTEM_PROMPT_TEXT
```

**Utilisation** :
- Remplace toutes les références à `LYRA_SYSTEM_PROMPT` (constante unique)
- Toutes les méthodes utilisent maintenant `self.system_prompt`

---

#### `mention_prob_ephaistos` (property)

```python
@property
def mention_prob_ephaistos(self) -> float:
    """Probabilite de mentionner EPHAISTOS selon le mode.

    TTS: 20% (modere)
    TEXT: 30% (plus frequent pour immersion)
    """
    return 0.20 if self.tts_mode else 0.30
```

**Impact** :
- Mode TEXT : Plus de mentions d'EPHAISTOS → plus d'immersion
- Mode TTS : Modéré pour ne pas alourdir

---

#### `mention_prob_hestia_error` (property)

```python
@property
def mention_prob_hestia_error(self) -> float:
    """Probabilite de mentionner HESTIA sur erreur.

    TTS: 20% (modere)
    TEXT: 40% (plus frequent pour immersion)
    """
    return 0.20 if self.tts_mode else 0.40
```

**Impact** :
- Mode TEXT : Plus de mentions d'HESTIA sur erreur → contexte technique
- Mode TTS : Modéré pour rester concis

---

#### `mention_prob_hestia_if_ephaistos` (property)

```python
@property
def mention_prob_hestia_if_ephaistos(self) -> float:
    """Probabilite de mentionner HESTIA si EPHAISTOS mentionne.

    TTS: 50% (modere)
    TEXT: 50% (identique, cascade naturelle)
    """
    return 0.50
```

**Impact** :
- Identique pour les deux modes (cascade naturelle)

---

### 3. Méthodes Adaptées

#### `ask_clarification()`

**Avant** :
```python
mention_ephaistos = random.random() < self.EPHAISTOS_MENTION_PROB
```

**Après** :
```python
mention_ephaistos = random.random() < self.mention_prob_ephaistos
```

---

#### `format_result()`

**Avant** :
```python
prompt = f"""Resume ce resultat d'execution en 1-2 phrases."""
```

**Après** :
```python
max_sentences_str = f"{self.max_sentences} phrases" if self.max_sentences > 1 else "1 phrase"
prompt = f"""Resume ce resultat d'execution en {max_sentences_str}."""
```

**Impact** :
- Mode TTS : "Resume en 2 phrases"
- Mode TEXT : "Resume en 4 phrases" → plus de détails

---

#### `answer_knowledge()`

**Avant** :
```python
prompt = f"""Reponds a cette question de maniere concise."""
```

**Après** :
```python
style = "concise" if self.tts_mode else "detaillee et utile"
prompt = f"""Reponds a cette question de maniere {style}."""
```

**Impact** :
- Mode TTS : Réponse concise
- Mode TEXT : Réponse détaillée avec contexte

---

#### `format_error()`

**Avant** :
```python
prompt = f"""Reformule en 1-2 phrases (SANS emoji):"""
mention_hestia = random.random() < self.HESTIA_MENTION_ON_ERROR
```

**Après** :
```python
max_sentences_str = f"{self.max_sentences} phrases"
prompt = f"""Reformule en {max_sentences_str} (SANS emoji):"""
mention_hestia = random.random() < self.mention_prob_hestia_error
```

---

### 4. Constantes Supprimées

**Avant** :
```python
EPHAISTOS_MENTION_PROB = 0.20
HESTIA_MENTION_IF_EPHAISTOS = 0.50
HESTIA_MENTION_ON_ERROR = 0.20
```

**Après** :
- ❌ Constantes supprimées
- ✅ Remplacées par propriétés adaptatives

---

## Comparaison Modes

| Aspect | Mode TTS (Vocal) | Mode TEXT (Texte) |
|--------|------------------|-------------------|
| **Phrases max** | 2 | 4 |
| **Acronymes** | ❌ Non ("machine virtuelle") | ✅ Oui ("VM") |
| **Mentions EPHAISTOS** | 20% | 30% |
| **Mentions HESTIA (erreur)** | 20% | 40% |
| **Style** | Concis, clair | Détaillé, immersif |
| **Expressions** | Formelles | Naturelles ("Super !", "Ah mince") |
| **Contexte technique** | Essentiel | Enrichi (RAM, CPU, chemins) |

---

## Exemples de Réponses

### Exemple 1 : Démarrage VM réussi

**Mode TTS** :
```
"C'est fait, preprod-09 est demarree. Son IP est 192.168.122.146."
```

**Mode TEXT** :
```
"Parfait ! La VM preprod-09 est demarree. Son IP est 192.168.122.146,
elle a 4 Go de RAM et 2 vCPUs. Tu peux t'y connecter via SSH avec
ton compte habituel."
```

---

### Exemple 2 : Erreur de connexion

**Mode TTS** :
```
"Il y a eu un souci avec la connexion. On peut reessayer si tu veux."
```

**Mode TEXT** :
```
"Ah mince, j'ai rencontre un souci avec la connexion au serveur.
L'erreur dit que le timeout est expire (le reseau repond pas).
Hestia suggere de verifier que la machine virtuelle est bien allumee,
ou on peut reessayer si tu veux?"
```

---

### Exemple 3 : Question de connaissance

**Requête** : "C'est quoi vm_clone ?"

**Mode TTS** :
```
"vm_clone cree une copie complete d'une machine virtuelle.
Tous les disques sont dupliques."
```

**Mode TEXT** :
```
"vm_clone cree une copie complete d'une machine virtuelle existante.
Ephaistos m'indique que tous les disques sont dupliques en mode
independant (pas de snapshot lie). Tu peux demarrer le clone
automatiquement avec l'option --start. Utile pour faire des tests
sans toucher a la machine de production."
```

---

## Utilisation

### Initialisation

```python
from lyra.models.model_manager import ModelManager
from lyra.models.lyra_voice import LyraVoice
from lyra.core.config import RAGConfig

config = RAGConfig.from_yaml('config.yaml')
manager = ModelManager(config)

# Mode TEXT (par défaut)
lyra_text = LyraVoice(manager, tts_mode=False)

# Mode TTS (vocal)
lyra_tts = LyraVoice(manager, tts_mode=True)
```

### Appel

```python
# Mode TEXT
response = lyra_text.format_result(
    tool_name="vm_start",
    result="VM preprod-09 started (IP: 192.168.122.146)",
    success=True
)
# → Réponse détaillée (2-4 phrases)

# Mode TTS
response = lyra_tts.format_result(
    tool_name="vm_start",
    result="VM preprod-09 started (IP: 192.168.122.146)",
    success=True
)
# → Réponse concise (1-2 phrases)
```

---

## Tests

### Test syntaxe Python

```bash
python -m py_compile lyra/models/lyra_voice.py
# ✅ Syntaxe OK
```

### Test propriétés

```python
lyra_tts = LyraVoice(manager, tts_mode=True)
assert lyra_tts.max_sentences == 2
assert lyra_tts.mention_prob_ephaistos == 0.20
assert lyra_tts.mention_prob_hestia_error == 0.20

lyra_text = LyraVoice(manager, tts_mode=False)
assert lyra_text.max_sentences == 4
assert lyra_text.mention_prob_ephaistos == 0.30
assert lyra_text.mention_prob_hestia_error == 0.40
```

---

## Prochaine Étape

➡️ **Phase 2 : Acknowledgements**
- Ajouter `generate_acknowledgement()` pour feedback immédiat
- Créer templates d'acks par intention (demande/info/discussion)

---

## Fichiers Modifiés

- ✅ `lyra/models/lyra_voice.py`

---

## Références

- **Issue** : Communication progressive LYRA
- **Date** : 2026-02-06
- **Auteur** : Claude Sonnet 4.5
