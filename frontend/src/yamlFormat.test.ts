import { describe, expect, it } from 'vitest'
import { formatYaml } from './yamlFormat'

describe('formatYaml', () => {
  it('returns null for invalid YAML', () => {
    expect(formatYaml('services: [this is not: valid: yaml')).toBeNull()
  })

  it('normalizes indentation to 2 spaces', () => {
    const input = 'services:\n    web:\n        image: nginx'
    expect(formatYaml(input)).toBe('services:\n  web:\n    image: nginx\n')
  })

  it('returns null for empty document edge case of unparseable content', () => {
    expect(formatYaml('a: b: c')).toBeNull()
  })
})
