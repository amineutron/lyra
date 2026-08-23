import type { McpDef } from '../lib/api'
import { Btn, Chip, PageTitle } from '../components/ui'

// Ecran 2 : choix des MCPs a installer. Une carte par entree du catalogue ;
// les entrees non installables (tracking) sont informatives, non cochables.

const COLOR_MAP: Record<string, string> = {
  cyan: '#5eead4', magenta: '#eb6f92', yellow: '#f6c177', green: '#82d69c',
  blue: '#6ea8fe', red: '#ff5c74', white: 'var(--text)',
}

function McpCard({ mcp, checked, onToggle }: {
  mcp: McpDef; checked: boolean; onToggle: () => void
}) {
  const accent = COLOR_MAP[mcp.color] ?? 'var(--gold)'
  const selectable = mcp.installable
  return (
    <div
      className="card"
      onClick={selectable ? onToggle : undefined}
      style={{
        cursor: selectable ? 'pointer' : 'default',
        borderColor: checked ? `color-mix(in srgb, ${accent} 55%, var(--line))` : undefined,
        background: checked ? `linear-gradient(160deg, color-mix(in srgb, ${accent} 8%, transparent), var(--surface) 55%)` : undefined,
        opacity: selectable ? 1 : 0.8,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
        <span className="mono" style={{ color: accent, fontSize: 12, fontWeight: 600 }}>
          {mcp.icon}
        </span>
        <b className="mono" style={{ fontSize: 13 }}>{mcp.name}</b>
        <span style={{ flex: 1 }} />
        {selectable ? (
          <input
            type="checkbox" checked={checked} readOnly
            aria-label={`Installer ${mcp.name}`}
            style={{ accentColor: accent, pointerEvents: 'none' }}
          />
        ) : (
          <Chip>inclus</Chip>
        )}
      </div>
      <div style={{ fontSize: 12.5, color: 'var(--muted)', marginBottom: 6 }}>{mcp.short_desc}</div>
      <div style={{ fontSize: 12, color: 'var(--text)', whiteSpace: 'pre-line', marginBottom: 8 }}>
        {mcp.long_desc}
      </div>
      {mcp.examples.length > 0 && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 6 }}>
          {mcp.examples.map((ex) => (
            <Chip key={ex} tone="gold">« {ex} »</Chip>
          ))}
        </div>
      )}
      {mcp.notes && (
        <div style={{ fontSize: 11, color: 'var(--faint)', whiteSpace: 'pre-line' }}>{mcp.notes}</div>
      )}
    </div>
  )
}

export function SelectMcps({ catalog, selected, onToggle, onBack, onContinue }: {
  catalog: McpDef[]
  selected: string[]
  onToggle: (id: string) => void
  onBack: () => void
  onContinue: () => void
}) {
  const installables = catalog.filter((m) => m.installable)
  const infos = catalog.filter((m) => !m.installable)
  return (
    <>
      <PageTitle
        title="serveurs mcp"
        desc="Choisis les integrations a installer — chaque serveur ajoute des commandes vocales."
      />
      <div className="grid g2" style={{ alignItems: 'stretch', marginBottom: 14 }}>
        {installables.map((m) => (
          <McpCard key={m.id} mcp={m} checked={selected.includes(m.id)}
            onToggle={() => onToggle(m.id)} />
        ))}
        {infos.map((m) => (
          <McpCard key={m.id} mcp={m} checked={false} onToggle={() => undefined} />
        ))}
      </div>
      <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
        <Btn onClick={onBack}>retour</Btn>
        <Btn solid onClick={onContinue}>
          continuer ({selected.length} serveur{selected.length > 1 ? 's' : ''})
        </Btn>
      </div>
    </>
  )
}
