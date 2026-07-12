import CodeMirror from '@uiw/react-codemirror'
import { yaml } from '@codemirror/lang-yaml'
import { indentUnit } from '@codemirror/language'
import { lintGutter } from '@codemirror/lint'
import { useIsDarkMode } from '../useIsDarkMode'
import { yamlLinter } from '../yamlLint'
import { yamlDarkTheme, yamlLightTheme } from '../yamlTheme'

interface YamlEditorProps {
  value: string
  onChange: (value: string) => void
  className?: string
}

export function YamlEditor({ value, onChange, className }: YamlEditorProps) {
  const isDark = useIsDarkMode()

  return (
    <CodeMirror
      value={value}
      onChange={onChange}
      theme={isDark ? yamlDarkTheme : yamlLightTheme}
      extensions={[yaml(), indentUnit.of('  '), lintGutter(), yamlLinter]}
      height="100%"
      className={className}
    />
  )
}
