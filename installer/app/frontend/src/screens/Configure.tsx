import { useState } from 'react'
import type { McpDef } from '../lib/api'
import { Btn, Card, Chip, PageTitle } from '../components/ui'

// Ecran 3 : formulaires generes depuis les champs des MCPs coches.
// Validation simple : champ non vide sauf s'il est optionnel.

export type DeviceConfig = Record<string, Record<string, string>>

function initialValues(mcps: McpDef[], previous: DeviceConfig): DeviceConfig {
  const out: DeviceConfig = {}
  for (const m of mcps) {
    if (m.fields.length === 0) continue
    out[m.id] = {}
    for (const f of m.fields) {
      out[m.id][f.key] = previous[m.id]?.[f.key] ?? f.default ?? ''
    }
  }
  return out
}

export function Configure({ mcps, previous, onBack, onContinue }: {
  mcps: McpDef[]                       // MCPs coches uniquement
  previous: DeviceConfig
  onBack: () => void
  onContinue: (config: DeviceConfig) => void
}) {
  const withFields = mcps.filter((m) => m.fields.length > 0)
  const [values, setValues] = useState<DeviceConfig>(() => initialValues(withFields, previous))
  const [touched, setTouched] = useState(false)

  const set = (mcpId: string, key: string, val: string) =>
    setValues((v) => ({ ...v, [mcpId]: { ...v[mcpId], [key]: val } }))

  const missing: string[] = []
  for (const m of withFields) {
    for (const f of m.fields) {
      if (!f.optional && !(values[m.id]?.[f.key] ?? '').trim()) {
        missing.push(`${m.name} — ${f.label}`)
      }
    }
  }

  const submit = () => {
    setTouched(true)
    if (missing.length > 0) return
    // ne transmettre que les valeurs non vides (les optionnels vides sont omis)
    const clean: DeviceConfig = {}
    for (const [mcpId, fields] of Object.entries(values)) {
      const kept = Object.fromEntries(
        Object.entries(fields).filter(([, v]) => v.trim() !== ''),
      )
      if (Object.keys(kept).length > 0) clean[mcpId] = kept
    }
    onContinue(clean)
  }

  if (withFields.length === 0) {
    return (
      <>
        <PageTitle title="configuration" desc="Aucun des serveurs choisis ne demande de reglage." />
        <div style={{ display: 'flex', gap: 10 }}>
          <Btn onClick={onBack}>retour</Btn>
          <Btn solid onClick={() => onContinue({})}>continuer</Btn>
        </div>
      </>
    )
  }

  return (
    <>
      <PageTitle
        title="configuration"
        desc="Adresses et cles des appareils — ecrites dans config.yaml et secrets.yaml (chmod 600)."
      />
      <div style={{ maxWidth: 640, display: 'flex', flexDirection: 'column', gap: 14 }}>
        {withFields.map((m) => (
          <Card key={m.id} title={m.name} lite={m.short_desc}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {m.fields.map((f) => {
                const val = values[m.id]?.[f.key] ?? ''
                const bad = touched && !f.optional && !val.trim()
                return (
                  <label key={f.key} style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                    <span className="mono" style={{ fontSize: 10.5, color: bad ? 'var(--crit)' : 'var(--faint)', letterSpacing: '.08em', textTransform: 'uppercase' }}>
                      {f.label}
                      {f.optional && <span style={{ color: 'var(--faint)', textTransform: 'none' }}> (optionnel)</span>}
                      {f.secret && <span style={{ color: 'var(--rose)', textTransform: 'none' }}> · secret</span>}
                    </span>
                    <div className="lyra-input" style={{ margin: 0, borderColor: bad ? 'var(--crit)' : undefined }}>
                      <input
                        type={f.secret ? 'password' : 'text'}
                        placeholder={f.label}
                        value={val}
                        aria-label={`${m.name} : ${f.label}`}
                        onChange={(e) => set(m.id, f.key, e.target.value)}
                      />
                    </div>
                  </label>
                )
              })}
            </div>
          </Card>
        ))}
        {touched && missing.length > 0 && (
          <Chip tone="crit">champs requis manquants : {missing.join(', ')}</Chip>
        )}
        <div style={{ display: 'flex', gap: 10 }}>
          <Btn onClick={onBack}>retour</Btn>
          <Btn solid onClick={submit}>continuer</Btn>
        </div>
      </div>
    </>
  )
}
