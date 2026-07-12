import { linter, type Diagnostic } from '@codemirror/lint'
import { isMap, isPair, isScalar, parseDocument, type Pair, type YAMLMap } from 'yaml'

function toDiagnostic(err: { pos: [number, number]; message: string }, severity: Diagnostic['severity']): Diagnostic {
  const [from, to] = err.pos
  return { from, to: Math.max(to, from + 1), severity, message: err.message }
}

function findPair(map: YAMLMap, key: string): Pair | undefined {
  return map.items.find((p) => isPair(p) && isScalar(p.key) && p.key.value === key)
}

function pairRange(pair: Pair, part: 'key' | 'value'): [number, number] | null {
  const node = part === 'key' ? pair.key : pair.value
  if (!isScalar(node) || !node.range) return null
  return [node.range[0], node.range[1]]
}

// Beyond generic YAML syntax, catch the litethaus-specific footguns that
// CaddyService.build_config() otherwise silently no-ops on (see backend
// caddy_service.py): a stack with only one of domain/port set just never
// gets proxied, with nothing in the UI to explain why.
function checkLitehausSchema(text: string): Diagnostic[] {
  const diagnostics: Diagnostic[] = []
  const doc = parseDocument(text)
  if (!isMap(doc.contents)) return diagnostics

  const xlh = findPair(doc.contents, 'x-litethaus')
  if (!xlh || !isMap(xlh.value)) return diagnostics
  const meta = xlh.value

  const domainPair = findPair(meta, 'domain')
  const portPair = findPair(meta, 'port')
  const servicePair = findPair(meta, 'service')

  if (domainPair && !portPair) {
    const range = pairRange(domainPair, 'key')
    if (range) {
      diagnostics.push({
        from: range[0],
        to: range[1],
        severity: 'warning',
        message: 'x-litethaus.domain is set but port is missing - this stack will not be proxied until both are set',
      })
    }
  }
  if (portPair && !domainPair) {
    const range = pairRange(portPair, 'key')
    if (range) {
      diagnostics.push({
        from: range[0],
        to: range[1],
        severity: 'warning',
        message: 'x-litethaus.port is set but domain is missing - this stack will not be proxied until both are set',
      })
    }
  }
  if (portPair && isScalar(portPair.value) && typeof portPair.value.value !== 'number') {
    const range = pairRange(portPair, 'value')
    if (range) {
      diagnostics.push({ from: range[0], to: range[1], severity: 'warning', message: 'x-litethaus.port should be a number' })
    }
  }

  if (servicePair && isScalar(servicePair.value)) {
    const serviceName = servicePair.value.value
    const services = doc.get('services')
    const knownServices = isMap(services) ? services.items.filter(isPair).map((p) => (isScalar(p.key) ? p.key.value : null)) : []
    if (typeof serviceName === 'string' && !knownServices.includes(serviceName)) {
      const range = pairRange(servicePair, 'value')
      if (range) {
        diagnostics.push({
          from: range[0],
          to: range[1],
          severity: 'warning',
          message: `x-litethaus.service "${serviceName}" does not match any service defined below`,
        })
      }
    }
  }

  return diagnostics
}

export const yamlLinter = linter((view) => {
  const text = view.state.doc.toString()
  const doc = parseDocument(text)
  return [
    ...doc.errors.map((e) => toDiagnostic(e, 'error')),
    ...doc.warnings.map((w) => toDiagnostic(w, 'warning')),
    ...(doc.errors.length === 0 ? checkLitehausSchema(text) : []),
  ]
})
