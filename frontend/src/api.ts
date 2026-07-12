export interface Stack {
  name: string
  path: string
  x_litethaus: Record<string, unknown>
  services: string[]
  error: string | null
}

export type StackState = 'running' | 'partial' | 'stopped'
export type HealthState = 'healthy' | 'unhealthy' | 'restarting' | 'starting' | 'unknown'

export interface ContainerInfo {
  name: string
  state: string
  health: string | null
  restart_count: number
}

export interface StackStatus {
  status: StackState
  health: HealthState
  containers: ContainerInfo[]
}

export async function fetchStacks(): Promise<Stack[]> {
  const res = await fetch('/api/stacks')
  return res.json()
}

export async function fetchStatus(name: string): Promise<StackStatus> {
  const res = await fetch(`/api/stacks/${name}/status`)
  return res.json()
}

export async function stackUp(name: string): Promise<{ ok: boolean; output: string }> {
  const res = await fetch(`/api/stacks/${name}/up`, { method: 'POST' })
  return res.json()
}

export async function stackDown(name: string): Promise<{ ok: boolean; output: string }> {
  const res = await fetch(`/api/stacks/${name}/down`, { method: 'POST' })
  return res.json()
}

async function unwrap<T>(res: Response, fallback: string): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new Error(body?.detail ?? fallback)
  }
  return res.json()
}

export async function fetchStackRaw(name: string): Promise<string> {
  const res = await fetch(`/api/stacks/${name}/raw`)
  const data = await unwrap<{ content: string }>(res, 'failed to load stack')
  return data.content
}

export async function createStack(name: string, content: string): Promise<Stack> {
  const res = await fetch('/api/stacks', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, content }),
  })
  return unwrap<Stack>(res, 'failed to create stack')
}

export async function updateStackRaw(name: string, content: string): Promise<Stack> {
  const res = await fetch(`/api/stacks/${name}/raw`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  })
  return unwrap<Stack>(res, 'failed to save stack')
}

export async function deleteStack(name: string): Promise<void> {
  const res = await fetch(`/api/stacks/${name}`, { method: 'DELETE' })
  await unwrap(res, 'failed to delete stack')
}

export function logsSocketUrl(name: string): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/api/stacks/${name}/logs`
}

export interface Config {
  stacks_dir: string
  caddy_admin_url: string
  https_mode: string
  acme_email: string
  theme: string
  webhook_url: string
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

export interface AuthStatus {
  configured: boolean
  authenticated: boolean
}

export async function fetchAuthStatus(): Promise<AuthStatus> {
  const res = await fetch('/api/auth/status')
  return res.json()
}

export async function authSetup(username: string, password: string): Promise<void> {
  const res = await fetch('/api/auth/setup', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  await unwrap(res, 'failed to set up login')
}

export async function authLogin(username: string, password: string): Promise<void> {
  const res = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  })
  await unwrap(res, 'invalid username or password')
}

export async function authLogout(): Promise<void> {
  await fetch('/api/auth/logout', { method: 'POST' })
}

export async function changePassword(currentPassword: string, newPassword: string): Promise<void> {
  const res = await fetch('/api/auth/change-password', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
  })
  await unwrap(res, 'failed to change password')
}
