import { createTheme } from '@uiw/codemirror-themes'
import { tags as t } from '@lezer/highlight'

function syntaxStyles(dark: boolean) {
  return [
    { tag: t.propertyName, color: dark ? '#60a5fa' : '#2563eb' },
    { tag: [t.string, t.special(t.string)], color: dark ? '#4ade80' : '#16a34a' },
    { tag: [t.number, t.bool, t.atom, t.null], color: dark ? '#fb923c' : '#ea580c' },
    { tag: t.comment, color: '#a3a3a3', fontStyle: 'italic' },
    { tag: [t.punctuation, t.operator, t.meta], color: dark ? '#a3a3a3' : '#737373' },
    { tag: t.invalid, color: dark ? '#f87171' : '#dc2626' },
  ]
}

export const editorLightTheme = createTheme({
  theme: 'light',
  settings: {
    background: '#ffffff',
    foreground: '#404040',
    caret: '#171717',
    selection: '#e5e5e5',
    selectionMatch: '#e5e5e5',
    lineHighlight: '#fafafa',
    gutterBackground: '#ffffff',
    gutterForeground: '#a3a3a3',
    gutterBorder: 'transparent',
  },
  styles: syntaxStyles(false),
})

export const editorDarkTheme = createTheme({
  theme: 'dark',
  settings: {
    background: '#171717',
    foreground: '#d4d4d4',
    caret: '#f5f5f5',
    selection: '#404040',
    selectionMatch: '#404040',
    lineHighlight: '#262626',
    gutterBackground: '#171717',
    gutterForeground: '#737373',
    gutterBorder: 'transparent',
  },
  styles: syntaxStyles(true),
})
