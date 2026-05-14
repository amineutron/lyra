# 🎨 Mermaid Fancy Template

Template HTML premium pour générer des diagrammes Mermaid avec style dark fancy pour Lyra.

## 📦 Contenu

```
docs/
├── mermaid_template_fancy.html       # Template HTML (utilisé par MermaidViewer)
├── exemple_mermaid_fancy.py          # Exemple complet Architecture Lyra V2
└── MERMAID_FANCY_README.md           # Ce fichier
```

## 🚀 Utilisation Rapide

### Option 1: Utiliser l'exemple Lyra

```bash
cd /home/amineutron/dev/lyra
python docs/exemple_mermaid_fancy.py
```

✅ Génère automatiquement `docs/architecture_lyra_v2_fancy.html` et l'ouvre dans le navigateur

### Option 2: Créer ton propre diagramme

```python
from lyra.utils.mermaid_viewer import MermaidViewer

# Initialiser avec le template fancy
viewer = MermaidViewer(template_path="docs/mermaid_template_fancy.html")

# Code Mermaid (TOUJOURS utiliser graph LR pour horizontal!)
mermaid_code = """
graph LR
    A["👤 USER<br/>INPUT"] --> B["🧠 Process"]
    B --> C["👤 USER<br/>OUTPUT"]

    classDef userClass fill:#ff6b6b,stroke:#c92a2a,stroke-width:3px,color:#fff
    class A,C userClass
"""

# Créer une légende (optionnel)
legend = viewer.create_legend({
    "User": {"color": "#ff6b6b", "description": "Entrée/Sortie"}
})

# Créer des sections info (optionnel)
info = viewer.create_info_section(
    "💡 Détails",
    "<p>Description de ton diagramme...</p>"
)

extra_content = legend + info

# Générer le HTML
viewer.generate(
    mermaid_code=mermaid_code,
    output_path="mon_diagramme.html",
    title="Mon Diagramme",
    subtitle="Description courte",
    theme="dark",
    extra_content=extra_content,
    filename="mon_diagramme",
    open_browser=True
)
```

## 🎯 Bonnes Pratiques

### ✅ DO (À faire)

1. **Toujours utiliser `graph LR`** (Left to Right)
   ```mermaid
   graph LR
       START["🚀 Début"] --> END["✅ Fin"]
   ```

2. **USER au début et à la fin** pour le flux
   ```mermaid
   graph LR
       USER_IN["👤 INPUT"] --> PROCESS["⚙️ Process"]
       PROCESS --> USER_OUT["👤 OUTPUT"]
   ```

3. **Utiliser des classDef pour les couleurs**
   ```mermaid
   classDef importantClass fill:#ff6b6b,stroke:#c92a2a,stroke-width:3px
   class NODE1,NODE2 importantClass
   ```

4. **Ajouter des emojis** pour la clarté visuelle
   ```mermaid
   A["🔍 Search"] --> B["✅ Result"]
   ```

5. **Stroke épais pour les nœuds importants**
   ```mermaid
   classDef keyNode fill:#4ecdc4,stroke:#45b7d1,stroke-width:3px
   ```

### ❌ DON'T (À éviter)

1. ❌ **Ne PAS utiliser `graph TB`** (Top to Bottom) - difficile à lire
2. ❌ **Ne PAS mettre trop de nœuds** (max 15-20)
3. ❌ **Ne PAS utiliser des labels trop longs** (max 3 lignes par nœud)
4. ❌ **Ne PAS oublier les styles** - les couleurs sont importantes
5. ❌ **Ne PAS oublier de fermer les guillemets** dans les labels

## 🎨 Palette de Couleurs Recommandées

| Couleur | Hex | Usage |
|---------|-----|-------|
| **Rouge** | `#ff6b6b` | Utilisateur, entrée/sortie |
| **Turquoise** | `#4ecdc4` | Backend, analyse |
| **Vert** | `#95e1d3` | Frontend, dialogue |
| **Orange** | `#feca57` | MCP, outils |
| **Violet** | `#aa96da` | RAG, recherche |
| **Rose** | `#f38181` | Exécution, actions |
| **Jaune** | `#fdcb6e` | Classification, routing |
| **Bleu** | `#74b9ff` | Session, mémoire |
| **Pêche** | `#fab1a0` | Audio, I/O |

## 📊 Structure Recommandée

```python
# 1. Code Mermaid (graph LR)
mermaid_code = """..."""

# 2. Légende des couleurs
legend = viewer.create_legend({...})

# 3. Informations supplémentaires (tableaux, stats, etc.)
info1 = viewer.create_info_section("Titre", "<table>...</table>")
info2 = viewer.create_info_section("Autre", "<ul>...</ul>")

# 4. Combiner
extra_content = legend + info1 + info2

# 5. Générer
viewer.generate(...)
```

