# Lyra V1 - Assistant DevOps Local

Assistant vocal **100% local** (0 EUR API) controlant l'infrastructure DevOps via commandes naturelles en francais.

## Fonctionnalites

- **Gestion VMs** : demarrer, arreter, cloner, snapshots, executer des commandes
- **Gestion Backups** : status, liste, creation, verification
- **Controle TV Philips** : power, volume, ambilight, apps, YouTube Cast
- **Controle Lumieres Hue** : on/off, couleurs, luminosite, scenes
- **Mode Vocal** : STT (Whisper) + TTS (Piper) en francais
- **Mode Performance** : execution instantanee sans confirmation (domotique)
- **Human-in-the-Loop** : confirmation avant chaque action (VMs/backups)
- **Todo List** : gestion de plusieurs actions en une commande
- **Operations Async** : clone VM, backups en arriere-plan

## Demo

```
Toi: clone preprod-09 vers sandbox-01 et sandbox-02

[i] Todo list: 2 actions proposees
==================================================
  [1] vm_clone -> preprod-09
  [2] vm_clone -> preprod-09
==================================================

Executer ? [T]out / [1] par 1 / [n]on : t

[i] [1/2] vm_clone -> preprod-09
[i] Lancement async via n8n (clone-vm)...
[+] Operation lancee en arriere-plan (mode local).

[i] [2/2] vm_clone -> preprod-09
[+] Operation lancee en arriere-plan (mode local).

[+] Todo list terminee: 2/2 actions
```

## Installation

### Prerequis

- **Ollama** avec le modele `qwen2.5-coder:14b`
- **Python 3.10+**
- **MCP Server fedora-agents** compile
- **RTX 3080 Ti** ou GPU avec 12+ Go VRAM (recommande)

### Installation

```bash
# 1. Telecharger le modele LLM (~9 GB)
ollama pull qwen2.5-coder:14b

# 2. Cloner et installer
cd ~/dev/lyra
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. Configurer sudoers (pour operations async sans mot de passe)
sudo tee /etc/sudoers.d/lyra << 'EOF'
amineutron ALL=(ALL) NOPASSWD: /home/amineutron/dev/fedora-setup/scripts/kvm/*.sh
amineutron ALL=(ALL) NOPASSWD: /home/amineutron/dev/fedora-setup/scripts/agents/vm-controller/*.sh
amineutron ALL=(ALL) NOPASSWD: /home/amineutron/dev/fedora-setup/scripts/agents/backup-manager/*.sh
amineutron ALL=(ALL) NOPASSWD: /usr/bin/virsh
amineutron ALL=(ALL) NOPASSWD: /usr/bin/virt-clone
amineutron ALL=(ALL) NOPASSWD: /usr/bin/qemu-img
amineutron ALL=(ALL) NOPASSWD: /usr/bin/systemctl is-active *
amineutron ALL=(ALL) NOPASSWD: /usr/bin/systemctl status *
EOF
sudo chmod 440 /etc/sudoers.d/lyra

# 4. Ajouter l'alias (optionnel)
echo 'alias lyra="~/dev/lyra/run.sh"' >> ~/.bashrc
source ~/.bashrc
```

## Utilisation

```bash
# Mode texte (defaut)
lyra

# Mode vocal (STT/TTS)
lyra --vocal

# Mode performance (domotique sans confirmation)
lyra --performance
lyra -p

# Combinaisons
lyra --vocal --performance      # Vocal + performance

# Avec un autre modele
lyra -m qwen3:8b

# Lister les peripheriques audio
lyra --list-devices
```

### Commandes internes

| Commande | Description |
|----------|-------------|
| `help` | Affiche l'aide |
| `clear` | Efface l'historique de conversation |
| `clearscreen` | Efface le terminal |
| `quit` / `stop` | Quitte Lyra |
| `mode` | Affiche le mode actuel |
| `mode performance` | Active le mode performance (domotique sans confirmation) |
| `mode default` | Retour au mode normal |

### Raccourcis clavier

