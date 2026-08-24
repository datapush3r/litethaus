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
