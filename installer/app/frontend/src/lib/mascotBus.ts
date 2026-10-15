// Bus d'activite des mascottes — reflete en direct ce que fait l'installeur.
// fast = mascotte du header · slow = reserve (parite avec neutroncore).
//
// Les etats "err" et "attente de reponse" sont COLLANTS : ils restent affiches
// tant qu'ils ne sont pas resolus (nouvelle activite reussie, reponse donnee,
// ou clic sur la mascotte pour acquitter).

export type MascotState = 'idle' | 'busy' | 'work' | 'ok' | 'err' | 'sleep'
export type MascotKind = 'fast' | 'slow'

type Entry = { state: MascotState; reason: string }
type Listener = (kind: MascotKind, state: MascotState) => void

const state: Record<MascotKind, Entry> = {
  fast: { state: 'idle', reason: '' },
  slow: { state: 'idle', reason: '' },
}
const listeners = new Set<Listener>()
const timers: Partial<Record<MascotKind, ReturnType<typeof setTimeout>>> = {}
let sleepTimer: ReturnType<typeof setTimeout> | null = null

function emit(kind: MascotKind, s: MascotState, reason = '') {
  state[kind] = { state: s, reason }
  listeners.forEach((l) => l(kind, s))
}

function armSleep() {
  if (sleepTimer) clearTimeout(sleepTimer)
  sleepTimer = setTimeout(() => {
    (['fast', 'slow'] as MascotKind[]).forEach((k) => {
      // ne jamais endormir une erreur ou une attente : l'info doit rester visible
      if (state[k].state === 'idle') emit(k, 'sleep')
    })
  }, 90000)
}

/** Change l'etat ; holdMs > 0 = transitoire puis retour a idle (sauf si un
 *  etat collant a ete pose entre-temps). */
export function setActivity(kind: MascotKind, s: MascotState, holdMs = 0, reason = ''): void {
  if (timers[kind]) clearTimeout(timers[kind])
  emit(kind, s, reason)
  if (holdMs > 0) {
    timers[kind] = setTimeout(() => {
      if (state[kind].state === s) emit(kind, 'idle')
    }, holdMs)
  }
  armSleep()
}

export function getActivity(kind: MascotKind): MascotState {
  return state[kind].state
}

export function getReason(kind: MascotKind): string {
  return state[kind].reason
}

/** Acquitte une erreur ou une attente (clic sur la mascotte). */
export function acknowledge(kind: MascotKind): void {
  if (state[kind].state === 'err' || state[kind].reason) emit(kind, 'idle')
}

export function subscribe(l: Listener): () => void {
  listeners.add(l)
  return () => listeners.delete(l)
}
