const THEME_STORAGE_KEY = 'litethaus-theme'

let currentPref = localStorage.getItem(THEME_STORAGE_KEY) ?? 'system'
let mediaQuery: MediaQueryList | null = null
let mediaListener: (() => void) | null = null

function resolveIsDark(pref: string): boolean {
  if (pref === 'dark') return true
  if (pref === 'light') return false
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

function apply(): void {
  document.documentElement.classList.toggle('dark', resolveIsDark(currentPref))
}

apply()

export function setThemePreference(pref: string): void {
  currentPref = pref
  localStorage.setItem(THEME_STORAGE_KEY, pref)
  apply()

  mediaQuery ??= window.matchMedia('(prefers-color-scheme: dark)')

  if (pref === 'system') {
    if (!mediaListener) {
      mediaListener = apply
      mediaQuery.addEventListener('change', mediaListener)
    }
  } else if (mediaListener) {
    mediaQuery.removeEventListener('change', mediaListener)
    mediaListener = null
  }
}
