// Client API de l'installeur — backend local 127.0.0.1:9877, meme origine.
// Pas d'auth Bearer : le serveur n'ecoute qu'en loopback.

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message)
  }
}

async function handle<T>(r: Response): Promise<T> {
  if (!r.ok) {
    let detail = r.statusText
    try {
      detail = (await r.json()).error ?? detail
    } catch {
      /* corps non JSON */
    }
    throw new ApiError(r.status, detail)
  }
  return r.json() as Promise<T>
}

export async function apiGet<T = unknown>(path: string): Promise<T> {
  return handle<T>(await fetch(path))
}

export async function apiPost<T = unknown>(path: string, body?: unknown): Promise<T> {
  return handle<T>(
    await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  )
}

// ---- types partages avec le backend ----------------------------------

export type SysInfo = {
  os: string; family: string; supported: boolean; python: string; lyra_dir: string
}

export type FieldDef = {
  key: string; label: string; section: string
  secret: boolean; optional: boolean; default: string; help: string
}

export type McpDef = {
  id: string; name: string; color: string; icon: string
  short_desc: string; long_desc: string; notes: string; examples: string[]
  installable: boolean; default_checked: boolean; fields: FieldDef[]
}

export type InstallEvent =
  | { type: 'steps'; steps: { id: string; label: string }[] }
  | { type: 'output'; line: string }
  | { type: 'progress'; step_id: string; detail: string }
  | { type: 'step'; step_id: string; status: string; elapsed: number; detail: string }
  | { type: 'ask'; ask_id: string; kind: string; prompt: string; default: unknown; extra: Record<string, unknown> }
  | { type: 'result'; ok: boolean; error: string }

// Flux SSE des evenements d'installation, lu en streaming fetch
// (parsing identique au chat Lyra de neutroncore : decoupage "\n\n").
export async function streamEvents(
  onEvent: (ev: InstallEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const r = await fetch('/api/events', { signal })
  if (!r.ok || !r.body) throw new ApiError(r.status, 'flux d’evenements indisponible')
  const reader = r.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const parts = buffer.split('\n\n')
    buffer = parts.pop() ?? ''
    for (const part of parts) {
      const line = part.trim()
      if (line.startsWith('data: ')) {
        try {
          onEvent(JSON.parse(line.slice(6)))
        } catch {
          /* ligne partielle ignoree */
        }
      }
    }
  }
}
