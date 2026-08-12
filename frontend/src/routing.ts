export type Route =
  | { view: 'home' }
  | { view: 'stacks' }
  | { view: 'stack'; name: string }
  | { view: 'settings' }
  | { view: 'caddy' }
  | { view: 'new' }

const STACK_PREFIX = '/stacks/'

export function parseRoute(pathname: string): Route {
  if (pathname === '/stacks') return { view: 'stacks' }
  if (pathname === '/settings') return { view: 'settings' }
  if (pathname === '/caddy') return { view: 'caddy' }
  if (pathname === '/new') return { view: 'new' }
  if (pathname.startsWith(STACK_PREFIX)) {
    const name = decodeURIComponent(pathname.slice(STACK_PREFIX.length))
    if (name) return { view: 'stack', name }
  }
  return { view: 'home' }
}

export function routePath(route: Route): string {
  if (route.view === 'home') return '/'
  if (route.view === 'stacks') return '/stacks'
  if (route.view === 'settings') return '/settings'
  if (route.view === 'caddy') return '/caddy'
  if (route.view === 'new') return '/new'
  return `${STACK_PREFIX}${encodeURIComponent(route.name)}`
}
