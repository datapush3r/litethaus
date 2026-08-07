# Settings page tabs — design

## Problem

`SettingsPage.tsx` is one long flat form. It grew a second Cloudflare-adjacent section (DDNS domains) during the Cloudflare DDNS feature, deliberately left ungated on `caddy_enabled` while the original Cloudflare section (token, wildcard domain) stayed gated — leaving two visually-adjacent `border-t` sections both titled "Cloudflare*" back to back, a cosmetic nit parked (not fixed) by that feature's final review. Splitting into tabs fixes this as a side effect while also giving the page room to grow.

## Non-goals

- No new save semantics — one `form` object, one `handleSave()`, one PATCH, unchanged. Tabs only control which fields are visible, not how they're saved.
- No fourth "Password" tab — change-password stays where it is today, folded into General.
- No new shared component — reuses `TabBar` (`frontend/src/components/TabBar.tsx`), the same component `CaddyPage.tsx` already uses for its own tabs.

## Design

### Tab boundaries

**General** (default tab): `stacks_dir`, `project_prefix`, `auto_icon_enabled`, `webhook_url`, `theme`, change-password section, Save button + Saved/error indicators. Unchanged from today's fields and layout, minus what moves to the other two tabs.

**Caddy**: the `caddy_enabled` checkbox moves here from its current position among the top-level fields (it's a Caddy setting, not a general one) + `caddy_admin_url`/`https_port`/`https_mode` (rendered when `caddy_enabled`, same as today) + `acme_email` (rendered when `https_mode === 'acme'`, same as today).

**Cloudflare**: `cloudflare_api_token`, `wildcard_domain`, `ddnsDomains` — merged into **one** section (today they're two adjacent `border-t` blocks: "Cloudflare" gated on `caddy_enabled`, "Cloudflare DDNS" always visible). This tab is **always visible, never gated on `caddy_enabled`** — removing the asymmetric wrapper entirely rather than carrying it into the tab. Each field's existing helper text already states its own prerequisite (wildcard domain: "requires https_mode acme above"; token: "enables DNS-01 + wildcard certs, and DDNS below").

### Shared state, no per-tab save

All three tabs render from the same `form: FormState` object in the one `SettingsPage` component. `TABS = ['General', 'Caddy', 'Cloudflare']`, `const [tab, setTab] = useState(TABS[0])`, `<TabBar items={TABS} active={tab} onSelect={setTab} />` — identical wiring to `CaddyPage.tsx:54-55`. Switching tabs only changes which JSX subtree is rendered; unsaved edits on a hidden tab are preserved since they live in the shared `form` state, not per-tab local state.

The Save button, `saved`/`saveError` indicators render **outside** the tab-switched region — visible on every tab, since all three tabs edit the same form and save together.

### Testing

No backend change — this is a pure frontend reorganization of existing fields, no new fields, no new API surface. Verification is `tsc --noEmit` (type safety) plus a manual click-through confirming: each field appears on exactly one tab, `caddy_enabled`'s relocation doesn't break its conditional (Caddy tab's own admin-URL/port/mode fields still hide when it's off), Cloudflare tab fields are reachable regardless of `caddy_enabled`, and Save persists edits made on any tab regardless of which tab is active when Save is clicked.
