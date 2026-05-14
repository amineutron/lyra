# 🎨 Mermaid MCP Server

**Serveur MCP complet pour génération et affichage de diagrammes Mermaid avec validation automatique des bonnes pratiques.**

## 📋 Fonctionnalités

- ✅ **Génération de diagrammes** avec template HTML professionnel
- ✅ **Validation automatique** selon les 12 règles de bonnes pratiques
- ✅ **Légendes automatiques** pour couleurs et technologies
- ✅ **Stack technique** affichée automatiquement (modèles LLM, technos, VRAM...)
- ✅ **Modes d'affichage** : Ask / Always / Never
- ✅ **Gestion de session** pour préférences persistantes
- ✅ **Cache des diagrammes** générés
- ✅ **Export SVG/PNG** depuis le viewer HTML
- ✅ **Thèmes** : dark (défaut), light, forest, neutral

---

## 🚀 Installation

### 1. Prérequis

```bash
# Python 3.10+
python --version

# Installer les dépendances
pip install mcp
```

### 2. Configuration MCP

Ajouter dans `~/.config/claude-code/mcp_settings.json` :

```json
{
  "mcpServers": {
    "mermaid": {
      "command": "python",
      "args": ["/home/amineutron/dev/lyra/mcp-servers/mermaid-mcp/server.py"],
      "env": {}
    }
  }
}
```

### 3. Redémarrer Claude Code

```bash
# Relancer Claude Code pour charger le MCP
```

---

## 🛠️ Outils disponibles

| Outil | Description |
|-------|-------------|
| **generate_diagram** | Génère un diagramme Mermaid avec template, légende et validation |
| **show_diagram** | Affiche un diagramme précédemment généré |
| **set_display_mode** | Configure le mode d'affichage (ask/always/never) |
| **validate_diagram** | Valide un code Mermaid selon les 12 règles |
| **list_diagrams** | Liste tous les diagrammes de la session |

---

## 📖 Guide d'utilisation

### 1. Générer un diagramme simple

```python
# Via Claude Code MCP
{
  "tool": "generate_diagram",
  "arguments": {
    "mermaid_code": "graph LR\n  A[User] --> B[LYRA]\n  B --> C[MCP]",
    "title": "Architecture Lyra",
    "subtitle": "Flux simplifié"
  }
}
```

**Résultat** :
- ✅ Diagramme généré : `diagram_1`
- 📁 Fichier : `/tmp/mermaid_mcp/diagram_1.html`
- ❓ Mode ask : Demande si vous voulez afficher

### 2. Générer avec légende et stack technique

```python
{
  "tool": "generate_diagram",
  "arguments": {
    "mermaid_code": "graph LR\n  A[\"🎯 Intent<br/>(Llama 3B)\"] --> B[\"🤖 LYRA<br/>(Llama 3B)\"]\n  B --> C[\"🔌 MCP\"]",
    "title": "Architecture Lyra RAG V2",
    "subtitle": "Avec modèles LLM",
    "add_legend": true,
    "legend_colors": {
      "Intent": {"color": "#4ecdc4", "description": "Classification (Llama 3B)"},
      "LYRA": {"color": "#95e1d3", "description": "Dialogue (Llama 3B)"},
      "MCP": {"color": "#a29bfe", "description": "Serveurs externes"}
    },
    "tech_stack": {
      "Intent Classifier": "Llama 3.2 3B",
      "LYRA Frontend": "Llama 3.2 3B",
      "EPHAISTOS Backend": "Qwen 2.5 Coder 7B",
      "RAG": "ChromaDB + BM25",
      "STT": "faster-whisper (CUDA)"
    },
    "theme": "dark",
    "output_name": "lyra_archi_v2"
  }
}
```

**Résultat** :
- ✅ Diagramme avec légende colorée
- ✅ Section "Stack Technique" complète
- ✅ Boutons export SVG/PNG intégrés

### 3. Configurer le mode d'affichage

#### Mode "Always" (toujours afficher)

```python
{
  "tool": "set_display_mode",
  "arguments": {
    "mode": "always"
  }
}
```

✅ Les diagrammes s'ouvriront automatiquement dans le navigateur

#### Mode "Never" (jamais afficher)

```python
{
  "tool": "set_display_mode",
  "arguments": {
    "mode": "never"
  }
}
```

💤 Les diagrammes sont générés mais pas affichés (affichage manuel via `show_diagram`)

