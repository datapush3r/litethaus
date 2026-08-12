# Homepage (URL launcher) — design

## Problem

Stacks with a domain configured currently only show their URL buried inside the `/stacks` list (or one at a time on a stack's detail page). There's no single, at-a-glance page listing every reachable URL — including domains that route through Caddy's manually-configured "extra routes" JSON rather than through a stack at all. Users want a quick-launch homepage: click a name, get a new tab to that service's webui.

## Non-goals

- No new backend endpoint. Everything needed (`stacks`, per-stack `status`, `config.caddy_extra_routes_json`, `https_port`) is already fetched by `Dashboard` today.
- No favoriting/reordering/grouping on the homepage — flat alphabetical list only.
- No new metadata fields on stacks or on extra routes. Extra routes have no name/icon in the config today, so they're labeled by hostname only.
- Not editable from the homepage — it's a read-only launcher. Editing domains/routes stays on the stack detail page / Caddy page.

## Design

### Routing

`routing.ts`'s `Route` union gets a `{ view: 'home' }` member. `/` now parses to `home` (was `stacks`); the stacks list moves to an explicit `/stacks` path.

```
parseRoute('/')        -> { view: 'home' }
parseRoute('/stacks')  -> { view: 'stacks' }
parseRoute(unknown)    -> { view: 'home' }   // fallback also becomes home
routePath({view:'home'})   -> '/'
routePath({view:'stacks'}) -> '/stacks'
```

`App.tsx`'s stale-route-redirect effect (`stacks !== null && route.view === 'stack' && stack missing -> navigate stacks`) is unaffected — it only fires for `view === 'stack'`.

### Sidebar

New nav entry "Home" above "Stacks" (same style as the Settings/Caddy links at the bottom — icon + label, highlighted when `route.view === 'home'`). "Stacks" folder header button now navigates to `{ view: 'stacks' }` explicitly instead of implying it via `onSelectStack(null)` targeting `/`.

### Data assembly

Dashboard already calls `fetchConfig()` once on mount for `theme`/`https_port`; extend that same call site to also stash `caddy_extra_routes_json` in state (`extraRoutesJson: string`), passed down to `HomePage`.

New pure function `buildHomeEntries` (co-located in `HomePage.tsx`, no new file — it's one small helper, not a shared utility yet):

```ts
interface HomeEntry {
  key: string
  label: string
  icon: string | null   // stack icon, or null for custom routes
  url: string
}

function buildHomeEntries(
  stacks: Stack[],
  statuses: Record<string, StackState>,
  extraRoutesJson: string,
  httpsPort: number,
): HomeEntry[]
```

Two sources, merged and sorted by `label`:

1. **Stacks**: `stacks.filter(s => !s.error && statuses[s.name] !== 'stopped' && typeof s.x_litethaus.domain === 'string')`. Entry: `label = s.name`, `icon = s.x_litethaus.icon`, `url = stackUrl(domain, httpsPort)`. `!== 'stopped'` matches the existing "isUp" convention already used by `Dashboard.handleToggle` — `partial` counts as running.
2. **Custom Caddy routes**: `JSON.parse(extraRoutesJson)` (wrapped in try/catch — parse failure means "render nothing from this source," same silent-skip behavior as the backend's own `caddy_service.py` fallback, not a page-level error). For each array element, collect every string in `route.match?.[].host?.[]`, dedupe by hostname. Entry: `label = host`, `icon = null`, `url = stackUrl(host, httpsPort)`.

Dedup across both sources isn't needed: a domain that's both a stack's domain and listed in extra-routes JSON is a pre-existing user misconfiguration, not something this page needs to reconcile.

### Component

`HomePage.tsx`, props `{ stacks, statuses, extraRoutesJson, httpsPort }`. Renders `buildHomeEntries(...)` as a simple vertical list: icon (generic `Globe`/`Waypoints` lucide icon when `icon === null`) + `label` + domain link, one row each, `target="_blank" rel="noreferrer"`.

The domain-link anchor (icon + href + external-link glyph) currently lives inline in `StackCard.tsx`'s `domainLink`. Factor it into a small shared `DomainLink({ domain, httpsPort })` component (new tiny file or exported from `StackCard.tsx`) and use it from both `StackCard` and `HomePage` instead of duplicating the JSX.

Empty state (no entries at all): "No running stacks or custom routes with a domain configured yet."

### Testing

No backend change. `buildHomeEntries` is a pure function — worth one small `test_*`-style check per the repo's own bug-fix habits, but this repo's `frontend/` has no test runner set up (only `backend/test_*.py` convention exists, per CLAUDE.md). Given the logic is a filter + one JSON-parse + dedupe (no branching worth a regression net on its own), skip an automated test; verify with `tsc --noEmit` plus a manual check: a running stack with a domain shows up, a stopped one doesn't, a malformed `caddy_extra_routes_json` doesn't crash the page (renders whatever's parseable, or nothing), and each row opens the right URL in a new tab.
