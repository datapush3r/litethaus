const THEME_STORAGE_KEY = 'litethaus-theme'

// The real source of truth is config.yaml's theme field, fetched only once
// Dashboard mounts (after login) - too late to paint the login screen with
// or to avoid a flash of the wrong theme right after logging in. Seed from
// the last confirmed value instead so both render correctly immediately.
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

// Runs at module load - i.e. during main.tsx's import evaluation, before
// React's first render - so the cached theme is already applied by the time
// anything paints, not just after this module's first setThemePreference() call.
apply()

// Single owner of the system-preference listener, since App's initial load
// and SettingsPage's save both need to set this and the browser only has
// one "system theme changed" event to subscribe to.
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
