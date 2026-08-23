import { useState } from 'react'

// Le cœur du réacteur — signature de l'accueil.
// Chaque arc = un sous-système avec SA couleur (identification claire) ;
// l'état (ok/warn/crit) est porté par la pastille de la légende et
// l'épaisseur/halo de l'arc. Cliquer un nom ou un arc isole le sous-système
// (les autres passent en gris) ; re-cliquer désélectionne.

const STATE_COLORS = { ok: '#82d69c', warn: '#f0b45e', crit: '#ff5c74', off: '#5c5262' }

// une teinte distincte par sous-système (cycle si plus de 10)
const HUES = [
  '#f6c177', '#eb6f92', '#6ea8fe', '#4ade80', '#c9a2e8',
  '#5eead4', '#f0a35c', '#ff8fab', '#a3e635', '#7dd3fc',
]

export type SubSystem = { label: string; state: keyof typeof STATE_COLORS }

export function Reactor({ systems, alertCount }: { systems: SubSystem[]; alertCount: number }) {
  const [selected, setSelected] = useState<string | null>(null)
  const n = Math.max(systems.length, 1)
  const R = 86
  const C = 100
  const gap = 5
  const seg = 360 / n

  const toggle = (label: string) => setSelected((s) => (s === label ? null : label))

  const segPath = (i: number) => {
    const a0 = ((i * seg + gap / 2 - 90) * Math.PI) / 180
    const a1 = (((i + 1) * seg - gap / 2 - 90) * Math.PI) / 180
    return `M ${C + R * Math.cos(a0)} ${C + R * Math.sin(a0)} A ${R} ${R} 0 0 1 ${C + R * Math.cos(a1)} ${C + R * Math.sin(a1)}`
  }

  const arcs = systems.map((s, i) => {
    const dimmed = selected !== null && selected !== s.label
    const isSel = selected === s.label
    const hue = HUES[i % HUES.length]
    return (
      <path
        key={s.label}
        className={`arc ${isSel ? 'sel' : ''}`}
        d={segPath(i)}
        stroke={dimmed ? 'var(--line2)' : hue}
        strokeWidth={isSel ? 11.5 : s.state === 'ok' ? 5.5 : 8}
        strokeLinecap="round"
        fill="none"
        opacity={dimmed ? 0.45 : s.state === 'off' ? 0.35 : 0.95}
        style={{ color: hue }}
      >
        {s.state === 'crit' && !dimmed && (
          <animate attributeName="opacity" values="0.95;0.35;0.95" dur="1.2s" repeatCount="indefinite" />
        )}
      </path>
    )
  })

  // zones de clic invisibles et LARGES par-dessus les arcs (un arc fin qui
  // tourne est quasi impossible à viser sinon)
  const hitAreas = systems.map((s, i) => (
    <path
      key={`hit-${s.label}`}
      d={segPath(i)}
      stroke="transparent"
      strokeWidth={26}
      strokeLinecap="round"
      fill="none"
      style={{ cursor: 'pointer', pointerEvents: 'stroke' }}
      onClick={() => toggle(s.label)}
    >
      <title>{s.label}</title>
    </path>
  ))

  return (
    <div className="reactor-card">
      <div className="eyebrow" style={{ marginBottom: 0 }}>état du réacteur</div>
      <div className="reactor">
        <div className="halo" />
        <svg viewBox="0 0 200 200" aria-label="État des sous-systèmes">
          <defs>
            <linearGradient id="cg" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0" stopColor="#eb6f92" />
              <stop offset="1" stopColor="#f6c177" />
            </linearGradient>
          </defs>
          {arcs}
          {hitAreas}
          <circle cx={C} cy={C} r={70} fill="none" stroke="url(#cg)" strokeWidth={1} opacity={0.5} strokeDasharray="2 5" />
        </svg>
        <div className="mid">
          <b>{alertCount}</b>
          <span>{alertCount === 1 ? 'alerte' : 'alertes'}</span>
        </div>
      </div>
      <div className="reactor-legend">
        {systems.map((s, i) => {
          const dimmed = selected !== null && selected !== s.label
          const hue = HUES[i % HUES.length]
          return (
            <span
              key={s.label}
              className={`pill ${selected === s.label ? 'sel' : ''}`}
              onClick={() => toggle(s.label)}
              style={{
                cursor: 'pointer',
                opacity: dimmed ? 0.35 : 1,
                color: dimmed ? 'var(--faint)' : hue,
                fontWeight: selected === s.label ? 600 : 400,
                transition: 'opacity .25s ease, color .25s ease',
              }}
            >
              <span className={`dot ${s.state}`} /> {s.label}
            </span>
          )
        })}
      </div>
      {selected && (
        <div style={{ fontFamily: 'var(--mono)', fontSize: 9.5, color: 'var(--muted)', marginTop: 8 }}>
          {selected} : {(() => {
            const st = systems.find((s) => s.label === selected)?.state
            return st === 'ok' ? 'tout va bien' : st === 'warn' ? 'attention requise' : st === 'crit' ? 'en panne' : 'inactif'
          })()} — recliquer pour tout réafficher
        </div>
      )}
    </div>
  )
}
