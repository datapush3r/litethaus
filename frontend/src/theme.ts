let currentPref = 'system'
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

// Single owner of the system-preference listener, since App's initial load
// and SettingsPage's save both need to set this and the browser only has
// one "system theme changed" event to subscribe to.
export function setThemePreference(pref: string): void {
  currentPref = pref
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