| Raccourci | Action |
|-----------|--------|
| `Ctrl+L` | Efface le terminal |
| `Ctrl+C` (2x) | Quitte Lyra (double-tap < 1.5s) |

## Exemples de prompts

### Lecture (safe)
```
liste mes VMs
status de preprod-09
montre les backups
status des backups
```

### Actions simples
```
demarre preprod-09
arrete preprod-09
cree un snapshot de preprod-09
```

### Actions multiples (Todo List)
```
supprime sandbox-01 et sandbox-02
demarre preprod-09 et fais un snapshot
clone preprod-09 vers sandbox-01 et sandbox-02
```

### Operations longues (Async)
```
clone preprod-09 vers sandbox
cree un backup timeshift
```

## Confirmation des actions

### Action simple
```
==================================================
  ACTION PROPOSEE
==================================================

  Outil: vm_stop
  Parametres:
    - vm_name: preprod-09

  Etat actuel:
    - Status: En cours d'execution
    - IP: 192.168.122.146

==================================================

  Executer ? [O/n/d] (O=oui, n=non, d=details)
```

### Todo List (actions multiples)
```
[i] Todo list: 2 actions proposees
==================================================
  [1] vm_destroy -> sandbox-01
  [2] vm_destroy -> sandbox-02
==================================================

Executer ? [T]out / [1] par 1 / [n]on :
```

- **T** ou **Entree** : Execute tout
- **1** : Confirme chaque action une par une
- **n** : Annule tout

## Mode Vocal

```bash
lyra --vocal
```

### Fonctionnement
1. **Bip sonore** indique que Lyra ecoute
2. **Barre de niveau** affiche le volume en temps reel
3. **Detection silence** (1s) termine l'enregistrement
4. **Transcription** puis traitement par le LLM
5. **Synthese vocale** de la reponse

### Commandes vocales
- Dites **"stop"** ou **"arrete"** pour quitter
- Confirmation des actions par clavier (pas vocal)

### Stack vocale
| Composant | Technologie | Details |
|-----------|-------------|---------|
| **STT** | faster-whisper | Modele `base`, GPU CUDA |
| **TTS** | Piper | Voix `fr_FR-upmc-medium` |
| **Audio** | sounddevice | 48kHz, mono |

## Operations Async

Les operations longues sont executees en arriere-plan :

| Operation | Duree | Mode |
|-----------|-------|------|
| `vm_clone` | ~60s | Async (subprocess) |
| `vm_clone_system` | ~10-30min | Async |
| `backup_create` | ~2min | Async |
| `backup_restore` | ~2min | Async |

Quand une operation async termine, un message s'affiche :
```
[+] [ASYNC] Operation vm_clone terminee avec succes!
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        LYRA V1                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  [User Input] ──► [Ollama/Qwen] ──► [Tool Call JSON]       │
│       │                                    │                │
│       │ (vocal)                            ▼                │
│       ▼                          ┌─────────────────┐        │
│  [Whisper STT]                   │ Human-in-Loop   │        │
│                                  │  Confirmation   │        │
│                                  └────────┬────────┘        │
│                                           │                 │
│                          ┌────────────────┼────────────┐    │
│                          ▼                ▼            ▼    │
│                    [Sync MCP]      [Async n8n]   [Fallback] │
│                          │                │      subprocess │
│                          └────────────────┴────────────┘    │
│                                           │                 │
│                                           ▼                 │
│                                  [Resultat ──► LLM]         │
│                                  [Resume en francais]       │
│                                           │                 │
│                                           ▼ (vocal)         │
│                                     [Piper TTS]             │
└─────────────────────────────────────────────────────────────┘
```

## Stack Technique

| Composant | Technologie |
|-----------|-------------|
| **LLM** | Qwen 2.5 Coder 14B via Ollama |
| **Wrapper** | Python (main.py) |
| **MCP** | fedora-agents (17 tools VM/Backup) |
| **MCP** | pylips-mcp (14 tools TV Philips) |
| **MCP** | hue-mcp (14 tools Philips Hue) |
| **STT** | faster-whisper (GPU CUDA) |
| **TTS** | Piper (voix francaise) |
| **ADB** | Android Debug Bridge (YouTube Premium sans pubs) |
| **Cast** | catt (fallback Chromecast) |
| **Async** | n8n webhooks + fallback subprocess |
| **Hardware** | RTX 3080 Ti (12 Go VRAM) |

