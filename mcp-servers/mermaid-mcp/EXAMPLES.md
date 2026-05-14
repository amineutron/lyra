# 📚 Exemples d'utilisation - Mermaid MCP

Collection d'exemples pratiques pour le serveur MCP Mermaid.

---

## 🎯 Cas d'usage 1 : Documentation d'architecture

### Objectif
Documenter l'architecture Lyra pour un nouveau développeur.

### Workflow

```python
# 1. Configurer le mode always pour génération rapide
{
  "tool": "set_display_mode",
  "arguments": {"mode": "always"}
}

# 2. Générer la vue globale
{
  "tool": "generate_diagram",
  "arguments": {
    "mermaid_code": """
graph LR
    A[\"👤 User\"] --> B[\"🎯 Intent Classifier\"]
    B -->|demande| C[\"⚡ RAG Pipeline\"]
    B -->|info| D[\"💬 LYRA Dialogue\"]
    C --> E[\"🔌 MCP Servers\"]
    E --> D
    D --> F[\"💭 Response\"]
""",
    "title": "Architecture Lyra - Vue Globale",
    "subtitle": "Pour nouveaux développeurs",
    "add_legend": true,
    "legend_colors": {
      "Input": {"color": "#ff6b6b", "description": "Entrée utilisateur"},
      "Processing": {"color": "#4ecdc4", "description": "Traitement et classification"},
      "Action": {"color": "#feca57", "description": "Pipeline RAG"},
      "External": {"color": "#a29bfe", "description": "Serveurs MCP"},
      "Output": {"color": "#fd79a8", "description": "Réponse finale"}
    },
    "output_name": "architecture_overview"
  }
}

# 3. Générer la vue détaillée du RAG Pipeline
{
  "tool": "generate_diagram",
  "arguments": {
    "mermaid_code": """
graph LR
    subgraph RAG[\"🔍 RAG Pipeline\"]
        semantic[\"Semantic Search<br/>(ChromaDB)\"]
        keyword[\"Keyword Search<br/>(BM25)\"]
        fusion[\"RRF Fusion\"]
        toon[\"📦 TOON<br/>Encoder\"]
    end

    input[\"Query\"] --> semantic
    input --> keyword
    semantic --> fusion
    keyword --> fusion
    fusion --> toon
    toon --> output[\"Specs MCP\"]
""",
    "title": "RAG Pipeline - Détail",
    "subtitle": "Recherche hybride semantic + keyword",
    "add_legend": true,
    "legend_colors": {
      "Search": {"color": "#4ecdc4", "description": "Semantic + Keyword"},
      "Processing": {"color": "#feca57", "description": "Fusion + Encoding"}
    },
    "tech_stack": {
      "Semantic Search": "ChromaDB (all-MiniLM-L6-v2)",
      "Keyword Search": "BM25 (rank-bm25)",
      "Fusion": "RRF (Reciprocal Rank Fusion)",
      "Encoder": "TOON (~40% compression)"
    },
    "output_name": "rag_pipeline_detail"
  }
}

# 4. Lister tous les diagrammes générés
{
  "tool": "list_diagrams",
  "arguments": {}
}
```

**Résultat** : 2 diagrammes complémentaires pour la documentation complète.

---

## 🎯 Cas d'usage 2 : Debugging d'un flux

### Objectif
Identifier un problème dans le flux de traitement.

### Workflow

