# Architecture Lyra - Diagramme Mermaid

Ce diagramme représente l'architecture complète de Lyra RAG V2.

```mermaid
%%{init: {'theme':'dark', 'themeVariables': { 'primaryColor':'#ff6b6b', 'primaryTextColor':'#fff', 'primaryBorderColor':'#c92a2a', 'lineColor':'#4ecdc4', 'secondaryColor':'#45b7d1', 'tertiaryColor':'#96ceb4'}}}%%
graph LR
    %% INPUT
    User["👤 User<br/>Input"]
    Whisper["🎙️ Whisper<br/>STT"]

    %% INTENT
    Intent["🎯 Intent<br/>Classifier<br/>(Llama 3B)"]

    %% PATHS
    subgraph PATH1["📚 PATH: Info/Discussion"]
        Lyra1["💬 LYRA<br/>(Llama 3B)<br/>Dialogue"]
    end

    subgraph PATH2["⚡ PATH: Action MCP"]
        direction TB
        RAG["🔍 RAG<br/>ChromaDB+BM25"]
        TOON["📦 TOON<br/>Compress"]
        Ephaistos["🔧 EPHAISTOS<br/>(Qwen 7B)"]
        Hestia["⚙️ HESTIA<br/>Executor"]

        RAG --> TOON --> Ephaistos --> Hestia
    end

    %% MCP SERVERS
    subgraph MCP["🌐 MCP SERVERS"]
        direction TB
        Fedora["🖥️ FEDORA<br/>VM/Backup"]
        Catt["📺 CATT<br/>Cast"]
        Hue["💡 HUE<br/>Lights"]
        TV["📺 TV<br/>Control"]
    end

    %% OUTPUT
    Lyra2["💬 LYRA<br/>Format"]
    Output["💭 Response"]
    Piper["🗣️ Piper<br/>TTS"]

    %% FLUX PRINCIPAL
    User -->|Texte| Intent
    User -->|Vocal| Whisper --> Intent

    Intent -->|"info<br/>discussion"| Lyra1 --> Output
    Intent -->|"demande"| PATH2

    Hestia --> Fedora & Catt & Hue & TV
    Fedora & Catt & Hue & TV --> Lyra2

    Lyra2 --> Output
    Output -->|Vocal| Piper

    %% Styles
    classDef inputStyle fill:#ff6b6b,stroke:#c92a2a,stroke-width:3px,color:#fff
    classDef intentStyle fill:#4ecdc4,stroke:#45b7d1,stroke-width:3px,color:#fff
    classDef pathStyle fill:#95e1d3,stroke:#38ada9,stroke-width:2px,color:#000
    classDef actionStyle fill:#feca57,stroke:#ee5a24,stroke-width:2px,color:#000
    classDef mcpStyle fill:#a29bfe,stroke:#6c5ce7,stroke-width:2px,color:#fff
    classDef outputStyle fill:#fd79a8,stroke:#e84393,stroke-width:3px,color:#fff

    class User,Whisper inputStyle
    class Intent intentStyle
    class Lyra1,Lyra2 pathStyle
    class RAG,TOON,Ephaistos,Hestia actionStyle
    class Fedora,Catt,Hue,TV mcpStyle
    class Output,Piper outputStyle
```

---

## Version simplifiée (ultra-clean)

```mermaid
%%{init: {'theme':'dark'}}%%
flowchart LR
    A["👤 User"] --> B["🎯 Intent"]

    B -->|Info| C1["💬 LYRA<br/>Dialogue"]
    B -->|Action| C2["⚡ Pipeline<br/>RAG→TOON→EPHAISTOS→HESTIA"]

    C2 --> D["🌐 MCP<br/>FEDORA|CATT|HUE|TV"]

    C1 --> E["💭 Response"]
    D --> E
    E --> F["🗣️ TTS"]

    style A fill:#ff6b6b,stroke:#c92a2a,color:#fff
    style B fill:#4ecdc4,stroke:#45b7d1,color:#fff
    style C1 fill:#95e1d3,stroke:#38ada9,color:#000
    style C2 fill:#feca57,stroke:#ee5a24,color:#000
    style D fill:#a29bfe,stroke:#6c5ce7,color:#fff
    style E fill:#fd79a8,stroke:#e84393,color:#fff
    style F fill:#fd79a8,stroke:#e84393,color:#fff
```

## Légende des composants

| Couleur | Layer | Composants |
|---------|-------|------------|
| 🔴 Rouge | Input | User, Whisper STT |
| 🔵 Cyan | Intent | IntentClassifier (Llama 3B) |
| 🟢 Vert | Knowledge | LYRA Voice (dialogue) |
| 🟡 Jaune | Action | RAG, TOON, EPHAISTOS, HESTIA |
| 🟣 Violet | MCP | FEDORA, CATT, HUE, TV |
| 🔴 Rose | Output | Response, Piper TTS |
| 🔵 Bleu | Storage | ChromaDB, BM25, SessionMemory |

## Flux de données

- **Ligne pleine** → Flux principal de données
- **Ligne pointillée** → Contexte et mémoire

## Ressources VRAM (~10.5 GB)

- EPHAISTOS (Qwen 7B): ~5 GB
- LYRA (Llama 3B): ~2.5 GB
- Embeddings: ~0.5 GB
- Whisper: ~1.5 GB

## Comment visualiser ce diagramme

### Option 1 : VSCode avec extension Mermaid
1. Installe l'extension "Markdown Preview Mermaid Support"
2. Ouvre ce fichier dans VSCode
3. Appuie sur `Ctrl+Shift+V` pour le preview Markdown

### Option 2 : En ligne
1. Va sur https://mermaid.live/
2. Copie-colle le code Mermaid (entre les ``` ````)
3. Le diagramme s'affiche automatiquement

### Option 3 : GitHub/GitLab
Les plateformes Git supportent nativement Mermaid dans les fichiers .md

### Option 4 : Mermaid CLI
```bash
npm install -g @mermaid-js/mermaid-cli
mmdc -i docs/ARCHITECTURE_DIAGRAM.md -o docs/architecture.png
```
