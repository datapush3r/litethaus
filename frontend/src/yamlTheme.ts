import { createTheme } from '@uiw/codemirror-themes'
import { tags as t } from '@lezer/highlight'

// Mirrors the app's own Tailwind neutral palette (see LogPanel/StackDetail
// panel styling) instead of CodeMirror's stock light/dark look, so the
// editor reads as part of the UI rather than an embedded third-party widget.
function syntaxStyles(dark: boolean) {
  return [
    { tag: t.propertyName, color: dark ? '#60a5fa' : '#2563eb' }, // blue-400 / blue-600 - mapping keys
    { tag: [t.string, t.special(t.string)], color: dark ? '#4ade80' : '#16a34a' }, // green-400 / green-600
    { tag: [t.number, t.bool, t.atom, t.null], color: dark ? '#fb923c' : '#ea580c' }, // orange-400 / orange-600
    { tag: t.comment, color: '#a3a3a3', fontStyle: 'italic' }, // neutral-400
    { tag: [t.punctuation, t.operator, t.meta], color: dark ? '#a3a3a3' : '#737373' }, // neutral-400 / neutral-500
    { tag: t.invalid, color: dark ? '#f87171' : '#dc2626' }, // red-400 / red-600
  ]
}

export const yamlLightTheme = createTheme({
  theme: 'light',
  settings: {
    background: '#ffffff',
    foreground: '#404040', // neutral-700
    caret: '#171717', // neutral-900
    selection: '#e5e5e5', // neutral-200
    selectionMatch: '#e5e5e5',
    lineHighlight: '#fafafa', // neutral-50
    gutterBackground: '#ffffff',
    gutterForeground: '#a3a3a3', // neutral-400
    gutterBorder: 'transparent',
  },
  styles: syntaxStyles(false),
})

export const yamlDarkTheme = createTheme({
  theme: 'dark',
  settings: {
    background: '#171717', // neutral-900
    foreground: '#d4d4d4', // neutral-300
    caret: '#f5f5f5', // neutral-100
    selection: '#404040', // neutral-700
    selectionMatch: '#404040',
    lineHighlight: '#262626', // neutral-800
    gutterBackground: '#171717',
    gutterForeground: '#737373', // neutral-500
    gutterBorder: 'transparent',
  },
  styles: syntaxStyles(true),
})
