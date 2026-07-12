import CodeMirror from '@uiw/react-codemirror'
import { yaml } from '@codemirror/lang-yaml'
import { unifiedMergeView } from '@codemirror/merge'
import { EditorView } from '@codemirror/view'
import { useIsDarkMode } from '../useIsDarkMode'
import { yamlDarkTheme, yamlLightTheme } from '../yamlTheme'

interface YamlDiffViewProps {
  original: string
  modified: string
  className?: string
}

export function YamlDiffView({ original, modified, className }: YamlDiffViewProps) {
  const isDark = useIsDarkMode()

  return (
    <CodeMirror
      value={modified}
      editable={false}
      theme={isDark ? yamlDarkTheme : yamlLightTheme}
      extensions={[yaml(), unifiedMergeView({ original, mergeControls: false }), EditorView.editable.of(false)]}
      height="100%"
      className={className}
    />
  )
}
