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
  className?: string
}

// Syntax-highlighted JSON, editable or read-only. Read-only mode (no
// onChange) drops the lint gutter - nothing to fix if you can't type.
// Fills its parent (height 100%, like YamlEditor) - wrap it in a sized
// flex box (e.g. `flex-1 min-h-0`) rather than passing a height here.
export function JsonEditor({ value, onChange, readOnly, className }: JsonEditorProps) {
  const isDark = useIsDarkMode()
  const editable = !readOnly && onChange !== undefined

  return (
    <CodeMirror
      value={value}
      onChange={onChange}
      editable={editable}
      theme={isDark ? editorDarkTheme : editorLightTheme}
      extensions={editable ? [json(), lintGutter(), jsonLinter] : [json(), EditorView.editable.of(false)]}
      height="100%"
      className={className}
    />
  )
}
