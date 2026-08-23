import type { ReactNode } from 'react'

// Primitives du design system neutroncore (tokens dans styles.css) —
// version installeur : le panneau d'aide contextuelle est retire.

export function Card({ title, lite, children, style, tour }: {
  title?: string; lite?: string; children: ReactNode
  style?: React.CSSProperties; tour?: string
}) {
  return (
    <div className="card" style={style} data-tour={tour}>
      {title && (
        <h3>
          {title}
          {lite && <span className="lite">{lite}</span>}
        </h3>
      )}
      {children}
    </div>
  )
}

export function Dot({ s }: { s: 'ok' | 'warn' | 'crit' | 'off' }) {
  return <span className={`dot ${s}`} />
}

export function Chip({ tone, children }: { tone?: 'gold' | 'rose' | 'ok' | 'warn' | 'crit'; children: ReactNode }) {
  return <span className={`chip ${tone ?? ''}`}>{children}</span>
}

export function Bar({ pct, tone }: { pct: number; tone?: 'ok' | 'warn' | 'crit' }) {
  return (
    <div className={`bar ${tone ?? ''}`}>
      <i style={{ width: `${Math.max(0, Math.min(100, pct))}%` }} />
    </div>
  )
}

export function Btn({ solid, danger, sm, onClick, disabled, children }: {
  solid?: boolean; danger?: boolean; sm?: boolean; onClick?: () => void; disabled?: boolean; children: ReactNode
}) {
  return (
    <button
      className={`btn ${solid ? 'solid' : ''} ${danger ? 'danger' : ''} ${sm ? 'sm' : ''}`}
      onClick={onClick}
      disabled={disabled}
    >
      {children}
    </button>
  )
}

export function Eyebrow({ children }: { children: ReactNode }) {
  return <div className="eyebrow">{children}</div>
}

export function PageTitle({ title, desc }: { title: string; desc: string }) {
  return (
    <>
      <div className="ptitle">
        <span className="t">{title}</span>
      </div>
      <div className="pdesc">{desc}</div>
    </>
  )
}

// Chargement localise : a placer DANS la zone concernee (pas plein ecran)
export function Loader({ label }: { label?: string }) {
  return (
    <div className="loader-zone">
      <span className="spinner" />
      {label ?? 'chargement…'}
    </div>
  )
}