### VRAM

| Modele | VRAM |
|--------|------|
| qwen2.5-coder:14b | ~10.1 GB |
| Whisper base | ~0.5 GB |
| qwen3:8b | ~5.2 GB |

## Outils MCP disponibles

### Gestion VMs (11 outils)
| Outil | Description |
|-------|-------------|
| `vm_status` | Status des VMs (IP, SSH, ressources) |
| `vm_start` | Demarrer une VM |
| `vm_stop` | Arreter une VM |
| `vm_destroy` | Supprimer une VM |
| `vm_snapshot` | Gerer les snapshots (create/list/restore/delete) |
| `vm_exec` | Executer une commande SSH |
| `vm_copy` | Copier des fichiers (SCP) |
| `vm_clone` | Cloner une VM existante |
| `vm_clone_system` | Cloner le systeme hote vers VM |
| `vm_verify` | Verifier un clone |

### Gestion Backups (6 outils)
| Outil | Description |
|-------|-------------|
| `backup_status` | Dashboard global des backups |
| `backup_list` | Lister les backups |
| `backup_create` | Creer un backup |
| `backup_restore` | Restaurer un backup |
| `backup_verify` | Verifier l'integrite |
| `backup_clean` | Nettoyer les anciens backups |

## Structure du projet

```
lyra/
├── run.sh               # Script de lancement (configure CUDA)
├── main.py              # Point d'entree + orchestrateur
├── config.yaml          # Configuration centralisee
├── modules/
│   ├── llm.py           # Client Ollama + parsing tool calls
│   ├── mcp.py           # MCPManager multi-serveurs + clients
│   ├── ui.py            # Interface utilisateur + confirmation
│   ├── audio.py         # STT/TTS/Recording
│   └── n8n.py           # Client n8n + fallback async
├── mcp-servers/
│   └── pylips-mcp/
│       └── server.py    # Serveur MCP pour TV Philips
├── models/
│   ├── fr_FR-upmc-medium.onnx       # Voix Piper
│   └── fr_FR-upmc-medium.onnx.json
└── prompts/
    └── system_prompt.txt  # Instructions pour le LLM
```

## Securite

### Principes
- **Human-in-the-Loop** : Confirmation obligatoire avant chaque action
- **Read-First** : Verification automatique de l'etat VM avant action
- **Avertissement destructif** : Actions dangereuses signalees en rouge
- **100% local** : Aucune donnee envoyee sur internet

### Actions destructives (confirmation renforcee)
- `vm_destroy` - Supprime definitivement une VM
- `vm_stop --force` - Arret force (risque corruption)
- `backup_restore` - Ecrase les donnees actuelles
- `backup_clean` - Supprime des backups

## Configuration

Fichier `config.yaml` :

```yaml
# LLM
llm:
  model: qwen2.5-coder:14b
  temperature: 0.3

# Audio (mode vocal)
audio:
  sample_rate: 48000
  silence_threshold: 0.005
  silence_duration: 1.0

# STT
stt:
  model: base
  device: cuda
  language: fr

# TTS
tts:
  model: fr_FR-upmc-medium

# n8n (optionnel)
n8n:
  enabled: true
  base_url: http://localhost:5678
```

## Phases de developpement

- [x] **Phase 1** : Wrapper Python + MCP (mode texte)
- [x] **Phase 2** : Mode Vocal (STT/TTS)
- [x] **Phase 3** : Read-First + Securite avancee
- [x] **Phase 4** : Operations async (n8n + fallback subprocess)
- [x] **Phase 5** : Controle Domotique (TV Philips + Hue)

---

## 🏠 Controle Domotique (Phase 5)

Lyra peut controler votre TV Philips et vos lumieres Hue via commandes vocales.

### Equipements supportes

