/// <reference types="node" />
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { contrast } from './contrast'

const css = readFileSync('src/styles/tokens.css', 'utf8') // vitest runs from frontend/

function tokens(block: RegExp): Record<string, string> {
  const m = css.match(block)
  if (!m) throw new Error('token block not found')
  return Object.fromEntries([...m[1].matchAll(/--([\w-]+):\s*(#[0-9a-f]{6})/gi)].map((x) => [x[1], x[2]]))
}

const themes = {
  light: tokens(/:root\s*\{([^}]*)\}/),
  dark: tokens(/:root\[data-theme=['"]?dark['"]?\]\s*\{([^}]*)\}/),
}

// Text tokens must reach AA (4.5:1) on the surface; accent is only ever a fill.
describe.each(Object.entries(themes))('%s theme contrast (WCAG AA)', (_name, t) => {
  it.each(['text-primary', 'text-secondary', 'up', 'down'])('%s on surface >= 4.5', (k) => {
    expect(contrast(t[k], t.surface)).toBeGreaterThanOrEqual(4.5)
  })
  it('on-accent text on the accent fill >= 4.5', () => {
    expect(contrast(t['on-accent'], t.accent)).toBeGreaterThanOrEqual(4.5)
  })
  it('focus ring is distinguishable from the surface (>= 3)', () => {
    expect(contrast(t.focus, t.surface)).toBeGreaterThanOrEqual(3)
  })
})
