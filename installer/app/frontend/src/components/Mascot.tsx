import { useEffect, useState } from 'react'
import mascotData from '@mascots'
import { getSettings } from '../lib/settings'
import { getActivity, subscribe, type MascotKind, type MascotState } from '../lib/mascotBus'

// Donnees du fichier mascottes partage avec le TUI (installer/assets/mascots.json) :
// 15 rapides + 15 lentes, chaque etat = frames ASCII 9x5 animees.
type MascotDef = { n: string; c: string; ms: number; role: string; states: Record<string, string[][]> }
const DATA = mascotData as unknown as { fast: MascotDef[]; slow: MascotDef[] }

export const MASCOTS: Record<MascotKind, { name: string; role: string }[]> = {
  fast: DATA.fast.map((m) => ({ name: m.n, role: m.role })),
  slow: DATA.slow.map((m) => ({ name: m.n, role: m.role })),
}

const STATE_COLOR: Record<MascotState, string> = {
  idle: 'var(--muted)', sleep: 'var(--faint)', busy: 'var(--gold)',
  work: 'var(--rose)', ok: 'var(--ok)', err: 'var(--crit)',
}

export function find(kind: MascotKind, name: string): MascotDef {
  const list = DATA[kind]
  return list.find((m) => m.n === name) ?? list[10] ?? list[0]
}

/** Rendu d'une mascotte ASCII animee. state fixe (preview) ou live (bus). */
export function Mascot({ kind, name, state, size = 13, live }: {
  kind: MascotKind; name: string; state?: MascotState; size?: number; live?: boolean
}) {
  const def = find(kind, name)
  const [liveState, setLiveState] = useState<MascotState>(() => getActivity(kind))
  const [frame, setFrame] = useState(0)
  const current: MascotState = live ? liveState : (state ?? 'idle')

  useEffect(() => {
    if (!live) return
    return subscribe((k, s) => { if (k === kind) setLiveState(s) })
  }, [kind, live])

  const frames = def.states[current] ?? def.states.idle
  useEffect(() => {
    setFrame(0)
    if (frames.length <= 1) return
    const speed = Math.max(0.25, getSettings().mascotSpeed || 1)
    const ms = ((current === 'busy' || current === 'work') ? def.ms : def.ms * 2.2) / speed
    const t = setInterval(() => setFrame((f) => (f + 1) % frames.length), ms)
    return () => clearInterval(t)
  }, [current, def, frames.length])

  return (
    <pre
      aria-label={`${def.n} — ${current}`}
      style={{
        fontFamily: 'var(--mono)', fontWeight: 400, fontSize: size, lineHeight: 1.18,
        letterSpacing: '0.06em', color: STATE_COLOR[current], margin: 0,
        transition: 'color .4s ease', userSelect: 'none',
      }}
    >{(frames[frame % frames.length] ?? frames[0]).join('\n')}</pre>
  )
}
