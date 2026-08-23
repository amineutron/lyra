import { Btn, Card, Chip, PageTitle } from '../components/ui'

// Ecran 5 : recap final — succes (commandes utiles) ou echec (erreur).

function Cmd({ children }: { children: string }) {
  return (
    <div className="mono" style={{
      background: 'var(--surface2)', border: '1px solid var(--line)',
      borderRadius: 8, padding: '8px 12px', fontSize: 12, marginBottom: 8,
      overflowX: 'auto', whiteSpace: 'nowrap',
    }}>
      <span style={{ color: 'var(--faint)' }}>$ </span>{children}
    </div>
  )
}

export function Done({ ok, error, demo, onRestart }: {
  ok: boolean; error: string; demo: boolean; onRestart: () => void
}) {
  if (!ok) {
    return (
      <>
        <PageTitle title="echec de l'installation" desc="Le pipeline s'est arrete sur une erreur." />
        <div style={{ maxWidth: 620 }}>
          <Card title="que s'est-il passe ?">
            <div style={{
              padding: '10px 12px', borderLeft: '2px solid var(--crit)',
              background: 'var(--rose-soft)', borderRadius: '0 8px 8px 0',
              fontFamily: 'var(--mono)', fontSize: 12, marginBottom: 14,
              whiteSpace: 'pre-wrap',
            }}>
              {error || 'erreur inconnue'}
            </div>
            <p style={{ fontSize: 12.5, color: 'var(--muted)', marginBottom: 14 }}>
              Le journal complet est visible sur l'ecran precedent. Corrige la
              cause puis relance : le pipeline reprend proprement depuis le debut
              (les etapes deja faites sont rapides).
            </p>
            <Btn solid onClick={onRestart}>recommencer</Btn>
          </Card>
        </div>
      </>
    )
  }
  return (
    <>
      <PageTitle title="installation terminee" desc="Lyra est prete — tout tourne en local." />
      <div style={{ maxWidth: 620 }}>
        <Card title="et maintenant ?">
          <div style={{ display: 'flex', gap: 8, marginBottom: 14 }}>
            <Chip tone="ok">succes</Chip>
            {demo && <Chip tone="gold">mode demo — rien n'a ete installe</Chip>}
          </div>
          <p style={{ fontSize: 12.5, color: 'var(--muted)', marginBottom: 10 }}>
            Parler a Lyra depuis un terminal :
          </p>
          <Cmd>lyra "liste mes VMs"</Cmd>
          <Cmd>lyra</Cmd>
          <p style={{ fontSize: 12.5, color: 'var(--muted)', margin: '14px 0 10px' }}>
            Suivre le demon (logs en continu) :
          </p>
          <Cmd>journalctl --user -u lyra-daemon -f</Cmd>
          <div style={{ marginTop: 16 }}>
            <Btn onClick={onRestart}>relancer l'installeur</Btn>
          </div>
        </Card>
      </div>
    </>
  )
}