| Equipement | IP | Protocole |
|------------|-----|-----------|
| TV Philips 55OLED705 | 192.168.1.50 | JointSpace API + Chromecast |
| Bridge Philips Hue | 192.168.1.51 | Hue REST API |

### Mode Performance

En mode performance, les commandes domotique s'executent **sans confirmation** (latence < 200ms).

```bash
# Lancement en mode performance
lyra --performance
lyra -p

# Pendant la session
mode performance    # Active
mode default        # Desactive
```

### 📺 Commandes TV

#### Power & Volume
```
allume la TV
eteins la TV
monte le son                    # +5
baisse le son                   # -5
mets le volume a 30
coupe le son
```

#### Ambilight
```
active l'ambilight
desactive l'ambilight
ambilight mode video            # Suit l'image
ambilight mode audio            # Suit le son
ambilight mode ambiance         # Lounge light
```

#### Applications
```
quelles apps peux-tu lancer ?   # Liste: netflix, youtube, plex, disney, prime
lance Netflix
lance YouTube
lance Plex
lance Disney+
lance Prime Video
```

#### YouTube avec video specifique (Premium sans pubs!)
```
lance cette video YouTube: https://youtube.com/watch?v=dQw4w9WgXcQ
mets la video dQw4w9WgXcQ sur YouTube
youtube video pAgnJDJN4VA
```

> **YouTube Premium:** Lyra utilise ADB pour lancer les videos avec ton compte connecte sur la TV.
> Resultat: **pas de publicites** si tu as YouTube Premium!

### 💡 Commandes Lumieres Hue

#### Lumieres disponibles
| ID | Nom | Description |
|----|-----|-------------|
| 1 | Hue | Ampoule principale |
| 2 | Hue 2 | Seconde ampoule |
| 3 | Hue Back | Lumiere arriere |
| 4 | Hue Play front | Barre Play LED |
| 5 | gradient lightstrip | Bandeau LED |

#### Groupes
| ID | Nom | Contenu |
|----|-----|---------|
| 81 | Chambre a coucher | Toutes les 5 lumieres |
| 83 | TV | Zone TV |
| 84 | Coin tele | Coin tele |

#### Controle individuel
```
allume la lumiere 1
eteins la lumiere 3
mets la lumiere 1 a 50%
lumiere 2 en rouge
lumiere 1 en mode relax
```

#### Controle groupe (toutes les lumieres)
```
allume toutes les lumieres
eteins toutes les lumieres
luminosite max
toutes les lumieres en bleu
toutes en mode warm
```

#### Scenes
```
scene Batman
scene Detente
scene Concentration
scene Lecture
```

> Note: La recherche de scene est insensible aux accents (Detente = Détente)

### 🎬 Commandes mixtes

```
allume la TV et mets les lumieres en bleu
mode cinema                     # TV + Ambilight + lumieres tamisees
eteins tout
Netflix et lumieres rouges
```

### Configuration domotique

Dans `config.yaml` :

```yaml
# TV Philips
tv:
  enabled: true
  host: "192.168.1.50"
  user: "***REMOVED***"           # Genere par pairing pylips
  pass: "<64-hex-jointspace>"        # 64 chars hex

# Philips Hue
hue:
  enabled: true
  bridge_ip: "192.168.1.51"
  username: "<cle-api-hue>"       # Genere par pairing Bridge
```

### Installation domotique

```bash
# Dependances
pip install requests pyyaml phue catt

# Pairing TV (premiere fois)
cd ~/dev/pylips
python pylips.py --host 192.168.1.50 --command pair
# Entrer le PIN affiche sur la TV
# Copier user/pass dans config.yaml

# Pairing Hue (premiere fois)
# 1. Appuyer sur le bouton du Bridge
# 2. Dans les 30s:
python -c "from phue import Bridge; b = Bridge('192.168.1.51'); b.connect()"
# 3. Copier le username genere dans config.yaml
```

### YouTube Premium (ADB)

Pour utiliser ton compte YouTube Premium (sans pubs), Lyra utilise ADB :

```bash
# ADB est telecharge automatiquement au premier usage
# Premiere connexion: un popup apparait sur la TV
# -> Cliquer "Toujours autoriser depuis cet ordinateur"
```

