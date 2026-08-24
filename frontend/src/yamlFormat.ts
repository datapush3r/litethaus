import { parseDocument } from 'yaml'

export function formatYaml(text: string): string | null {
  const doc = parseDocument(text)
  if (doc.errors.length > 0) return null
  return doc.toString({ indent: 2 })
}
