# 🎨 Mermaid Viewer - Guide d'utilisation

Système de template pour générer des visualiseurs HTML interactifs à partir de diagrammes Mermaid.

## 📁 Fichiers

| Fichier | Description |
|---------|-------------|
| `docs/mermaid_template.html` | Template HTML avec placeholders |
| `lyra/utils/mermaid_viewer.py` | Classe Python pour générer les HTML |
| `scripts/mermaid_render.py` | CLI pour utilisation rapide |

## 🚀 Utilisation rapide (CLI)

### Depuis un fichier .mmd

```bash
# Générer un HTML depuis un fichier Mermaid
python scripts/mermaid_render.py diagram.mmd -o output.html

# Avec titre et ouverture auto dans le navigateur
python scripts/mermaid_render.py diagram.mmd \
    --title "Mon Architecture" \
    --subtitle "Version 2.0" \
    --open

# Thème clair
python scripts/mermaid_render.py diagram.mmd --theme light -o output.html
```

### Code inline

```bash
# Passer le code Mermaid directement
python scripts/mermaid_render.py "graph LR; A-->B; B-->C" -o simple.html --open
```

## 💻 Utilisation Python (pour intégration MCP)

### Exemple basique

```python
from lyra.utils.mermaid_viewer import MermaidViewer

viewer = MermaidViewer()

mermaid_code = """
graph LR
    A[User] --> B[Intent]
    B --> C[LYRA]
"""

viewer.generate(
    mermaid_code=mermaid_code,
    output_path="output.html",
    title="Mon Diagramme",
    open_browser=True
)
```

### Exemple avec légende

```python
from lyra.utils.mermaid_viewer import MermaidViewer

viewer = MermaidViewer()

# Code Mermaid
mermaid_code = """
%%{init: {'theme':'dark'}}%%
graph LR
    A[User] --> B[LYRA]
    B --> C[MCP]

    classDef userStyle fill:#ff6b6b
    classDef lyraStyle fill:#4ecdc4
    classDef mcpStyle fill:#a29bfe

    class A userStyle
    class B lyraStyle
    class C mcpStyle
"""

# Créer une légende
colors = {
    "User": {"color": "#ff6b6b", "description": "Utilisateur"},
    "LYRA": {"color": "#4ecdc4", "description": "Assistant IA"},
    "MCP": {"color": "#a29bfe", "description": "Serveurs MCP"}
}

legend = viewer.create_legend(colors)

# Ajouter des infos supplémentaires
info = viewer.create_info_section(
    title="Ressources VRAM",
    content="""
    <ul>
        <li><strong>LYRA</strong>: ~2.5 GB</li>
        <li><strong>EPHAISTOS</strong>: ~5 GB</li>
    </ul>
    """,
    icon="💾"
)

extra_content = legend + info

# Générer
viewer.generate(
    mermaid_code=mermaid_code,
    output_path="architecture.html",
    title="Architecture Lyra",
    subtitle="Version RAG V2",
    extra_content=extra_content,
    filename="lyra_archi",
    open_browser=True
)
```

## 🎯 Intégration MCP

Pour intégrer dans un serveur MCP qui affiche des diagrammes :

```python
from lyra.utils.mermaid_viewer import MermaidViewer
import tempfile
import webbrowser

def show_mermaid_diagram(mermaid_code: str, title: str = "Diagramme"):
    """Affiche un diagramme Mermaid dans le navigateur."""
    viewer = MermaidViewer()

    # Créer un fichier temporaire
    with tempfile.NamedTemporaryFile(
        mode='w',
        suffix='.html',
        delete=False,
        encoding='utf-8'
    ) as f:
        output_path = f.name

    # Générer et ouvrir
    viewer.generate(
        mermaid_code=mermaid_code,
        output_path=output_path,
        title=title,
        open_browser=True
    )

    return output_path

# Utilisation dans un outil MCP
@tool
def visualize_architecture():
    """Affiche l'architecture Lyra."""
    mermaid_code = """
    graph LR
        A[User] --> B[LYRA]
    """

    path = show_mermaid_diagram(mermaid_code, "Architecture Lyra")
    return f"Diagramme affiché: {path}"
```

## 🎨 Template personnalisé

Tu peux créer ton propre template en copiant `docs/mermaid_template.html` :

```bash
cp docs/mermaid_template.html docs/my_template.html
# Modifier my_template.html...
```

Puis l'utiliser :

```python
viewer = MermaidViewer(template_path="docs/my_template.html")
viewer.generate(...)
```

## 📦 Placeholders disponibles

Dans le template `mermaid_template.html` :

| Placeholder | Description |
|-------------|-------------|
| `{{TITLE}}` | Titre de la page |
| `{{SUBTITLE}}` | Sous-titre |
| `{{THEME}}` | Thème Mermaid (dark/light/etc) |
| `{{MERMAID_CODE}}` | Code du diagramme |
| `{{EXTRA_CONTENT}}` | HTML additionnel (légende, infos) |
| `{{FILENAME}}` | Nom pour exports SVG/PNG |

## ✨ Fonctionnalités du viewer HTML

Le HTML généré inclut automatiquement :

- 📥 **Export SVG** : Télécharge le diagramme en SVG
- 📸 **Export PNG** : Télécharge en image PNG
- 📋 **Copier code** : Copie le code Mermaid dans le presse-papiers
- 🎨 **Thème dark** par défaut
- 📱 **Responsive** : S'adapte à toutes les tailles d'écran

## 🔧 Thèmes Mermaid disponibles

- `dark` (défaut)
- `light`
- `forest`
- `neutral`
- `base`

## 📝 Formats de fichiers supportés

En entrée :
- `.mmd` (recommandé)
- `.mermaid`
- `.txt`
- Code inline (string)

En sortie :
- `.html` (viewer interactif)
- Exports depuis le HTML : `.svg`, `.png`

## 🚨 Troubleshooting

### Le diagramme ne s'affiche pas

- Vérifier la syntaxe Mermaid sur https://mermaid.live
- Vérifier que le CDN Mermaid est accessible (connexion Internet)

### Les couleurs ne s'appliquent pas

- Utiliser `classDef` dans le code Mermaid
- Vérifier les noms de classes avec `class NodeName styleName`

### Le fichier ne s'ouvre pas automatiquement

- Vérifier que `firefox` ou `google-chrome` est dans le PATH
- Ouvrir manuellement : `firefox output.html`

## 💡 Exemples

Voir les exemples dans :
- `docs/architecture_viewer.html` (Architecture Lyra complète)
- `lyra/utils/mermaid_viewer.py` (fonction `main()`)

---

**Fait avec ❤️ pour Lyra**