| Composant | Chemin |
|-----------|--------|
| ADB binaire | `/tmp/platform-tools/adb` |
| Cle RSA | `~/.android/adbkey` |
| Port TV | 5555 |

### Outils domotique (28 outils)

#### TV (14 outils)
| Outil | Description |
|-------|-------------|
| `tv.power_on` | Allume la TV |
| `tv.power_off` | Eteint la TV |
| `tv.volume_up` | Volume +5 |
| `tv.volume_down` | Volume -5 |
| `tv.volume_set` | Volume = X (0-60) |
| `tv.mute` | Toggle mute |
| `tv.ambilight_on` | Active Ambilight |
| `tv.ambilight_off` | Desactive Ambilight |
| `tv.ambilight_mode` | Change mode (follow_video/audio/lounge_light) |
| `tv.list_apps` | Liste les apps |
| `tv.launch_app` | Lance une app |
| `tv.youtube_video` | Lance YouTube sur une video (ADB = Premium sans pubs) |
| `tv.get_state` | Etat de la TV |
| `tv.send_key` | Touche telecommande |

#### Hue (14 outils)
| Outil | Description |
|-------|-------------|
| `hue.turn_on_light` | Allume une lumiere |
| `hue.turn_off_light` | Eteint une lumiere |
| `hue.set_brightness` | Luminosite (0-254) |
| `hue.set_color_rgb` | Couleur RGB |
| `hue.set_color_preset` | Preset (warm/cool/relax/energize) |
| `hue.turn_on_group` | Allume un groupe |
| `hue.turn_off_group` | Eteint un groupe |
| `hue.set_group_brightness` | Luminosite groupe |
| `hue.set_group_color_rgb` | Couleur groupe |
| `hue.set_group_color_preset` | Preset groupe |
| `hue.activate_scene_by_name` | Active une scene par nom |
| `hue.get_all_lights` | Liste les lumieres |
| `hue.get_all_groups` | Liste les groupes |
| `hue.get_all_scenes` | Liste les scenes |

## Troubleshooting

### "Timeout apres 60s" sur backup_status
Le dashboard backup prend ~40s. Le timeout a ete augmente a 120s.

### Le LLM ne genere pas le JSON
Relancer Lyra pour recharger le system prompt. Le prompt demande explicitement de generer UNIQUEMENT le JSON.

### Operations async ne fonctionnent pas
Verifier que le fichier sudoers `/etc/sudoers.d/lyra` existe et contient les bonnes regles NOPASSWD.

### Erreur CUDA/Whisper
Le script `run.sh` configure automatiquement `LD_LIBRARY_PATH`. Utiliser `./run.sh` au lieu de `python main.py`.

### TV ne repond pas (401 Unauthorized)
Les credentials TV ont expire ou sont incorrects. Refaire le pairing :
```bash
cd ~/dev/pylips
python pylips.py --host 192.168.1.50 --command pair
```

### YouTube ne se lance pas sur la video
Lyra utilise ADB pour lancer YouTube (avec compte Premium).
Si ADB echoue, verifier :
```bash
# Verifier connexion ADB
/tmp/platform-tools/adb devices
# Si "unauthorized", accepter le popup sur la TV
/tmp/platform-tools/adb connect 192.168.1.50:5555
```
Fallback: `catt` est utilise si ADB echoue (mais avec pubs).

### YouTube avec pubs malgre Premium
Verifier que tu es connecte a ton compte Premium sur l'app YouTube de la TV.
Si Lyra affiche "Lecture (Cast)" au lieu de "YouTube Premium", c'est le fallback catt.

### Hue "group not found"
Utiliser `group_id=81` (Chambre a coucher) au lieu de `group_id=0`.
Verifier les groupes disponibles : "liste les groupes Hue"

### Scene Hue introuvable
Utiliser le nom de la scene (ex: "Batman", "Detente") et non l'ID.
La recherche est insensible aux accents.

### Ambilight reste blanc
L'API necessite le parametre `menuSetting`. Ce bug a ete corrige dans pylips-mcp.
