import { describe, expect, it } from 'vitest'
import { sortStacksByStatus, type Stack, type StackState } from './api'

const stack = (name: string): Stack => ({
  name,
  path: `/config/stacks/${name}`,
  x_litethaus: {},
  services: [],
  error: null,
  compose_files: ['compose.yaml'],
  override_file: null,
})

describe('sortStacksByStatus', () => {
  it('orders running before partial before stopped', () => {
    const stacks = [stack('zeta'), stack('alpha'), stack('mid')]
    const statuses: Record<string, StackState> = { zeta: 'stopped', alpha: 'running', mid: 'partial' }
    expect(sortStacksByStatus(stacks, statuses).map((s) => s.name)).toEqual(['alpha', 'mid', 'zeta'])
  })

  it('breaks ties alphabetically and treats missing status as stopped', () => {
    const stacks = [stack('b'), stack('a'), stack('c')]
    expect(sortStacksByStatus(stacks, {}).map((s) => s.name)).toEqual(['a', 'b', 'c'])
  })

  it('does not mutate the input array', () => {
    const stacks = [stack('z'), stack('a')]
    const copy = [...stacks]
    sortStacksByStatus(stacks, {})
    expect(stacks).toEqual(copy)
  })
})
