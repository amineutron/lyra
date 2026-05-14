#!/usr/bin/env python3
"""
Exemple d'utilisation du template fancy pour générer le diagramme Lyra.

Usage:
    python docs/exemple_mermaid_fancy.py
"""

import sys
from pathlib import Path

# Ajouter le parent au path pour importer lyra
sys.path.insert(0, str(Path(__file__).parent.parent))

from lyra.utils.mermaid_viewer import MermaidViewer


def create_lyra_architecture_diagram():
    """Génère le diagramme d'architecture Lyra V2 RAG avec le template fancy."""

    # Initialiser le viewer avec le template fancy
    template_path = Path(__file__).parent / "mermaid_template_fancy.html"
    viewer = MermaidViewer(template_path=str(template_path))

    # Code Mermaid (LR = Left to Right pour lecture horizontale)
    mermaid_code = """graph LR
    %% Entrée utilisateur
    USER_IN["👤 UTILISATEUR<br/>INPUT"]

    %% Modes d'entrée
    VOCAL_IN["🎤 Vocal"]
    TEXT_IN["⌨️ Texte"]

    %% STT
    WHISPER["🔊 Whisper STT<br/>faster-whisper CUDA<br/>~1.5 GB"]

    %% Classification
    INTENT["🧠 IntentClassifier<br/>LYRA Llama 3B<br/>demande/info/discussion"]

    %% Branches selon intention
    BRANCH_DEMANDE{"📌 demande?"}
    BRANCH_INFO{"💬 info/discussion?"}

    %% Pipeline RAG
    RAG_QUERY["🔍 Query Processing<br/>Pre-filtrage catégorie"]
    RAG_SEMANTIC["📚 ChromaDB<br/>Semantic Search<br/>multilingual-MiniLM<br/>~0.5 GB"]
    RAG_KEYWORD["🔤 BM25<br/>Keyword Search<br/>rank-bm25"]
    RAG_FUSION["⚡ RRF Fusion<br/>k=60, top_k=5"]
    TOON["📦 TOON Encoder<br/>~40% compression<br/>specs compactes"]

    %% Backend
    EPHAISTOS["🔧 EPHAISTOS<br/>Qwen 2.5 Coder 7B<br/>~5 GB VRAM<br/>Analyse specs MCP"]

    %% Exécution
    HESTIA["⚙️ HESTIA Executor<br/>Gestion erreurs"]
    CONFIRM{"🤚 Mode<br/>Performance?"}

    %% MCP Servers
    MCP_SERVERS["🔌 MCP SERVERS<br/>80 outils<br/>━━━━━━━━━<br/>FEDORA 17<br/>HUE 24<br/>TV 14<br/>CATT 15<br/>DENON 10"]

    %% Async
    ASYNC{"⏱️ Opération<br/>async?"}
    N8N["🌐 n8n Webhooks"]
    SUBPROCESS["⚡ subprocess<br/>fallback"]

    %% Résultats
    RESULTS["✅ Résultats MCP"]

    %% Session Memory
    SESSION["💾 Session Memory<br/>Contexte multi-tour<br/>PendingChoice"]

    %% Frontend
    LYRA_VOICE["🗣️ LYRA Frontend<br/>Llama 3.2 3B<br/>~2.5 GB VRAM<br/>Dialogue + Formatage"]

    %% TTS
    TTS_CHOICE{"🔊 Mode<br/>vocal?"}
    PIPER["🔉 Piper TTS<br/>fr_FR-upmc-medium"]

    %% Sortie utilisateur
    USER_OUT["👤 UTILISATEUR<br/>OUTPUT"]

    %% === FLUX PRINCIPAL ===

    %% Entrée
    USER_IN -->|Vocal| VOCAL_IN
    USER_IN -->|Texte| TEXT_IN

    VOCAL_IN --> WHISPER
    TEXT_IN --> INTENT
    WHISPER --> INTENT

    %% Classification
    INTENT --> BRANCH_DEMANDE
    INTENT --> BRANCH_INFO

    %% Branche INFO (directe)
    BRANCH_INFO -->|Oui| LYRA_VOICE

    %% Branche DEMANDE (RAG)
    BRANCH_DEMANDE -->|Oui| RAG_QUERY

    RAG_QUERY --> RAG_SEMANTIC
    RAG_QUERY --> RAG_KEYWORD

    RAG_SEMANTIC --> RAG_FUSION
    RAG_KEYWORD --> RAG_FUSION

    RAG_FUSION --> TOON
    TOON --> EPHAISTOS

    %% Exécution MCP
    EPHAISTOS --> HESTIA
    HESTIA --> CONFIRM

    CONFIRM -->|Oui, skip| MCP_SERVERS
    CONFIRM -->|Non, confirm| MCP_SERVERS

    %% Async ou Sync
    MCP_SERVERS --> ASYNC

    ASYNC -->|Sync| RESULTS
    ASYNC -->|Async| N8N
    N8N -->|OK| RESULTS
    N8N -.->|Échec| SUBPROCESS
    SUBPROCESS --> RESULTS

    %% Session + Frontend
    RESULTS --> SESSION
    SESSION --> LYRA_VOICE

    %% Sortie
    LYRA_VOICE --> TTS_CHOICE

    TTS_CHOICE -->|Oui| PIPER
    TTS_CHOICE -->|Non| USER_OUT
    PIPER --> USER_OUT

    %% === STYLES ===

    classDef userClass fill:#ff6b6b,stroke:#c92a2a,stroke-width:3px,color:#fff
    classDef inputClass fill:#a29bfe,stroke:#6c5ce7,color:#fff
    classDef intentClass fill:#fdcb6e,stroke:#e17055,color:#000
    classDef ragClass fill:#aa96da,stroke:#6c5ce7,color:#fff
    classDef backendClass fill:#4ecdc4,stroke:#45b7d1,color:#fff
    classDef executionClass fill:#f38181,stroke:#aa5042,color:#fff
    classDef mcpClass fill:#feca57,stroke:#ee5a24,color:#000
    classDef frontendClass fill:#95e1d3,stroke:#38ada9,color:#000
    classDef memoryClass fill:#74b9ff,stroke:#0984e3,color:#fff
    classDef audioClass fill:#fab1a0,stroke:#e17055,color:#000

    class USER_IN,USER_OUT userClass
    class VOCAL_IN,TEXT_IN inputClass
    class WHISPER,PIPER audioClass
    class INTENT,BRANCH_DEMANDE,BRANCH_INFO intentClass
    class RAG_QUERY,RAG_SEMANTIC,RAG_KEYWORD,RAG_FUSION,TOON ragClass
    class EPHAISTOS backendClass
    class HESTIA,CONFIRM,ASYNC executionClass
    class MCP_SERVERS mcpClass
    class LYRA_VOICE,TTS_CHOICE frontendClass
    class SESSION memoryClass
    class N8N,SUBPROCESS,RESULTS memoryClass"""

    # Créer la légende des couleurs avec les helpers
    legend_colors = {
        "Utilisateur": {
            "color": "#ff6b6b",
            "description": "Entrée/Sortie (INPUT/OUTPUT)"
        },
        "Interface": {
            "color": "#a29bfe",
            "description": "Modes Vocal/Texte"
        },
        "Audio": {
            "color": "#fab1a0",
            "description": "Whisper STT + Piper TTS"
        },
        "Classification": {
            "color": "#fdcb6e",
            "description": "IntentClassifier (demande/info)"
        },
        "RAG Pipeline": {
            "color": "#aa96da",
            "description": "ChromaDB + BM25 + TOON"
        },
        "Backend": {
            "color": "#4ecdc4",
            "description": "EPHAISTOS (Qwen 7B)"
        },
        "Exécution": {
            "color": "#f38181",
            "description": "HESTIA + Confirmation"
        },
        "MCP Servers": {
            "color": "#feca57",
            "description": "80 outils (5 serveurs)"
        },
        "Frontend": {
            "color": "#95e1d3",
            "description": "LYRA (Llama 3B)"
        },
        "Session/Résultats": {
            "color": "#74b9ff",
            "description": "Memory + Async"
        }
    }

    legend = viewer.create_legend(legend_colors)

    # Créer le tableau VRAM
    vram_table = """
    <table>
        <thead>
            <tr>
                <th>Composant</th>
                <th>Modèle</th>
                <th>VRAM</th>
                <th>Rôle</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><strong>EPHAISTOS</strong></td>
                <td>Qwen 2.5 Coder 7B</td>
                <td>~5 GB</td>
                <td>Analyse specs MCP, extraction args</td>
            </tr>
            <tr>
                <td><strong>LYRA</strong></td>
                <td>Llama 3.2 3B</td>
                <td>~2.5 GB</td>
                <td>Dialogue, classification, personnalité</td>
            </tr>
            <tr>
                <td><strong>Embeddings</strong></td>
                <td>paraphrase-multilingual-MiniLM-L12-v2</td>
                <td>~0.5 GB</td>
                <td>Recherche sémantique RAG</td>
            </tr>
            <tr>
                <td><strong>Whisper</strong></td>
                <td>faster-whisper base (CUDA)</td>
                <td>~1.5 GB</td>
                <td>Speech-to-Text (mode vocal)</td>
            </tr>
            <tr style="font-weight: bold; background: rgba(78, 205, 196, 0.1);">
                <td colspan="2"><strong>TOTAL</strong></td>
                <td>~10.5 GB</td>
                <td>87.5% de 12 GB</td>
            </tr>
        </tbody>
    </table>
    """
    vram_info = viewer.create_info_section("💾 VRAM Allocation (RTX 3080 Ti 12GB)", vram_table)

    # Créer le tableau des MCP servers
    mcp_table = """
    <table>
        <thead>
            <tr>
                <th>Serveur</th>
                <th>Outils</th>
                <th>Description</th>
                <th>Technologie</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td><strong>FEDORA</strong></td>
                <td>17</td>
                <td>VM KVM + Backups (vm_start, vm_clone, backup_create...)</td>
                <td>Node.js</td>
            </tr>
            <tr>
                <td><strong>HUE</strong></td>
                <td>24</td>
                <td>Lumières Philips Hue (turn_on/off, set_brightness...)</td>
                <td>Python (hue-mcp)</td>
            </tr>
            <tr>
                <td><strong>TV</strong></td>
                <td>14</td>
                <td>TV Philips 55OLED705 (power, volume, ambilight...)</td>
                <td>Python (pylips-mcp)</td>
            </tr>
            <tr>
                <td><strong>CATT</strong></td>
                <td>15</td>
                <td>Cast YouTube/Video (cast_youtube, cast_pause...)</td>
                <td>Python (catt-mcp)</td>
            </tr>
            <tr>
                <td><strong>DENON</strong></td>
                <td>10</td>
                <td>Home Cinema Denon AVR-X1700H (volume, mute, input...)</td>
                <td>Python (denon-mcp)</td>
            </tr>
        </tbody>
    </table>
    """
    mcp_info = viewer.create_info_section("🔌 MCP Servers (80 outils)", mcp_table)

    # Créer la section flux de traitement
    flux_content = """
    <h3>1️⃣ Entrée Utilisateur (gauche)</h3>
    <p><strong>USER INPUT</strong> → Mode Vocal/Texte → Whisper STT (si vocal) → IntentClassifier</p>

    <h3>2️⃣ Classification & Routage</h3>
    <ul>
        <li><strong>🔴 demande</strong> (action MCP) → Pipeline RAG → EPHAISTOS → MCP</li>
        <li><strong>🟢 info/discussion</strong> → LYRA directement (pas de RAG)</li>
    </ul>

    <h3>3️⃣ Pipeline RAG (si demande)</h3>
    <p>Query Processing → ChromaDB + BM25 → RRF Fusion → TOON Encoder → EPHAISTOS</p>

    <h3>4️⃣ Exécution MCP</h3>
    <p>EPHAISTOS → HESTIA → Confirmation (si mode default) → MCP Servers → Résultats</p>

    <h3>5️⃣ Formatage & Sortie (droite)</h3>
    <p>Résultats → Session Memory → LYRA Frontend → Piper TTS (si vocal) → <strong>USER OUTPUT</strong></p>
    """
    flux_info = viewer.create_info_section("🎯 Flux de Traitement", flux_content)

    # Créer la section optimisations
    optim_content = """
    <ul>
        <li><strong>TOON Encoder</strong>: Compression ~40% des specs MCP avant EPHAISTOS</li>
        <li><strong>BM25 Keyword</strong>: Recherche par mots-clés français (meilleure que semantic seul)</li>
        <li><strong>RRF Fusion</strong>: Combine semantic + keyword (k=60, top_k=5)</li>
        <li><strong>Pre-filtrage catégorie</strong>: Boost résultats par mots-clés (lumière→hue, vm→fedora...)</li>
        <li><strong>Mode Performance</strong>: Skip confirmation pour domotique (TV, Hue, Denon, CATT)</li>
        <li><strong>Session Memory</strong>: Contexte multi-tour (max_turns=10) + PendingChoice</li>
        <li><strong>Async Operations</strong>: n8n webhooks + fallback subprocess (vm_clone, backup_*)</li>
    </ul>
    """
    optim_info = viewer.create_info_section("⚡ Optimisations Clés", optim_content)

    # Combiner tout le contenu extra
    extra_content = legend + flux_info + vram_info + mcp_info + optim_info

    # Générer le fichier HTML
    output_path = viewer.generate(
        mermaid_code=mermaid_code,
        output_path="docs/architecture_lyra_v2_fancy.html",
        title="🚀 Architecture Lyra V2 RAG",
        subtitle="Assistant Vocal DevOps Local - 100% Offline",
        theme="dark",
        extra_content=extra_content,
        filename="lyra_architecture_v2",
        open_browser=True
    )

    print(f"\n✅ Diagramme généré avec succès!")
    print(f"📁 Fichier: {output_path}")
    print(f"🌐 Ouvert dans le navigateur")
    print(f"\n💡 Conseil: Utilisez les boutons pour exporter en SVG/PNG")


if __name__ == "__main__":
    create_lyra_architecture_diagram()
