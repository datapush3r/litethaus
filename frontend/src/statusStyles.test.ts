import { describe, expect, it } from 'vitest'
import { BAD_HEALTH, HEALTH_BADGE, STATUS_DOT } from './statusStyles'

describe('status styles', () => {
  it('flags only unhealthy and restarting as bad health', () => {
    expect(BAD_HEALTH.has('unhealthy')).toBe(true)
    expect(BAD_HEALTH.has('restarting')).toBe(true)
    expect(BAD_HEALTH.has('healthy')).toBe(false)
    expect(BAD_HEALTH.has('starting')).toBe(false)
  })

  it('covers every stack state with a dot color', () => {
    expect(Object.keys(STATUS_DOT).sort()).toEqual(['partial', 'running', 'stopped'])
  })

  it('covers every health state with a badge', () => {
    for (const h of ['healthy', 'unhealthy', 'restarting', 'starting', 'unknown'] as const) {
      expect(HEALTH_BADGE[h]).toBeTruthy()
    }
  })
})
