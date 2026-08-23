import { useEffect, useRef, useState } from 'react'
import { apiPost, streamEvents, type InstallEvent } from '../lib/api'
import { setActivity } from '../lib/mascotBus'
import { Reactor, type SubSystem } from '../components/Reactor'
import { Bar, Btn, Card, Chip, Eyebrow, PageTitle } from '../components/ui'
import type { DeviceConfig } from './Configure'

// Ecran 4 : execution du pipeline — frise, etapes, journal, reacteur, prompts.

type StepInfo = { id: string; label: string }
type StepState = { status: string; detail: string }
type AskEv = Extract<InstallEvent, { type: 'ask' }>

const ICON: Record<string, string> = { ok: '[ok]', run: '[>>]', err: '[!]', skip: '[--]', wait: '[ ]' }
const REACTOR_STATE: Record<string, SubSystem['state']> = { ok: 'ok', run: 'warn', err: 'crit', skip: 'off', wait: 'off' }

function AskModal({ ask, onAnswer }: { ask: AskEv; onAnswer: (v: unknown) => void }) {
  const secret = /token|mot de passe|cle|clef|passe|password/i.test(ask.prompt)
  const [val, setVal] = useState(() => (typeof ask.default === 'string' ? ask.default : ''))
  return (
    <div className="pre-modal">
      <div className="inner" style={{ minWidth: 'min(430px, 92vw)' }}>
        <div className="head">lyra a besoin d'une reponse</div>
        <div style={{ padding: '14px 16px' }}>
          <p style={{ fontSize: 13, marginBottom: 14, whiteSpace: 'pre-line' }}>{ask.prompt}</p>
          {ask.kind === 'input' ? (
            <>
              <div className="lyra-input" style={{ margin: '0 0 12px' }}>
                <input
                  type={secret ? 'password' : 'text'} value={val} autoFocus
                  aria-label={ask.prompt} placeholder={secret ? 'secret' : 'reponse'}
                  onChange={(e) => setVal(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && onAnswer(val)}
                />
              </div>
              <Btn solid onClick={() => onAnswer(val)}>valider</Btn>
            </>
          ) : (
            <div style={{ display: 'flex', gap: 10 }}>
              <Btn solid onClick={() => onAnswer(true)}>oui</Btn>
              <Btn onClick={() => onAnswer(false)}>non</Btn>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export function Install({ mcps, deviceConfig, demo, onDone }: {
  mcps: string[]; deviceConfig: DeviceConfig; demo: boolean
  onDone: (ok: boolean, error: string) => void
}) {
  const [steps, setSteps] = useState<StepInfo[]>([])
  const [states, setStates] = useState<Record<string, StepState>>({})
  const [logs, setLogs] = useState<string[]>([])
  const [ask, setAsk] = useState<AskEv | null>(null)
  const [result, setResult] = useState<{ ok: boolean; error: string } | null>(null)
  const [startErr, setStartErr] = useState('')
  const [showLog, setShowLog] = useState(false)
  const started = useRef(false)
  const logEnd = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (started.current) return   // StrictMode : un seul lancement
    started.current = true
    const abort = new AbortController()
    const onEvent = (ev: InstallEvent) => {
      if (ev.type === 'steps') setSteps(ev.steps)
      else if (ev.type === 'step') {
        setStates((s) => ({ ...s, [ev.step_id]: { status: ev.status, detail: ev.detail } }))
        if (ev.status === 'run') setActivity('fast', 'work')
        else if (ev.status === 'err') setActivity('fast', 'err', 0, 'erreur — clic pour acquitter')
      } else if (ev.type === 'output') setLogs((l) => [...l.slice(-400), ev.line])
      else if (ev.type === 'progress') {
        setStates((s) => ({ ...s, [ev.step_id]: { status: s[ev.step_id]?.status ?? 'run', detail: ev.detail } }))
      } else if (ev.type === 'ask') { setAsk(ev); setActivity('fast', 'busy', 0, 'attend ta reponse') }
      else if (ev.type === 'result') {
        setResult({ ok: ev.ok, error: ev.error })
        setActivity('fast', ev.ok ? 'ok' : 'err', ev.ok ? 6000 : 0)
      }
    }
    const run = async () => {
      setActivity('fast', 'busy')
      try {
        await apiPost('/api/install', { mcps, device_config: deviceConfig, options: { demo } })
        await streamEvents(onEvent, abort.signal)
      } catch (e) {
        if (!abort.signal.aborted) {
          setStartErr((e as Error).message)
          setActivity('fast', 'err', 0, 'erreur — clic pour acquitter')
        }
      }
    }
    run()
    return () => abort.abort()
  }, [mcps, deviceConfig, demo])

  useEffect(() => { logEnd.current?.scrollIntoView({ behavior: 'smooth' }) }, [logs, showLog])

  const answer = async (value: unknown) => {
    if (!ask) return
    setAsk(null)
    setActivity('fast', 'work')
    try { await apiPost('/api/answer', { ask_id: ask.ask_id, value }) } catch { /* pipeline deja parti */ }
  }

  const finished = steps.filter((s) => ['ok', 'skip'].includes(states[s.id]?.status ?? '')).length
  const pct = steps.length > 0 ? (finished / steps.length) * 100 : 0
  const errCount = steps.filter((s) => states[s.id]?.status === 'err').length
  const systems: SubSystem[] = steps.map((s) => ({
    label: s.label, state: REACTOR_STATE[states[s.id]?.status ?? 'wait'] ?? 'off',
  }))

  return (
    <>
      <PageTitle title="installation" desc={demo
        ? 'Simulation complete du pipeline — aucune commande reelle.'
        : 'Le pipeline s’execute — chaque etape est suivie en temps reel.'} />
      {startErr && <Chip tone="crit">echec du lancement : {startErr}</Chip>}
      <div className="pipe scroll-x" style={{ marginBottom: 16, paddingBottom: 4 }}>
        {steps.map((s, i) => {
          const st = states[s.id]?.status ?? 'wait'
          const cls = st === 'ok' || st === 'skip' ? 'done' : st === 'run' ? 'run' : ''
          return (
            <span key={s.id} style={{ display: 'contents' }}>
              {i > 0 && <span className={`link ${cls === 'done' ? 'done' : ''}`} />}
              <span className={`step ${cls}`}><span className="n">{i + 1}</span>{s.label}</span>
            </span>
          )
        })}
      </div>
      <div className="grid g2" style={{ alignItems: 'start' }}>
        <div className="sess" style={{ marginBottom: 0 }}>
          <div className="head" style={{ cursor: 'default' }}>
            <Chip tone={result ? (result.ok ? 'ok' : 'crit') : 'gold'}>
              {result ? (result.ok ? 'terminee' : 'echec') : 'en cours'}
            </Chip>
            <span className="nm">installation de Lyra</span>
            <span className="num" style={{ fontSize: 11, color: 'var(--muted)' }}>{Math.round(pct)}%</span>
          </div>
          <Bar pct={result?.ok ? 100 : pct} tone={result ? (result.ok ? 'ok' : 'crit') : undefined} />
          <div className="items">
            {steps.map((s) => {
              const st = states[s.id]
              const status = st?.status ?? 'wait'
              return (
                <div key={s.id} className={`item ${status === 'ok' ? 'done' : status === 'run' ? 'run' : status === 'err' ? 'err' : ''}`}>
                  <span className="ic">{ICON[status] ?? '[ ]'}</span>
                  {s.label}
                  {st?.detail && (
                    <span style={{ color: status === 'err' ? 'var(--crit)' : 'var(--faint)', fontSize: 10, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      — {st.detail}
                    </span>
                  )}
                </div>
              )
            })}
          </div>
          <div style={{ marginTop: 12, display: 'flex', gap: 10, alignItems: 'center' }}>
            <Btn sm onClick={() => setShowLog((v) => !v)}>
              {showLog ? 'masquer le journal' : `journal (${logs.length})`}
            </Btn>
            {result && (
              <Btn sm solid onClick={() => onDone(result.ok, result.error)}>
                {result.ok ? 'voir le recap' : 'voir le detail de l’erreur'}
              </Btn>
            )}
          </div>
          {showLog && (
            <div className="sess-detail" style={{ maxHeight: 260, overflowY: 'auto' }}>
              {logs.map((l, i) => <div className="logline" key={i}>{l}</div>)}
              {logs.length === 0 && <div style={{ color: 'var(--faint)' }}>pas encore de logs</div>}
              <div ref={logEnd} />
            </div>
          )}
        </div>
        <div>
          <Eyebrow>reacteur</Eyebrow>
          <Card style={{ padding: 0, border: 'none', background: 'transparent' }}>
            <Reactor systems={systems} alertCount={errCount} />
          </Card>
        </div>
      </div>
      {ask && <AskModal ask={ask} onAnswer={answer} />}
    </>
  )
}
