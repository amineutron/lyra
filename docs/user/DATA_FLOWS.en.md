# Lyra Data Flows: What Is Captured, Stored, and Transmitted

*[Version française](DATA_FLOWS.md) | English version*

Lyra is **local by default**: speech processing, the LLM, search indexing, and tool execution run entirely on your machine. This document addresses the questions an IT security lead asks before deploying an assistant that listens and acts.

## What Lyra Captures and Where It Goes

| Data | Captured by | Stored where | Retention duration | How to purge |
|---|---|---|---|---|
| Voice (microphone) | `sounddevice`, voice mode only | Never written to disk: transcribed in memory via faster-whisper then discarded | 0 | Nothing to do |
| Request and response text | Daemon | `data/session_history.db` (SQLite, unencrypted) | Sliding window of the last 15 interactions | `rm data/session_history.db` |
| User feedback ("good / bad") | RAG enhanced | `data/feedback.json` | Until manual deletion | `rm data/feedback.json` |
| Tool specification index | RAG indexer | `.chromadb/` (local embeddings) | Until re-indexed | `rm -rf .chromadb && make index` |
| Settings (voice, models) | `/setting` menu | `~/.lyra/settings.json` | Until modified | Delete the file |
| Errors | Error log | `~/.lyra/logs/errors/` | Rotated by daemon | Delete the directory |
| Daemon socket | Daemon | `~/.lyra/lyra.sock` (UNIX socket, 0600 permissions) | Process runtime | Automatic |
| MCP action log | mcp-tracking | `~/.local/state/tracking/` (via local API 127.0.0.1:8765) | Automatic purge (7 days after completion) | Tracking API |

None of these files are ever sent externally. Secrets (tokens, equipment passwords) reside in `secrets.yaml` and are never written to logs.

## Outbound Network Connections (All Optional)

| Outbound target | Destination | Enabled by | Data sent |
|---|---|---|---|
| Remote Ollama | Host configured via `--ollama-host` or `llm.base_url` | You, during setup | Prompt text over HTTP on your network; defaults to `localhost:11434` |
| mcp-tracking | `127.0.0.1:8765` (local) | `tracking.enabled` | Name and progress of long-running actions |
| n8n | `n8n.base_url` (defaults to `localhost:5678`) | `n8n.enabled` | Triggering asynchronous workflows (VM clones, backups) |
| Discord | `discord.webhook_url` | `discord.enabled` **and** a webhook set in `secrets.yaml` | Task completion and error notifications (title, status) |
| Home Assistant | `homeassistant.url` | `homeassistant.enabled` **and** an API token | Home automation commands |
| Notion | Notion API | `notion.enabled` (disabled by default) **and** an API token | Workflow logs |
| Installer | `ollama.com`, `huggingface.co`, `pypi.org` | Installation time only | Model weights, Piper binary, and Python package dependencies |

Without explicit configuration (tokens, URLs), each outbound route remains inactive: `enabled: true` alone does not activate them. For strictly offline operation, set `enabled: false` for n8n, Discord, Home Assistant, and Notion, and point Ollama to the local machine.

## What Lyra Never Does

- **No calls to third-party cloud LLM APIs** (OpenAI, Google, Anthropic, etc.): no cloud client exists in the codebase.
- **No telemetry or analytics**: zero usage counters or tracking data sent to authors.
- **No sensitive execution without human confirmation**: see the Security section in README.

## Verify for Yourself

```bash
grep -rn "https\?://" lyra modules | grep -v "127.0.0.1\|localhost"   # the only external URLs are those listed above
ss -tnp | grep python                                                   # active connections opened by the daemon
```
