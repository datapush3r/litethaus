# Cloudflare DDNS — design

## Problem

The prod environment runs a separate always-on container (`favonia/cloudflare-ddns`) just to keep one Cloudflare A record (`crystalmaze.net`) pointed at the host's current public IP, with its own copy of the Cloudflare API token and its own external dead-man's-switch (healthchecks.io ping). litehaus already holds a Cloudflare API token (`cloudflare_api_token` in `config.yaml`, currently used only for Caddy's DNS-01 ACME challenges) and already has an alerting path (`webhook_url`). DDNS is small enough, and close enough to infra litehaus already owns, to fold in directly and retire the standalone container.

This is the first of two features surfaced by surveying the prod `/docker` environment for what's "easily incorporated into litehaus." The second — replacing `watchtower`'s blanket auto-updater with per-stack "update available" visibility, extending the existing manual Update button — is a separate follow-up brainstorming session, not part of this spec.

## Non-goals

- Not building a general DNS record manager. Litehaus's DDNS only ever updates the `content` (IP) of a pre-existing A record it's told about — no create, no delete, no touching `proxied`/TTL/other fields.
- Not adding IPv6/AAAA support (current prod setup is IPv4-only; matches `IP6_PROVIDER=none`).
- Not building a DDNS status panel in the UI. Notifications go through the existing `webhook_url`; logs cover the rest, same as the existing cert-expiry check has no dedicated panel.
- Not reusing `caddy-dns/cloudflare` (the xcaddy plugin in `caddy/Dockerfile`) — confirmed it's DNS-01 ACME-challenge-only (ephemeral TXT records), no A-record capability. DDNS makes the litehaus backend a direct Cloudflare API client for the first time.

## Architecture

### `backend/ddns_service.py` (new)

Pure logic module, no threading — same shape as `cert_service.py`.

- `get_public_ip() -> str | None` — GET `https://www.cloudflare.com/cdn-cgi/trace`, parse the `ip=` line. Chosen over a third-party IP-echo service (ipify, icanhazip, etc.) because it's the same vendor already trusted for DNS — no new external dependency introduced.
- `find_zone_id(token, domain) -> str | None` — GET `/zones` (Cloudflare API), longest-suffix match of `domain` against the returned zone names.
- `find_record(token, zone_id, domain) -> dict | None` — GET `/zones/{zone_id}/dns_records?type=A&name={domain}`.
- `update_record(token, zone_id, record_id, ip) -> None` — PATCH `content` only.
- `class DdnsService: sync(token, domains: list[str]) -> list[dict]` — orchestrates the above per domain. Each result: `{"domain": str, "status": "unchanged" | "updated" | "error", "old_ip": str | None, "new_ip": str | None, "detail": str | None}`.

All HTTP calls via `urllib.request`, matching the rest of the codebase (`caddy_service.py`, `health_service.py`) — no new dependency (no `requests`).

Record must already exist — if `find_record` returns `None`, that's an `error` result ("no A record found for `<domain>`"), never auto-created. Matches the "never touch what I didn't explicitly configure" posture already established for `proxied`.

### `health_service.py` (extended)

A third gated check inside the existing `watch_forever()` loop, same shape as `_check_certs_once`:

```python
DDNS_CHECK_INTERVAL_SECONDS = 300  # 5 min - hardcoded, like CERT_CHECK_INTERVAL_SECONDS
```

`_check_ddns_once(webhook_url)`:
- No-ops if `ddns_domains` is empty or `cloudflare_api_token` is blank (same early-return pattern as `if not webhook_url: return` in `_check_certs_once`).
- Calls `ddns_service.sync(token, domains)`.
- For each result:
  - `status == "updated"` → always notify (webhook payload below).
  - `status == "error"` → notify only on the success→failure transition, tracked via a new `self._ddns_failing: set[str]` (domain names currently failing), same idea as `_alerted_certs`. Recovery (failure→success) is silent, matching how health-check recovery is already silent.
  - `status == "unchanged"` → no notification, clears the domain from `_ddns_failing` if present.

No new thread. Runs on the same poll cadence as the existing loop, just gated to fire every 5 minutes instead of every 15 seconds.

### Config (`config.yaml`)

One new field:

```yaml
# Domains to keep pointed at this host's current public IP via Cloudflare's
# API. Requires cloudflare_api_token above. Each domain must already have an
# A record in Cloudflare - litethaus updates the IP, never creates records or
# touches proxied/TTL. Leave empty to disable.
ddns_domains: []
```

Reuses `cloudflare_api_token` and `webhook_url` — no new secrets.

### Notifications (webhook payloads)

Same style as existing `stack`/`health` and `cert_domain`/`days_until_expiry` payloads:

- IP change: `{"ddns_domain": "crystalmaze.net", "old_ip": "1.2.3.4", "new_ip": "5.6.7.8"}`
- Failure (first occurrence only): `{"ddns_error": "crystalmaze.net", "detail": "<error string>"}`

### Settings UI (`SettingsPage.tsx`)

Currently `cloudflare_api_token` and `wildcard_domain` only render inside `{form.https_mode === 'acme' && ...}` — because today Cloudflare is exclusively an ACME concern. DDNS breaks that assumption: it needs the token independent of HTTPS mode. Fix as part of this change, not deferred:

- Pull `cloudflare_api_token`, `wildcard_domain`, and the new `ddns_domains` field out of the ACME-only conditional into their own section, gated only on `caddy_enabled` (matches existing scoping for Cloudflare's role in Caddy's cert/DNS story generally).
- Label it `<h2>Cloudflare</h2>` + `border-t`, matching the one existing sectioning precedent in this file (the "Change password" section) — the file has no other section headers today, so this introduces the pattern rather than fighting an existing one.
- `wildcard_domain`'s existing helper text ("requires a Cloudflare API token above") stays accurate since it's still adjacent to the token field, just now outside the ACME conditional too.
- `ddns_domains` renders as a single comma-separated text input (same ergonomic as `extra_routes_json`'s raw-text approach elsewhere in the app) — split into a list client-side/server-side on save. No dynamic add/remove list widget; not warranted for a rarely-edited field.
- No separate top-level page/nav entry (see Non-goals) — Cloudflare has no live operational data to justify Caddy's tabbed-page treatment.

### Testing

- `backend/test_ddns_service.py` — plain-assert style matching `test_cert_service.py`: mock `urllib.request.urlopen` for the trace endpoint and Cloudflare API calls.
  - IP unchanged → no PATCH call, `status: "unchanged"`.
  - IP changed → PATCH called with new IP only (assert no other fields in the PATCH body), `status: "updated"`.
  - Zone not found → `status: "error"`, no crash.
  - Record not found → `status: "error"`, no crash, no create attempted.
- `backend/test_health_service.py` — extend with the transition-only notify behavior: IP change → webhook called; first failure → webhook called; repeated failure → webhook not called again; recovery → silent, `_ddns_failing` cleared.

### Follow-up (not this change)

Once this ships and is confirmed working, decommission the `cloudflare-ddns` stack in `/docker` (and its plaintext-token compose file) as a separate manual step — not automated by this change.
