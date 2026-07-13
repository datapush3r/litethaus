export interface Stack {
  name: string
  path: string
  x_litethaus: Record<string, unknown>
  services: string[]
  error: string | null
  compose_files: string[]
  override_file: string | null
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

export async function stackRestart(name: string): Promise<{ ok: boolean; output: string }> {
  const res = await fetch(`/api/stacks/${name}/restart`, { method: 'POST' })
  return res.json()
}

export async function stackUpdate(name: string): Promise<{ ok: boolean; output: string }> {
  const res = await fetch(`/api/stacks/${name}/update`, { method: 'POST' })
  return res.json()
}

async function unwrap<T>(res: Response, fallback: string): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new Error(body?.detail ?? fallback)
  }
  return res.json()
}

export async function fetchStackRaw(name: string, file?: string): Promise<string> {
  const qs = file ? `?file=${encodeURIComponent(file)}` : ''
  const res = await fetch(`/api/stacks/${name}/raw${qs}`)
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

export async function updateStackRaw(name: string, content: string, file?: string): Promise<Stack> {
  const res = await fetch(`/api/stacks/${name}/raw`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content, file }),
  })
  return unwrap<Stack>(res, 'failed to save stack')
}

export async function updateStackMetadata(
  name: string,
  patch: { icon?: string | null; port?: number | null; domain?: string | null; service?: string | null }
): Promise<Stack> {
  const res = await fetch(`/api/stacks/${name}/metadata`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(patch),
  })
  return unwrap<Stack>(res, 'failed to save stack metadata')
}

export async function deleteStack(name: string): Promise<void> {
  const res = await fetch(`/api/stacks/${name}`, { method: 'DELETE' })
  await unwrap(res, 'failed to delete stack')
}

export function logsSocketUrl(name: string, container?: string | null): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const qs = container ? `?container=${encodeURIComponent(container)}` : ''
  return `${protocol}//${window.location.host}/api/stacks/${name}/logs${qs}`
}

export function terminalSocketUrl(name: string, container: string): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/api/stacks/${name}/terminal?container=${encodeURIComponent(container)}`
}

export interface Config {
  stacks_dir: string
  caddy_enabled: boolean
  auto_icon_enabled: boolean
  caddy_admin_url: string
  https_port: number
  https_mode: string
  acme_email: string
  cloudflare_api_token: string
  wildcard_domain: string
  theme: string
  webhook_url: string
  [key: string]: unknown
}

export function stackUrl(domain: string, httpsPort: number): string {
  return httpsPort === 443 ? `https://${domain}` : `https://${domain}:${httpsPort}`
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