#### Mode "Ask" (demander à chaque fois) - DÉFAUT

```python
{
  "tool": "set_display_mode",
  "arguments": {
    "mode": "ask"
  }
}
```

❓ Demande à chaque génération si vous voulez afficher

### 4. Afficher un diagramme

```python
# Afficher le dernier diagramme généré
{
  "tool": "show_diagram",
  "arguments": {
    "diagram_id": "last"
  }
}

# Afficher un diagramme spécifique
{
  "tool": "show_diagram",
  "arguments": {
    "diagram_id": "diagram_3"
  }
}
```

### 5. Valider un diagramme

```python
{
  "tool": "validate_diagram",
  "arguments": {
    "mermaid_code": "graph LR\n  A[User] --> B[LYRA]"
  }
}
```

**Vérifie** :
- ✅ Direction du flux (LR recommandé)
- ✅ Nombre de nœuds (< 15)
- ✅ Présence de styles
- ✅ Longueur des labels
- ✅ Définition du thème
- ✅ Modèles LLM avec taille

**Retourne** :
```
## 📐 Validation du diagramme

### ⚠️ Avertissements (2)
- ⚠️ Aucun style défini (classDef). Considérez ajouter des couleurs pour la clarté.
- ⚠️ Aucun thème défini. Ajouter %%{init: {'theme':'dark'}}%%

📊 **Stats**: 2 nœud(s) détecté(s)
```

### 6. Lister les diagrammes

```python
{
  "tool": "list_diagrams",
  "arguments": {}
}
```

**Retourne** :
```
📚 **3 diagramme(s) disponible(s)**

- **diagram_1**
  📁 /tmp/mermaid_mcp/diagram_1.html

- **diagram_2**
  📁 /tmp/mermaid_mcp/diagram_2.html

- **diagram_3** ⭐ (dernier)
  📁 /tmp/mermaid_mcp/diagram_3.html

💡 Mode d'affichage actuel: **ask**
```

---

## 🎨 Exemples complets

### Exemple 1 : Architecture simple

```python
{
  "tool": "generate_diagram",
  "arguments": {
    "mermaid_code": """
%%{init: {'theme':'dark'}}%%
graph LR
    A[\"👤 User\"] --> B[\"🎯 Intent\"]
    B --> C[\"🤖 LYRA\"]
    C --> D[\"💭 Response\"]

    classDef inputStyle fill:#ff6b6b,stroke:#c92a2a,color:#fff
    classDef processStyle fill:#4ecdc4,stroke:#45b7d1,color:#fff
    classDef outputStyle fill:#fd79a8,stroke:#e84393,color:#fff

    class A inputStyle
    class B,C processStyle
    class D outputStyle
""",
    "title": "Flux Lyra Simplifié",
    "add_legend": true,
    "legend_colors": {
      "Input": {"color": "#ff6b6b", "description": "Utilisateur"},
      "Processing": {"color": "#4ecdc4", "description": "Intent, LYRA"},
      "Output": {"color": "#fd79a8", "description": "Réponse"}
    }
  }
}
```

### Exemple 2 : Architecture complète avec stack

```python
{
  "tool": "generate_diagram",
  "arguments": {
    "mermaid_code": """
%%{init: {'theme':'dark'}}%%
graph LR
    subgraph INPUT[\"🎤 INPUT\"]
        usr[\"👤 User\"]
        stt[\"🎙️ Whisper STT<br/>(faster-whisper CUDA)\"]
    end

    subgraph CORE[\"🧠 CORE\"]
        int[\"🎯 Intent<br/>(Llama 3.2 3B)\"]
        lyra[\"💬 LYRA<br/>(Llama 3B)\"]
        ephai[\"🔧 EPHAISTOS<br/>(Qwen 7B)\"]
    end

    subgraph MCP[\"🔌 MCP\"]
        hestia[\"⚙️ HESTIA\"]
        mcp[\"🌐 Servers\"]
    end

    usr --> int
    stt --> int
    int --> lyra
    int --> ephai
    ephai --> hestia
    hestia --> mcp
    mcp --> lyra

    classDef inputS fill:#ff6b6b,stroke:#c92a2a,color:#fff
    classDef coreS fill:#4ecdc4,stroke:#45b7d1,color:#fff
    classDef mcpS fill:#a29bfe,stroke:#6c5ce7,color:#fff

    class usr,stt inputS
    class int,lyra,ephai coreS
    class hestia,mcp mcpS
""",
    "title": "Architecture Lyra RAG V2",
    "subtitle": "Vue complète avec modèles et technologies",
    "add_legend": true,
    "legend_colors": {
      "Input": {"color": "#ff6b6b", "description": "User, Whisper STT"},
      "Core": {"color": "#4ecdc4", "description": "Intent, LYRA, EPHAISTOS"},
      "MCP": {"color": "#a29bfe", "description": "HESTIA, Serveurs"}
    },
    "tech_stack": {
      "Intent Classifier": "Llama 3.2 3B",
      "LYRA Frontend": "Llama 3.2 3B",
      "EPHAISTOS Backend": "Qwen 2.5 Coder 7B",
      "STT": "faster-whisper (CUDA)",
      "RAG": "ChromaDB + BM25",
      "Embeddings": "all-MiniLM-L6-v2"
    },
    "output_name": "lyra_complete"
  }
}
```

