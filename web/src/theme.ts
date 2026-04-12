export type ThemeMode = 'light' | 'dark'

const THEME_STORAGE_KEY = 'tsbot-theme-mode'

function readStoredTheme(): ThemeMode | null {
  try {
    const value = localStorage.getItem(THEME_STORAGE_KEY)
    if (value === 'light' || value === 'dark') return value
  } catch {
  }
  return null
}

function detectPreferredTheme(): ThemeMode {
  if (typeof window !== 'undefined' && window.matchMedia?.('(prefers-color-scheme: dark)').matches) {
    return 'dark'
  }
  return 'light'
}

export function getInitialTheme(): ThemeMode {
  return readStoredTheme() || detectPreferredTheme()
}

export function applyTheme(mode: ThemeMode): void {
  document.documentElement.classList.toggle('theme-dark', mode === 'dark')
  document.body.classList.toggle('theme-dark', mode === 'dark')
  document.documentElement.style.colorScheme = mode
  try {
    localStorage.setItem(THEME_STORAGE_KEY, mode)
  } catch {
  }
}

export function initializeTheme(): ThemeMode {
  const mode = getInitialTheme()
  applyTheme(mode)
  return mode
}
