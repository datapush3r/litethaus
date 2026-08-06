import CodeMirror from '@uiw/react-codemirror'
import { json, jsonParseLinter } from '@codemirror/lang-json'
import { linter, lintGutter } from '@codemirror/lint'
import { EditorView } from '@codemirror/view'
import { useIsDarkMode } from '../useIsDarkMode'
import { editorDarkTheme, editorLightTheme } from '../editorTheme'

const jsonLinter = linter(jsonParseLinter())

interface JsonEditorProps {
  value: string
  onChange?: (value: string) => void
  readOnly?: boolean
  maxHeight?: string
  minHeight?: string
  className?: string
}

// Syntax-highlighted JSON, editable or read-only. Read-only mode (no
// onChange) drops the lint gutter - nothing to fix if you can't type.
export function JsonEditor({ value, onChange, readOnly, maxHeight = '24rem', minHeight, className }: JsonEditorProps) {
  const isDark = useIsDarkMode()
  const editable = !readOnly && onChange !== undefined

  return (
    <CodeMirror
      value={value}
      onChange={onChange}
      editable={editable}
      theme={isDark ? editorDarkTheme : editorLightTheme}
      extensions={editable ? [json(), lintGutter(), jsonLinter] : [json(), EditorView.editable.of(false)]}
      height="auto"
      minHeight={minHeight}
      maxHeight={maxHeight}
      className={className}
    />
  )
}