---

## 📥 Fonctionnalités d'export

Chaque diagramme généré inclut **3 boutons d'export** dans le viewer HTML :

### 1. 📥 Télécharger SVG

**Fonctionnalités** :
- Export vectoriel (qualité infinie, redimensionnable)
- Préserve tous les styles et couleurs
- Format léger et éditable
- Feedback visuel : "✅ Téléchargé !" pendant 2 secondes

**Usage** :
- Cliquer sur "📥 Télécharger SVG"
- Fichier téléchargé : `{output_name}.svg`
- Ouvrable avec : Inkscape, Illustrator, navigateurs

**Technique** :
- Clone le SVG avec attributs xmlns
- Sérialisation propre via XMLSerializer
- Blob avec charset UTF-8

### 2. 📸 Télécharger PNG

**Fonctionnalités** :
- Export bitmap haute qualité (2x scale)
- Fond dark automatique (#1e1e1e)
- Format universel pour présentations
- Feedback visuel : "✅ Téléchargé !" pendant 2 secondes

**Usage** :
- Cliquer sur "📸 Télécharger PNG"
- Fichier téléchargé : `{output_name}.png`
- Haute résolution (2x dimensions du SVG)

**Technique** :
- Canvas HTML5 avec scale 2x
- Conversion SVG → Image → Canvas → PNG
- Fond dark ajouté pour éviter transparence

### 3. 📋 Copier le code

**Fonctionnalités** :
- Copie le code Mermaid dans le presse-papiers
- API clipboard moderne + fallback
- Feedback visuel : "✅ Copié !" pendant 2 secondes

**Usage** :
- Cliquer sur "📋 Copier le code"
- Code disponible immédiatement (Ctrl+V)
- Compatible tous navigateurs

**Technique** :
- Navigator.clipboard API (moderne)
- Fallback execCommand pour vieux navigateurs
- Protection contre les erreurs

### Qualité des exports

| Format | Résolution | Taille fichier | Usage recommandé |
|--------|-----------|----------------|------------------|
| **SVG** | Vectoriel (∞) | ~50-200 KB | Documentation, web, édition |
| **PNG** | 2x (haute) | ~500KB-2MB | Présentations, rapports, impression |

### Exemple d'utilisation

```python
# Générer un diagramme
{
  "tool": "generate_diagram",
  "arguments": {
    "mermaid_code": "...",
    "output_name": "architecture_v2"  # Nom des exports
  }
}

# Résultat : 3 boutons disponibles dans le HTML
# 📥 → architecture_v2.svg
# 📸 → architecture_v2.png
# 📋 → Code Mermaid copié
```

---

## 🔧 Configuration avancée

### Personnaliser le template HTML

Le serveur utilise le template dans `docs/mermaid_template.html`. Vous pouvez le personnaliser :

```bash
cp docs/mermaid_template.html docs/my_template.html
# Modifier my_template.html...
```

Puis modifier `server.py` :
```python
self.viewer = MermaidViewer(template_path="docs/my_template.html")
```

### Changer le dossier de sortie

Par défaut : `/tmp/mermaid_mcp/`

Modifier dans `server.py` :
```python
output_path = Path(f"/home/amineutron/dev/lyra/diagrams/{diagram_id}.html")
```

---

## 📊 Validation automatique (12 règles)

Le validateur vérifie :

1. ✅ **Direction** : LR recommandé pour flux
2. ✅ **Complexité** : Max 15 nœuds
3. ✅ **Styles** : classDef présent si > 3 nœuds
4. ✅ **Labels** : < 20 caractères sur les liens
5. ✅ **Thème** : Défini via %%{init:}%%
6. ✅ **Modèles LLM** : Taille précisée (3B, 7B...)
7. ✅ **Couleurs** : Palette cohérente
8. ✅ **Emojis** : 1 par nœud max
9. ✅ **Sous-graphes** : Logiques et cohérents
10. ✅ **Contraste** : Lisibilité texte/fond
11. ✅ **Flèches** : Sémantique appropriée
12. ✅ **Légende** : Présente si pertinent

---

## 🎯 Intégration avec Lyra

### Dans un workflow Lyra

```python
from lyra.utils.mermaid_viewer import MermaidViewer

# Générer un diagramme depuis Lyra
def show_architecture():
    """Affiche l'architecture Lyra."""
    mermaid_code = """
    graph LR
        A[User] --> B[LYRA]
        B --> C[MCP]
    """

    viewer = MermaidViewer()
    viewer.generate(
        mermaid_code=mermaid_code,
        output_path="architecture.html",
        title="Architecture Lyra",
        open_browser=True
    )
```

### Via MCP depuis Lyra

```python
# Dans un outil MCP Lyra
@tool
def visualize_architecture():
    """Génère et affiche l'architecture Lyra."""
    # Appeler le MCP Mermaid
    result = call_mcp_tool(
        "mermaid",
        "generate_diagram",
        {
            "mermaid_code": "...",
            "title": "Architecture Lyra"
        }
    )
    return result
```

---

## 🚨 Troubleshooting

### Le serveur ne démarre pas

```bash
# Vérifier les dépendances
pip install mcp

# Vérifier Python
python --version  # 3.10+

# Tester manuellement
cd /home/amineutron/dev/lyra/mcp-servers/mermaid-mcp
python server.py
```

### Le diagramme ne s'affiche pas

- Vérifier le mode d'affichage : `list_diagrams`
- Changer le mode : `set_display_mode` → "always"
- Afficher manuellement : `show_diagram` → "last"

### Le navigateur ne s'ouvre pas

```bash
# Vérifier que firefox est installé
which firefox

# Ou utiliser chrome
export BROWSER=google-chrome
```

### Erreur de validation

Utiliser `validate_diagram` pour identifier les problèmes :
- Trop de nœuds → Diviser en plusieurs diagrammes
- Labels longs → Réduire à 1-3 mots
- Modèles sans taille → Ajouter (3B, 7B...)

---

## 📚 Ressources

- **Guide des bonnes pratiques** : `/home/amineutron/dev/lyra/docs/MERMAID_BEST_PRACTICES.md`
- **Template HTML** : `/home/amineutron/dev/lyra/docs/mermaid_template.html`
- **MermaidViewer Python** : `/home/amineutron/dev/lyra/lyra/utils/mermaid_viewer.py`
- **Mermaid Live Editor** : https://mermaid.live
- **Documentation Mermaid** : https://mermaid.js.org

---

## 📝 Changelog

### v1.0.1 (2026-02-06) - Export Fix
- 🔧 **Fix exports SVG/PNG** : Fonctionnent maintenant parfaitement
- ✨ **Feedback visuel** : "✅ Téléchargé !" / "✅ Copié !" sur les boutons
- 🎨 **PNG haute qualité** : Scale 2x + fond dark automatique
- 🛡️ **Robustesse** : Protection event.target + gestion d'erreurs
- 📖 **Documentation** : Section complète sur les exports

### v1.0.0 (2026-02-06) - Initial Release
- ✅ Génération de diagrammes avec template
- ✅ Validation automatique (12 règles)
- ✅ Modes d'affichage (ask/always/never)
- ✅ Légendes et stack technique
- ✅ Cache de session
- ✅ Export SVG/PNG (basique)

---

## 🤝 Contribution

Pour améliorer le serveur MCP Mermaid :

1. Modifier `server.py`
2. Tester avec Claude Code
3. Mettre à jour cette documentation
4. Ajouter des exemples

---

## 📜 Licence

MIT License - Fait avec ❤️ pour Lyra

---

**Auteur** : Lyra Team
**Version** : 1.0.0
**Date** : 2026-02-06
