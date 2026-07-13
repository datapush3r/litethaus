import { linter, type Diagnostic } from '@codemirror/lint'
import { parseDocument } from 'yaml'

function toDiagnostic(err: { pos: [number, number]; message: string }, severity: Diagnostic['severity']): Diagnostic {
  const [from, to] = err.pos
  return { from, to: Math.max(to, from + 1), severity, message: err.message }
}

export const yamlLinter = linter((view) => {
  const text = view.state.doc.toString()
  const doc = parseDocument(text)
  return [...doc.errors.map((e) => toDiagnostic(e, 'error')), ...doc.warnings.map((w) => toDiagnostic(w, 'warning'))]
})