## 🔧 Fonctionnalités du Template

### Boutons Automatiques

- **📥 Télécharger SVG** - Export vectoriel (qualité infinie)
- **📸 Télécharger PNG** - Export bitmap (2x resolution)
- **📋 Copier le code** - Copie le code Mermaid dans le presse-papier

### Styles Fancy

- ✅ Gradient dark background (`#1a1a2e → #16213e`)
- ✅ Bordures glowing (rgba avec transparence)
- ✅ Hover effects sur les boutons
- ✅ Animation au chargement (fadeIn)
- ✅ Responsive design (mobile-friendly)
- ✅ Scroll horizontal hint pour les grands diagrammes

### Sections Info Automatiques

- `.info` - Blocs d'information avec bordure cyan
- `table` - Tableaux stylés avec hover
- `.legend` - Grille responsive pour la légende des couleurs
- `.actions` - Boutons d'export stylés

## 💡 Exemples de Diagrammes

### Exemple 1: Flux Simple

```python
mermaid_code = """
graph LR
    A["👤 User"] --> B["🔍 Search"]
    B --> C["📊 Results"]
    C --> D["👤 User"]

    classDef userClass fill:#ff6b6b,stroke:#c92a2a,stroke-width:3px
    class A,D userClass
"""
```

### Exemple 2: Pipeline de Données

```python
mermaid_code = """
graph LR
    INPUT["📥 Input"] --> VALIDATE["✔️ Validate"]
    VALIDATE --> PROCESS["⚙️ Process"]
    PROCESS --> SAVE["💾 Save"]
    SAVE --> OUTPUT["📤 Output"]

    classDef inputClass fill:#a29bfe
    classDef processClass fill:#4ecdc4
    classDef outputClass fill:#95e1d3

    class INPUT inputClass
    class VALIDATE,PROCESS processClass
    class SAVE,OUTPUT outputClass
"""
```

### Exemple 3: Architecture avec Branches

```python
mermaid_code = """
graph LR
    START["🚀 Start"] --> CHECK{"Type?"}
    CHECK -->|A| PATH_A["🔵 Process A"]
    CHECK -->|B| PATH_B["🟢 Process B"]
    PATH_A --> END["✅ End"]
    PATH_B --> END

    classDef startClass fill:#ff6b6b,stroke-width:3px
    classDef endClass fill:#95e1d3,stroke-width:3px

    class START startClass
    class END endClass
"""
```

## 🐛 Troubleshooting

### Le diagramme ne s'affiche pas

1. Vérifier que le code Mermaid est valide
2. Ouvrir la console du navigateur (F12) pour voir les erreurs
3. Vérifier que tous les guillemets sont fermés

### Les couleurs ne s'appliquent pas

1. Vérifier que `classDef` est bien défini
2. Vérifier que `class NODE_NAME className` est présent
3. Les noms de classes doivent correspondre exactement

### Le fichier HTML est vide

1. Vérifier que le template existe: `ls docs/mermaid_template_fancy.html`
2. Vérifier les permissions: `chmod +r docs/mermaid_template_fancy.html`

### Le navigateur ne s'ouvre pas

1. Désactiver `open_browser=False` dans `viewer.generate()`
2. Ouvrir manuellement: `xdg-open fichier.html`

## 📝 Notes Importantes

- Le template est optimisé pour **dark theme** uniquement
- Les diagrammes sont **non interactifs** (pas de zoom/pan dans Mermaid, utiliser le navigateur)
- Les exports PNG ont un **fond dark** (`#1a1a2e`) automatique
- Le scroll horizontal est **automatique** si le diagramme est trop large
- Les **emojis** fonctionnent dans tous les navigateurs modernes

## 🚀 Tips Pro

1. **Utiliser `<br/>` pour les retours à la ligne** dans les labels
2. **3 lignes max par nœud** pour la lisibilité
3. **Stroke-width:3px** pour les nœuds clés (USER, OUTPUT, etc.)
4. **Grouper par couleur** les composants similaires
5. **Ajouter des légendes** pour expliquer les couleurs
6. **Tableaux pour les specs techniques** (VRAM, outils, etc.)
7. **Utiliser des labels courts** (3-5 mots max)

## 📚 Ressources

- [Mermaid Documentation](https://mermaid.js.org/)
- [Mermaid Live Editor](https://mermaid.live/) - Pour tester le code
- [Template Original](mermaid_template.html) - Version simple
- [Exemple Complet](exemple_mermaid_fancy.py) - Architecture Lyra V2

---

**Créé pour Lyra V2 | 2026-02-06**
