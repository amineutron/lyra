# Lyra data flows: what is captured, what is kept, what leaves the machine

*Version française : [DATA_FLOWS.md](DATA_FLOWS.md).*

Lyra is **local by default**: speech processing, the LLM, search and tool execution run on your machine. This page answers the questions an IT manager asks before installing an assistant that listens and acts.

## What Lyra captures and where it goes

| Data | Captured by | Stored where | How long | Purge |
|---|---|---|---|---|
| Voice (microphone) | `sounddevice`, in voice mode only | never written to disk: transcribed in memory by faster-whisper, then discarded | 0 | nothing to do |
| Text of requests and answers | the daemon | `data/session_history.db` (SQLite, plain text) | sliding window of the last 15 exchanges | `rm data/session_history.db` |
| User feedback ("that was right / wrong") | enhanced RAG | `data/feedback.json` | until deleted | `rm data/feedback.json` |
| Index of tool specifications | RAG indexer | `.chromadb/` (local embeddings) | until reindexing | `rm -rf .chromadb && make index` |
| Settings (voice, models) | `/setting` menu | `~/.lyra/settings.json` | until changed | delete the file |
| Errors | error log | `~/.lyra/logs/errors/` | rotated by the daemon | delete the folder |
| Daemon socket | daemon | `~/.lyra/lyra.sock` (UNIX, mode 0600) | while running | automatic |
| Log of MCP actions | mcp-tracking | `~/.local/state/tracking/` (through the local API 127.0.0.1:8765) | purged automatically (7 days after completion) | tracking API |

None of these files is sent anywhere. Secrets (tokens, device passwords) live in `secrets.yaml`, never in the logs.

## Network outputs, all optional

| Output | To | Enabled by | What leaves |
|---|---|---|---|
| Remote Ollama | the host given by `--ollama-host` or `llm.base_url` | you, at install time | the text of requests, over HTTP on your network; `localhost:11434` by default |
| mcp-tracking | `127.0.0.1:8765` (local) | `tracking.enabled` | name and progress of long actions |
| n8n | `n8n.base_url` (`localhost:5678` by default) | `n8n.enabled` | triggers for asynchronous tasks (VM clone, backup) |
| Discord | `discord.webhook_url` | `discord.enabled` **and** a webhook set in `secrets.yaml` | end-of-task and error notifications (title, status) |
| Home Assistant | `homeassistant.url` | `homeassistant.enabled` **and** a token | home automation commands |
| Notion | Notion API | `notion.enabled` (off by default) **and** a token | workflow log |
| Installer | `ollama.com`, `huggingface.co`, `pypi.org` | at install time only | download of models, Piper and dependencies |

Without explicit configuration (token, URL), each of these outputs stays inactive: `enabled: true` alone is not enough. For strictly offline use, set `enabled: false` on n8n, Discord, Home Assistant and Notion, and point Ollama to the local machine.

## What Lyra never does

- No call to an online LLM provider (OpenAI, Google, Anthropic…): there is no client for that in the code.
- No telemetry, no usage counter sent to the author.
- No sensitive action without human confirmation: see the Security section of the README.

## Check for yourself

```bash
grep -rn "https\?://" lyra modules | grep -v "127.0.0.1\|localhost"   # the only external URLs are the ones above
ss -tnp | grep python                                                   # connections opened by the daemon
```