```python
# 1. Mode ask pour validation manuelle
{
  "tool": "set_display_mode",
  "arguments": {"mode": "ask"}
}

# 2. Créer un diagramme du flux actuel (avec bug)
{
  "tool": "generate_diagram",
  "arguments": {
    "mermaid_code": """
graph LR
    A[\"User Query\"] --> B[\"Intent\"]
    B --> C[\"EPHAISTOS\"]
    C --> D[\"MCP\"]
    D --x E[\"Error Handler\"]
    E -.-> C
    C --> F[\"LYRA\"]
""",
    "title": "Flux avec Bug",
    "subtitle": "Boucle infinie détectée entre EPHAISTOS et Error Handler",
    "output_name": "flux_bug"
  }
}

# 3. Valider le diagramme
{
  "tool": "validate_diagram",
  "arguments": {
    "mermaid_code": """
graph LR
    A[\"User Query\"] --> B[\"Intent\"]
    B --> C[\"EPHAISTOS\"]
    C --> D[\"MCP\"]
    D --x E[\"Error Handler\"]
    E -.-> C
    C --> F[\"LYRA\"]
"""
  }
}

# 4. Créer le diagramme corrigé
{
  "tool": "generate_diagram",
  "arguments": {
    "mermaid_code": """
graph LR
    A[\"User Query\"] --> B[\"Intent\"]
    B --> C[\"EPHAISTOS\"]
    C --> D[\"MCP\"]
    D -->|Succès| E[\"LYRA\"]
    D --x F[\"Error Handler\"]
    F --> E
""",
    "title": "Flux Corrigé",
    "subtitle": "Error Handler renvoie directement à LYRA",
    "output_name": "flux_fixed"
  }
}

# 5. Comparer les deux
{
  "tool": "list_diagrams",
  "arguments": {}
}
```

**Résultat** : Identification et correction du flux.

---

## 🎯 Cas d'usage 3 : Présentation pour stakeholders

### Objectif
Créer des diagrammes pour une présentation business.

### Workflow

```python
# 1. Mode always pour rapidité
{
  "tool": "set_display_mode",
  "arguments": {"mode": "always"}
}

# 2. Diagramme ultra-simplifié (5 nœuds max)
{
  "tool": "generate_diagram",
  "arguments": {
    "mermaid_code": """
%%{init: {'theme':'light'}}%%
graph LR
    A[\"👤 Utilisateur\"] --> B[\"🤖 Lyra AI\"]
    B --> C[\"☁️ Cloud Services\"]
    C --> B
    B --> D[\"✅ Résultat\"]

    classDef clean fill:#4ecdc4,stroke:#45b7d1,stroke-width:3px,color:#fff
    class A,B,C,D clean
""",
    "title": "Lyra - Vue Business",
    "subtitle": "Assistant IA pour DevOps",
    "theme": "light",
    "add_legend": false,
    "output_name": "business_view"
  }
}

# 3. Ajouter les bénéfices
{
  "tool": "generate_diagram",
  "arguments": {
    "mermaid_code": """
%%{init: {'theme':'light'}}%%
graph TB
    A[\"⚡ Lyra DevOps AI\"]
    A --> B[\"💰 Réduction coûts<br/>-40% tokens (TOON)\"]
    A --> C[\"🚀 Productivité<br/>Commandes vocales\"]
    A --> D[\"🔒 Sécurité<br/>100% local/offline\"]
    A --> E[\"🎯 Précision<br/>RAG + validation\"]

    classDef benefit fill:#95e1d3,stroke:#38ada9,stroke-width:2px,color:#000
    class B,C,D,E benefit
""",
    "title": "Bénéfices Lyra",
    "subtitle": "ROI et valeur business",
    "theme": "light",
    "output_name": "benefits"
  }
}
```

**Résultat** : Diagrammes clairs pour présentation business.

---

## 🎯 Cas d'usage 4 : Onboarding nouveau modèle LLM

### Objectif
Documenter l'ajout d'un nouveau modèle dans l'architecture.

### Workflow

