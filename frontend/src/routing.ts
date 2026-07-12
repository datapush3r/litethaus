const STACK_PREFIX = '/stacks/'

export function parseSelected(pathname: string): string | null {
  if (!pathname.startsWith(STACK_PREFIX)) return null
  const name = decodeURIComponent(pathname.slice(STACK_PREFIX.length))
  return name || null
}

export function stackPath(name: string | null): string {
  return name ? `${STACK_PREFIX}${encodeURIComponent(name)}` : '/'
}
