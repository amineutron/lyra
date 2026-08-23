import { useEffect, useState } from 'react'
import { apiGet, type SysInfo } from '../lib/api'
import { BootSplash } from '../components/BootSplash'
import { Btn, Card, Chip, Loader, PageTitle } from '../components/ui'
import { getSettings } from '../lib/settings'

// Ecran 1 : boot splash puis carte d'accueil (OS detecte + mode demo).

export function Welcome({ demoDefault, onContinue }: {
  demoDefault: boolean
  onContinue: (demo: boolean) => void
}) {
  const [booted, setBooted] = useState(() => !getSettings().bootAnim)
  const [sys, setSys] = useState<SysInfo | null>(null)
  const [err, setErr] = useState('')
  const [demo, setDemo] = useState(demoDefault)

  useEffect(() => {
    apiGet<SysInfo>('/api/sysinfo')
      .then(setSys)
      .catch((e) => setErr((e as Error).message))
  }, [])

  if (!booted) return <BootSplash onDone={() => setBooted(true)} />

  return (
    <>
      <PageTitle
        title="bienvenue"
        desc="Installation locale de Lyra — assistant DevOps vocal, 100 % hors ligne."
      />
      <div style={{ maxWidth: 560 }}>
        <Card title="installer Lyra">
          {sys === null && !err && <Loader label="detection du systeme…" />}
          {err && <Chip tone="crit">backend injoignable : {err}</Chip>}
          {sys && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 14 }}>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <Chip tone={sys.supported ? 'ok' : 'crit'}>{sys.os}</Chip>
                <Chip>python {sys.python}</Chip>
                <Chip>famille {sys.family}</Chip>
              </div>
              <div className="mono" style={{ fontSize: 10.5, color: 'var(--faint)' }}>
                dossier : {sys.lyra_dir}
              </div>
              {!sys.supported && (
                <div style={{
                  padding: '8px 11px', borderLeft: '2px solid var(--crit)',
                  background: 'var(--rose-soft)', borderRadius: '0 8px 8px 0',
                  fontSize: 12.5, color: 'var(--muted)',
                }}>
                  Distribution non supportee ({sys.family}) : l'installation des
                  paquets systeme echouera probablement. Le mode demo reste
                  disponible pour explorer l'installeur.
                </div>
              )}
            </div>
          )}
          <label style={{
            display: 'flex', alignItems: 'center', gap: 9, cursor: 'pointer',
            fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--muted)',
            marginBottom: 16,
          }}>
            <input
              type="checkbox" checked={demo}
              onChange={(e) => setDemo(e.target.checked)}
              style={{ accentColor: 'var(--gold)' }}
            />
            mode demo — simulation complete, aucune commande reelle
          </label>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <Btn solid disabled={sys === null} onClick={() => onContinue(demo)}>continuer</Btn>
            {demo && <Chip tone="gold">demo</Chip>}
          </div>
        </Card>
      </div>
    </>
  )
}