```python
# 1. Diagramme AVANT (état actuel)
{
  "tool": "generate_diagram",
  "arguments": {
    "mermaid_code": """
graph LR
    A[\"Intent\"] --> B[\"LYRA<br/>(Llama 3B)\"]
    A --> C[\"EPHAISTOS<br/>(Qwen 7B)\"]
    B --> D[\"Response\"]
    C --> E[\"MCP\"]
    E --> D
""",
    "title": "Architecture Actuelle",
    "subtitle": "2 modèles LLM",
    "tech_stack": {
      "LYRA": "Llama 3.2 3B (~2.5 GB VRAM)",
      "EPHAISTOS": "Qwen 2.5 Coder 7B (~5 GB VRAM)",
      "Total VRAM": "~7.5 GB"
    },
    "output_name": "before_model"
  }
}

# 2. Diagramme APRÈS (avec nouveau modèle)
{
  "tool": "generate_diagram",
  "arguments": {
    "mermaid_code": """
graph LR
    A[\"Intent\"] --> B[\"LYRA<br/>(Llama 3B)\"]
    A --> C[\"EPHAISTOS<br/>(Qwen 7B)\"]
    A --> F[\"ATHENA<br/>(Mixtral 8x7B)\"]
    B --> D[\"Response\"]
    C --> E[\"MCP\"]
    F --> E
    E --> D

    classDef new fill:#feca57,stroke:#ee5a24,stroke-width:3px,color:#000
    class F new
""",
    "title": "Architecture Proposée",
    "subtitle": "3 modèles LLM avec ATHENA (nouveau)",
    "tech_stack": {
      "LYRA": "Llama 3.2 3B (~2.5 GB VRAM)",
      "EPHAISTOS": "Qwen 2.5 Coder 7B (~5 GB VRAM)",
      "ATHENA (NEW)": "Mixtral 8x7B (~13 GB VRAM)",
      "Total VRAM": "~20.5 GB"
    },
    "add_legend": true,
    "legend_colors": {
      "Existing": {"color": "#4ecdc4", "description": "Modèles actuels"},
      "New": {"color": "#feca57", "description": "Nouveau modèle ATHENA"}
    },
    "output_name": "after_model"
  }
}

# 3. Valider le nouveau diagramme
{
  "tool": "validate_diagram",
  "arguments": {
    "mermaid_code": "..."
  }
}
```

**Résultat** : Documentation complète avant/après pour décision d'ajout.

---

## 🎯 Cas d'usage 5 : Tests de performance

### Objectif
Visualiser les chemins de performance critiques.

### Workflow

```python
{
  "tool": "generate_diagram",
  "arguments": {
    "mermaid_code": """
graph LR
    A[\"User Query\"] --> B[\"Intent<br/>⏱️ 50ms\"]
    B ==> C[\"RAG Search<br/>⏱️ 300ms\"]
    C ==> D[\"TOON Encode<br/>⏱️ 10ms\"]
    D ==> E[\"EPHAISTOS<br/>⏱️ 2000ms\"]
    E ==> F[\"MCP Execute<br/>⏱️ 500ms\"]
    F ==> G[\"LYRA Format<br/>⏱️ 100ms\"]
    G --> H[\"Response\"]

    B --> I[\"LYRA Direct<br/>⏱️ 100ms\"]
    I --> H

    classDef fast fill:#95e1d3,stroke:#38ada9,color:#000
    classDef slow fill:#feca57,stroke:#ee5a24,color:#000
    classDef critical fill:#ff6b6b,stroke:#c92a2a,color:#fff

    class B,D fast
    class C,F,G slow
    class E critical
""",
    "title": "Performance Analysis",
    "subtitle": "Chemins critiques identifiés",
    "add_legend": true,
    "legend_colors": {
      "Fast": {"color": "#95e1d3", "description": "< 100ms"},
      "Slow": {"color": "#feca57", "description": "100-500ms"},
      "Critical": {"color": "#ff6b6b", "description": "> 500ms"}
    },
    "tech_stack": {
      "Total Time (Action Path)": "~2960ms",
      "Total Time (Info Path)": "~150ms",
      "Bottleneck": "EPHAISTOS (2000ms)"
    },
    "output_name": "performance_analysis"
  }
}
```

