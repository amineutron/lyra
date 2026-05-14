#!/usr/bin/env python3
"""
Lyra Intro - Partie 2 : Sequence d'installation / boot style JARVIS (FR)
"""
import time
import sys
from rich.console import Console
from rich.text import Text
from rich.align import Align

console = Console()

BLUE_DIM = "cyan"
GREEN    = "bold green"
WHITE    = "bold white"
DIM      = "dim white"
DARK     = "dim cyan"

INSTALL_STEPS = [
    ("Python 3.12",          "Verification du runtime",                    0.3,  "ok"),
    ("CUDA 12.x",            "GPU detecte  RTX 3080 Ti  10.5 Go VRAM",    0.5,  "ok"),
    ("Ollama",               "qwen2.5-coder:0.5b + llama3.2:1b",          0.6,  "ok"),
    ("faster-whisper",       ">=0.10.0  [backend CUDA]",                   0.4,  "ok"),
    ("nvidia-cublas-cu12",   ">=12.0.0",                                   0.25, "ok"),
    ("nvidia-cudnn-cu12",    ">=9.0.0",                                    0.25, "ok"),
    ("piper-tts",            ">=1.2.0  fr_FR-upmc-medium",                 0.4,  "ok"),
    ("chromadb",             "Stockage vectoriel  [all-MiniLM-L6-v2]",     0.5,  "ok"),
    ("rank-bm25",            "Recherche par mots-cles",                    0.2,  "ok"),
    ("sounddevice",          ">=0.4.6  Entree / Sortie audio",             0.2,  "ok"),
    ("rich",                 ">=13.0.0",                                    0.15, "ok"),
]

MCP_SERVERS = [
    ("fedora-agents",  "Gestionnaire VM KVM + Sauvegardes",  0.4),
    ("pylips-mcp",     "Philips 55OLED705/12",               0.3),
    ("hue-mcp",        "Pont Hue @ 192.168.1.51",            0.3),
    ("denon-mcp",      "AVR-X1700H DAB",                     0.3),
]

RAG_STEPS = [
    ("SlangNormalizer",      "172 expressions FR/EN",          0.3),
    ("ContextInjector",      "Memoire multi-tour",             0.3),
    ("ConfidenceCascader",   "Cascade multi-niveaux",          0.3),
    ("RAG3Tier",             "exact / semantique / mots-cles", 0.4),
    ("BoucleRetroaction",    "Controle qualite actif",         0.25),
    ("Index BM25",           "Indexation specs MCP",           0.5),
    ("Embeddings ChromaDB",  "3 collections prets",            0.5),
]


def scan_line(text: str, style: str = DIM, delay: float = 0.013) -> None:
    for ch in text:
        console.print(ch, end="", style=style)
        sys.stdout.flush()
        time.sleep(delay)
    console.print("")


def status_line(icon: str, label: str, detail: str, status: str, delay: float = 0.3) -> None:
    time.sleep(delay)
    row = Text()
    row.append(f"  {icon} ", style=DARK)
    row.append(f"{label:<28}", style=WHITE)
    row.append(f"{detail:<42}", style=DIM)
    console.print(row, end="")
    time.sleep(0.1)
    if status == "ok":
        console.print(Text("  EN LIGNE", style=GREEN))
    elif status == "warn":
        console.print(Text("  ALERTE  ", style="bold yellow"))


def section(title: str) -> None:
    console.print("")
    t = Text()
    t.append("  // ", style=DARK)
    t.append(title, style=BLUE_DIM)
    console.print(t)
    console.print("")


def run() -> None:
    console.clear()
    console.print("")

    title = Text()
    for i, ch in enumerate("L.Y.R.A"):
        title.append(ch, style="bold cyan" if ch != "." else "dim cyan")
    console.print(Align.center(title))
    console.print(Align.center(Text(
        "  SYSTEME DEVOPS VOCAL AUTONOME  ", style="dim white on black"
    )))
    console.print("")
    console.rule(style="cyan dim")
    console.print("")

    time.sleep(0.2)
    scan_line("  Initialisation de la sequence de deploiement LYRA...", style=DARK, delay=0.016)
    time.sleep(0.2)
    scan_line("  Hote detecte    neutron  Fedora 43  x86_64",           style=DIM,  delay=0.011)
    time.sleep(0.15)
    scan_line("  GPU detecte     NVIDIA RTX 3080 Ti  10 517 Mo VRAM",   style=DIM,  delay=0.011)
    time.sleep(0.15)
    scan_line("  Python          3.12.13",                               style=DIM,  delay=0.011)
    console.print("")
    time.sleep(0.3)

    section("PHASE 1  --  DEPENDANCES")
    for label, detail, delay, st in INSTALL_STEPS:
        status_line("[+]", label, detail, st, delay)

    section("PHASE 2  --  SERVEURS MCP")
    for label, detail, delay in MCP_SERVERS:
        status_line("[>]", label, detail, "ok", delay)

    section("PHASE 3  --  PIPELINE RAG ENHANCED")
    for label, detail, delay in RAG_STEPS:
        status_line("[~]", label, detail, "ok", delay)

    section("PHASE 4  --  INTEGRATION SYSTEME")
    status_line("[+]", "sudoers /etc/sudoers.d/lyra", "kvm/*.sh  vm-controller  backup-manager", "ok", 0.3)
    status_line("[+]", "alias  lyra",                  "~/dev/lyra/run.sh  --  pret",             "ok", 0.25)
    status_line("[+]", "systemd tracking-api",          "127.0.0.1:8765  --  actif (running)",     "ok", 0.25)

    console.print("")
    console.rule(style="cyan dim")
    console.print("")
    time.sleep(0.4)

    scan_line("  Tous les systemes sont nominaux.", style=BLUE_DIM, delay=0.022)
    time.sleep(0.15)
    scan_line("  Acces administrateur confirme.",   style=BLUE_DIM, delay=0.022)
    time.sleep(0.15)
    scan_line("  Bonjour.",                          style=BLUE_DIM, delay=0.022)
    console.print("")
    time.sleep(0.5)


if __name__ == "__main__":
    run()
