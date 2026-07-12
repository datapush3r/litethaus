import { parseDocument } from 'yaml'

// Returns null (rather than throwing or emitting garbage) when the input
// doesn't parse cleanly, so callers can leave the editor content untouched
// and surface an error instead.
export function formatYaml(text: string): string | null {
  const doc = parseDocument(text)
  if (doc.errors.length > 0) return null
  return doc.toString({ indent: 2 })
}