**Résultat** : Identification claire du bottleneck (EPHAISTOS).

---

## 🎯 Cas d'usage 6 : Session de brainstorming

### Objectif
Générer rapidement plusieurs variantes d'architecture.

### Workflow

```python
# Mode always pour vitesse
{
  "tool": "set_display_mode",
  "arguments": {"mode": "always"}
}

# Variante 1: Approche monolithique
{
  "tool": "generate_diagram",
  "arguments": {
    "mermaid_code": "graph LR\n  A[User] --> B[Lyra Mono]\n  B --> C[MCP]",
    "title": "Variante 1: Monolithique",
    "output_name": "var1_mono"
  }
}

# Variante 2: Microservices
{
  "tool": "generate_diagram",
  "arguments": {
    "mermaid_code": "graph LR\n  A[User] --> B[Gateway]\n  B --> C[Intent Service]\n  B --> D[LYRA Service]\n  B --> E[EPHAISTOS Service]",
    "title": "Variante 2: Microservices",
    "output_name": "var2_micro"
  }
}

# Variante 3: Hybride (actuelle)
{
  "tool": "generate_diagram",
  "arguments": {
    "mermaid_code": "graph LR\n  A[User] --> B[Intent]\n  B --> C[LYRA]\n  B --> D[EPHAISTOS Pipeline]",
    "title": "Variante 3: Hybride (recommandée)",
    "output_name": "var3_hybrid"
  }
}

# Comparer toutes les variantes
{
  "tool": "list_diagrams",
  "arguments": {}
}
```

**Résultat** : 3 variantes à comparer visuellement.

---

## 💡 Bonnes pratiques

### 1. Workflow itératif

```
1. generate_diagram (brouillon)
2. validate_diagram (vérifier)
3. generate_diagram (corrigé)
4. show_diagram (valider visuellement)
5. list_diagrams (archiver)
```

### 2. Modes d'affichage

- **Développement** : `mode: "ask"` (validation manuelle)
- **Présentation** : `mode: "always"` (rapidité)
- **CI/CD** : `mode: "never"` (génération batch)

### 3. Nommage des outputs

```python
# ✅ BON: Noms descriptifs
"output_name": "architecture_v2_2026"
"output_name": "flux_payment_processing"
"output_name": "performance_analysis_q1"

# ❌ MAUVAIS: Noms génériques
"output_name": "diagram"
"output_name": "test"
"output_name": "output"
```

### 4. Validation systématique

Toujours valider avant de partager :

```python
# 1. Générer
generate_diagram(...)

# 2. Valider
validate_diagram(mermaid_code)

# 3. Corriger si nécessaire
# 4. Régénérer
# 5. Partager
```

---

## 📝 Templates prêts à l'emploi

### Template 1: Architecture 3-tiers

```python
mermaid_code = """
graph LR
    subgraph FRONTEND["🖥️ Frontend"]
        ui["UI Layer"]
    end

    subgraph BACKEND["⚙️ Backend"]
        api["API Gateway"]
        logic["Business Logic"]
    end

    subgraph DATA["💾 Data Layer"]
        db["Database"]
        cache["Cache"]
    end

    ui --> api
    api --> logic
    logic --> db
    logic --> cache
"""
```

### Template 2: Pipeline ML

```python
mermaid_code = """
graph LR
    A["📊 Data"] --> B["🔧 Preprocessing"]
    B --> C["🧠 Model<br/>(Your Model Here)"]
    C --> D["✅ Validation"]
    D --> E["🚀 Deploy"]
"""
```

### Template 3: Event-driven

```python
mermaid_code = """
graph TB
    A["⚡ Event Source"] --> B["📮 Message Queue"]
    B --> C["👂 Consumer 1"]
    B --> D["👂 Consumer 2"]
    B --> E["👂 Consumer 3"]
"""
```

---

**Besoin d'aide?** Consultez le README.md principal !
