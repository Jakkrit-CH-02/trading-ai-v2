import { create } from 'zustand'

export type Theme = 'light' | 'dark'

function initial(): Theme {
  try {
    const saved = localStorage.getItem('theme')
    if (saved === 'light' || saved === 'dark') return saved
  } catch {
    /* storage unavailable */
  }
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function apply(t: Theme) {
  document.documentElement.dataset.theme = t
  try {
    localStorage.setItem('theme', t)
  } catch {
    /* ignore */
  }
}

export const useTheme = create<{ theme: Theme; toggle: () => void }>((set, get) => {
  const t = initial()
  apply(t)
  return {
    theme: t,
    toggle: () => {
      const next = get().theme === 'light' ? 'dark' : 'light'
      apply(next)
      set({ theme: next })
    },
  }
})
