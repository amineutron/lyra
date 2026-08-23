import { useEffect, useRef, useState } from 'react'
import { apiGet, type SysInfo } from '../lib/api'
import { getSettings } from '../lib/settings'
import { Mascot } from './Mascot'

// Animation de lancement : allumage du reacteur (smooth) puis wordmark LYRA
// et log de boot en ASCII (TUI). Le log affiche la detection REELLE du
// systeme (GET /api/sysinfo). Toujours passable au clic ou a la touche.

const WORDMARK = [
  '    ____  ______  ___ ',
  '   / /\\ \\/ / __ \\/   |',
  '  / /  \\  / /_/ / /| |',
  ' / /___/ / _, _/ ___ |',
  '/_____/_/_/ |_/_/  |_|',
]

type Line = { text: string; value: string; tone: 'ok' | 'warn' | 'crit' }

export function BootSplash({ onDone }: { onDone: () => void }) {
  const [phase, setPhase] = useState(0)      // 0 reacteur, 1 wordmark, 2 log, 3 sortie
  const [shown, setShown] = useState(0)      // lignes de log revelees
  const [lines, setLines] = useState<Line[]>([])
  const doneRef = useRef(false)
  const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

  const finish = () => {
    if (doneRef.current) return
    doneRef.current = true
    setPhase(3)
    setTimeout(onDone, 420)
  }

  // Detection reelle du systeme (le log n'est pas decoratif)
  useEffect(() => {
    let alive = true
    const detect = async () => {
      const out: Line[] = []
      try {
        const s = await apiGet<SysInfo>('/api/sysinfo')
        out.push({
          text: 'systeme', value: s.os,
          tone: s.supported ? 'ok' : 'warn',
        })
        out.push({
          text: 'famille', value: s.supported ? s.family : `${s.family} (non supportee)`,
          tone: s.supported ? 'ok' : 'crit',
        })
        out.push({ text: 'python', value: s.python, tone: 'ok' })
        out.push({ text: 'dossier lyra', value: s.lyra_dir, tone: 'ok' })
      } catch {
        out.push({ text: 'backend installeur', value: 'injoignable', tone: 'crit' })
      }
      out.push({ text: 'interface', value: 'prete', tone: 'ok' })
      if (alive) setLines(out)
    }
    detect()
    return () => { alive = false }
  }, [])

  // Enchainement des phases
  useEffect(() => {
    if (reduced) { finish(); return }
    const t1 = setTimeout(() => setPhase(1), 620)
    const t2 = setTimeout(() => setPhase(2), 1250)
    return () => { clearTimeout(t1); clearTimeout(t2) }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Revelation des lignes de log une par une
  useEffect(() => {
    if (phase !== 2 || lines.length === 0) return
    if (shown >= lines.length) {
      const t = setTimeout(finish, 900)
      return () => clearTimeout(t)
    }
    const t = setTimeout(() => setShown((n) => n + 1), 180)
    return () => clearTimeout(t)
  }, [phase, shown, lines.length]) // eslint-disable-line react-hooks/exhaustive-deps

  // Passer : clic, touche, ou fin naturelle
  useEffect(() => {
    const skip = () => finish()
    window.addEventListener('keydown', skip)
    window.addEventListener('pointerdown', skip)
    return () => {
      window.removeEventListener('keydown', skip)
      window.removeEventListener('pointerdown', skip)
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const s = getSettings()
  return (
    <div className={`boot ${phase === 3 ? 'out' : ''}`} role="presentation">
      <div className="boot-core" />
      {phase >= 1 && (
        <pre className="boot-wm" aria-label="LYRA">
          {WORDMARK.join('\n')}
        </pre>
      )}
      {phase >= 1 && <div className="boot-sub">installeur · assistant devops vocal</div>}
      {phase >= 2 && (
        <div className="boot-log">
          {lines.slice(0, shown).map((l, i) => (
            <div className="boot-line" key={i}>
              <span className="lbl">{l.text}</span>
              <span className="dots" />
              <span className={`val ${l.tone}`}>{l.value}</span>
            </div>
          ))}
          {shown < lines.length && <span className="boot-cursor" />}
        </div>
      )}
      {phase >= 2 && s.mascots && (
        <div className="boot-mascot">
          <Mascot kind="fast" name={s.mascotFast} state={shown >= lines.length ? 'ok' : 'busy'} size={9} />
        </div>
      )}
      <div className="boot-skip">toucher pour passer</div>
    </div>
  )
}
