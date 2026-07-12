export type Route = { view: 'stacks' } | { view: 'stack'; name: string } | { view: 'settings' } | { view: 'new' }

const STACK_PREFIX = '/stacks/'

export function parseRoute(pathname: string): Route {
  if (pathname === '/settings') return { view: 'settings' }
  if (pathname === '/new') return { view: 'new' }
  if (pathname.startsWith(STACK_PREFIX)) {
    const name = decodeURIComponent(pathname.slice(STACK_PREFIX.length))
    if (name) return { view: 'stack', name }
  }
  return { view: 'stacks' }
}

export function routePath(route: Route): string {
  if (route.view === 'settings') return '/settings'
  if (route.view === 'new') return '/new'
  if (route.view === 'stack') return `${STACK_PREFIX}${encodeURIComponent(route.name)}`
  return '/'
}
