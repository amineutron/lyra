// Reglages persistants (localStorage) de l'installeur — theme + mascottes.
// Version simplifiee des reglages neutroncore : les 7 themes sont gardes,
// les options liees aux ecrans absents (posters, ecoPoll...) sont retirees.

export type Settings = {
  theme: 'neutron' | 'ironman' | 'matrix' | 'midnight' | 'dawn' | 'paper' | 'sky'
  mascots: boolean        // afficher les mascottes
  mascotFast: string      // nom de la mascotte rapide (header + boot)
  mascotSlow: string      // nom de la mascotte lente (non utilisee ici, gardee)
  mascotSpeed: number     // vitesse d'animation des mascottes (x0.5 a x3)
  bootAnim: boolean       // sequence de boot au lancement
}

export const THEMES: { id: Settings['theme']; label: string; dark: boolean; sw: [string, string, string] }[] = [
  { id: 'neutron', label: 'neutron', dark: true, sw: ['#0e0a10', '#f6c177', '#eb6f92'] },
  { id: 'ironman', label: 'iron man', dark: true, sw: ['#0d0d0d', '#e04a4a', '#f0a35c'] },
  { id: 'matrix', label: 'matrix', dark: true, sw: ['#050a06', '#4ade80', '#a3e635'] },
  { id: 'midnight', label: 'midnight', dark: true, sw: ['#070b16', '#6ea8fe', '#9d7bf5'] },
  { id: 'dawn', label: 'dawn', dark: false, sw: ['#faf4ed', '#c8851f', '#d4567e'] },
  { id: 'paper', label: 'paper', dark: false, sw: ['#f6f6f4', '#a06a10', '#c04a70'] },
  { id: 'sky', label: 'sky', dark: false, sw: ['#eef4fa', '#1f6fc0', '#7c5cd6'] },
]

const KEY = 'lyra_installer_settings'
const DEFAULTS: Settings = {
  theme: 'neutron',
  mascots: true,
  mascotFast: 'spark',
  mascotSlow: 'blob',
  mascotSpeed: 1,
  bootAnim: true,
}

export function getSettings(): Settings {
  try {
    return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(KEY) ?? '{}') }
  } catch {
    return { ...DEFAULTS }
  }
}

export function saveSettings(patch: Partial<Settings>): Settings {
  const next = { ...getSettings(), ...patch }
  localStorage.setItem(KEY, JSON.stringify(next))
  applySettings(next)
  return next
}

export function applySettings(s: Settings = getSettings()): void {
  const root = document.documentElement
  if (s.theme === 'neutron') delete root.dataset.theme
  else root.dataset.theme = s.theme
}
