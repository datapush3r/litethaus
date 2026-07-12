export interface Stack {
  name: string
  path: string
  x_litethaus: Record<string, unknown>
  services: string[]
  error: string | null
}

export type StackState = 'running' | 'partial' | 'stopped'

export async function fetchStacks(): Promise<Stack[]> {
  const res = await fetch('/api/stacks')
  return res.json()
}

export async function fetchStatus(name: string): Promise<StackState> {
  const res = await fetch(`/api/stacks/${name}/status`)
  const data = await res.json()
  return data.status
}

export async function stackUp(name: string): Promise<{ ok: boolean; output: string }> {
  const res = await fetch(`/api/stacks/${name}/up`, { method: 'POST' })
  return res.json()
}

export async function stackDown(name: string): Promise<{ ok: boolean; output: string }> {
  const res = await fetch(`/api/stacks/${name}/down`, { method: 'POST' })
  return res.json()
}

export function logsSocketUrl(name: string): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/api/stacks/${name}/logs`
}

export interface Config {
  stacks_dir: string
  caddy_admin_url: string
  theme: string
  [key: string]: unknown
}

export async function fetchConfig(): Promise<Config> {
  const res = await fetch('/api/config')
  return res.json()
}

export async function updateConfig(patch: Record<string, unknown>): Promise<Config> {
  const res = await fetch('/api/config', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  })
  return res.json()
}
