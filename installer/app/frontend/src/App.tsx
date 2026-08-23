import { useEffect, useState } from 'react'
import { apiGet, type McpDef } from './lib/api'
import { applySettings, getSettings, saveSettings, THEMES } from './lib/settings'
import { Mascot } from './components/Mascot'
import { Welcome } from './screens/Welcome'
import { SelectMcps } from './screens/SelectMcps'
import { Configure, type DeviceConfig } from './screens/Configure'
import { Install } from './screens/Install'
import { Done } from './screens/Done'

// Installeur = WIZARD lineaire (pas de nav libre) :
// welcome -> select -> configure -> install -> done

type Step = 'welcome' | 'select' | 'configure' | 'install' | 'done'
const STEP_LABEL: Record<Step, string> = {
  welcome: 'bienvenue', select: 'serveurs mcp', configure: 'configuration',
  install: 'installation', done: 'fin',
}

const DEMO_FROM_URL = new URLSearchParams(window.location.search).has('demo')

export default function App() {
  const [step, setStep] = useState<Step>('welcome')
  const [catalog, setCatalog] = useState<McpDef[]>([])
  const [demo, setDemo] = useState(DEMO_FROM_URL)
  const [selected, setSelected] = useState<string[]>([])
  const [deviceConfig, setDeviceConfig] = useState<DeviceConfig>({})
  const [result, setResult] = useState<{ ok: boolean; error: string }>({ ok: false, error: '' })
  const [theme, setTheme] = useState(() => getSettings().theme)
  const settings = getSettings()

  useEffect(() => { applySettings() }, [])

  useEffect(() => {
    apiGet<McpDef[]>('/api/catalog')
      .then((c) => {
        setCatalog(c)
        setSelected(c.filter((m) => m.installable && m.default_checked).map((m) => m.id))
      })
      .catch(() => setCatalog([]))
  }, [])

  const toggle = (id: string) =>
    setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]))

  const cycleTheme = () => {
    const idx = THEMES.findIndex((t) => t.id === theme)
    const next = THEMES[(idx + 1) % THEMES.length].id
    saveSettings({ theme: next })
    setTheme(next)
  }

  const selectedMcps = catalog.filter((m) => selected.includes(m.id))

  return (
    <div className="app" style={{ gridTemplateColumns: '1fr' }}>
      <div className="main">
        <div className="topbar">
          <span className="sys-chip" style={{ border: 'none', padding: 0 }}>
            <span className="core" />
          </span>
          <span className="crumb" style={{ fontSize: 13 }}>
            <span className="mono" style={{ fontWeight: 600, color: 'var(--text)' }}>
              lyra<i style={{ fontStyle: 'normal', background: 'linear-gradient(100deg,var(--rose),var(--gold))', WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent' }}>.installeur</i>
            </span>
            {' '}/ <b>{STEP_LABEL[step]}</b>
          </span>
          <span className="grow" />
          <button className="btn sm" onClick={cycleTheme} aria-label="Changer de theme">
            theme : {THEMES.find((t) => t.id === theme)?.label}
          </button>
          {settings.mascots && step !== 'welcome' && (
            <Mascot kind="fast" name={settings.mascotFast} live size={7} />
          )}
        </div>
        <section className="content on">
          {step === 'welcome' && (
            <Welcome demoDefault={demo} onContinue={(d) => { setDemo(d); setStep('select') }} />
          )}
          {step === 'select' && (
            <SelectMcps
              catalog={catalog} selected={selected} onToggle={toggle}
              onBack={() => setStep('welcome')}
              onContinue={() => setStep('configure')}
            />
          )}
          {step === 'configure' && (
            <Configure
              mcps={selectedMcps} previous={deviceConfig}
              onBack={() => setStep('select')}
              onContinue={(cfg) => { setDeviceConfig(cfg); setStep('install') }}
            />
          )}
          {step === 'install' && (
            <Install
              mcps={selected} deviceConfig={deviceConfig} demo={demo}
              onDone={(ok, error) => { setResult({ ok, error }); setStep('done') }}
            />
          )}
          {step === 'done' && (
            <Done
              ok={result.ok} error={result.error} demo={demo}
              onRestart={() => { setDeviceConfig({}); setStep('welcome') }}
            />
          )}
        </section>
      </div>
    </div>
  )
}
