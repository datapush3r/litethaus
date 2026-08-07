# Cloudflare DDNS Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fold Cloudflare DDNS (currently a standalone `favonia/cloudflare-ddns` container in prod) into litethaus, reusing the existing `cloudflare_api_token` and `webhook_url`, so the standalone container and its duplicate token can be retired.

**Architecture:** A new `backend/ddns_service.py` holds pure Cloudflare-API-client logic (public IP lookup via Cloudflare's own trace endpoint, zone/record lookup, IP-only record update). `health_service.py`'s existing background loop gets a third gated check (alongside container-health and cert-expiry) that calls it every 5 minutes and notifies via the existing webhook on IP changes and on failure transitions only. `SettingsPage.tsx` gets a new `ddns_domains` field, and its Cloudflare fields move out of the ACME-only conditional since DDNS needs the token independent of HTTPS mode.

**Tech Stack:** Python 3.11+ stdlib (`urllib.request`, `json`) — no new dependency. TypeScript/React on the frontend, existing `Config` PATCH round-trip.

## Global Constraints

- Update-only: never create a DNS record, never touch `proxied`/TTL/anything but `content`. Error out if no matching A record exists.
- IPv4 only — no AAAA/IPv6.
- No new external dependency for IP detection — use Cloudflare's own `https://www.cloudflare.com/cdn-cgi/trace`.
- No new Python package — `urllib.request`, matching every other HTTP call already in this codebase (`caddy_service.py`, `health_service.py`).
- Backend tests are plain-`assert` functions with an `if __name__ == "__main__":` block — no pytest, no fixtures. Run with `python3 test_x.py` (or, inside the venv set up during the earlier `caddy-review-followups` work, `LITETHAUS_CONFIG_PATH=/tmp/litehaus-cfg/config.yaml /tmp/litehaus-venv/bin/python test_x.py`).
- Notifications are transition-only: an IP change always notifies; a failure notifies once on success→failure, stays silent on repeat failures, and recovery (failure→success) is silent too — matching `_check_certs_once`'s `_alerted_certs` pattern.

---

### Task 1: `ddns_service.py` — Cloudflare API client + IP detection

**Files:**
- Create: `backend/ddns_service.py`
- Create: `backend/test_ddns_service.py`

**Interfaces:**
- Produces: `get_public_ip() -> str | None`; `find_zone_id(token: str, domain: str) -> str | None`; `find_record(token: str, zone_id: str, domain: str) -> dict[str, Any] | None`; `update_record(token: str, zone_id: str, record_id: str, ip: str) -> None`; `class DdnsService` with `sync(self, token: str, domains: list[str]) -> list[dict[str, Any]]`, each result dict shaped `{"domain": str, "status": "unchanged" | "updated" | "error", "old_ip": str | None, "new_ip": str | None, "detail": str | None}`; module-level singleton `ddns_service = DdnsService()`.

- [ ] **Step 1: Write the public-IP-detection tests**

Create `backend/test_ddns_service.py`:

```python
from unittest.mock import MagicMock, patch


def test_get_public_ip_parses_trace_response() -> None:
    from ddns_service import get_public_ip

    fake_resp = MagicMock()
    fake_resp.read.return_value = b"fl=1\nip=203.0.113.5\nts=123\n"
    fake_resp.__enter__.return_value = fake_resp
    with patch("ddns_service.urllib.request.urlopen", return_value=fake_resp):
        assert get_public_ip() == "203.0.113.5"


def test_get_public_ip_returns_none_on_failure() -> None:
    from ddns_service import get_public_ip

    with patch("ddns_service.urllib.request.urlopen", side_effect=OSError("boom")):
        assert get_public_ip() is None


if __name__ == "__main__":
    test_get_public_ip_parses_trace_response()
    test_get_public_ip_returns_none_on_failure()
    print("ok")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd backend && python3 test_ddns_service.py`
Expected: `ModuleNotFoundError: No module named 'ddns_service'`

- [ ] **Step 3: Write `get_public_ip`**

Create `backend/ddns_service.py`:

```python
import json
import logging
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

CF_API_BASE = "https://api.cloudflare.com/client/v4"
TRACE_URL = "https://www.cloudflare.com/cdn-cgi/trace"


def get_public_ip() -> str | None:
    # Cloudflare's own trace endpoint - same vendor already trusted for DNS,
    # no new third-party IP-echo service introduced.
    try:
        with urllib.request.urlopen(TRACE_URL, timeout=5) as resp:
            body = resp.read().decode()
    except Exception:
        logger.exception("Failed to fetch public IP from Cloudflare trace endpoint")
        return None
    for line in body.splitlines():
        if line.startswith("ip="):
            return line[len("ip=") :].strip()
    return None
```

- [ ] **Step 4: Run it to verify it passes**

Run: `cd backend && python3 test_ddns_service.py`
Expected: `ok`

- [ ] **Step 5: Write the Cloudflare API helper tests (zone lookup + record update)**

Append to `backend/test_ddns_service.py` (before the `if __name__` block):

```python
def test_find_zone_id_picks_longest_matching_suffix() -> None:
    from ddns_service import find_zone_id

    zones_response = {
        "result": [
            {"id": "z-outer", "name": "example.com"},
            {"id": "z-inner", "name": "sub.example.com"},
        ]
    }
    with patch("ddns_service._cf_request", return_value=zones_response):
        assert find_zone_id("tok", "app.sub.example.com") == "z-inner"


def test_find_zone_id_returns_none_when_no_zone_matches() -> None:
    from ddns_service import find_zone_id

    with patch("ddns_service._cf_request", return_value={"result": [{"id": "z1", "name": "other.com"}]}):
        assert find_zone_id("tok", "app.example.com") is None


def test_update_record_patches_only_content_field() -> None:
    from ddns_service import update_record

    with patch("ddns_service._cf_request") as cf_request:
        update_record("tok", "zone1", "rec1", "9.9.9.9")
        cf_request.assert_called_once_with(
            "tok", "/zones/zone1/dns_records/rec1", method="PATCH", body={"content": "9.9.9.9"}
        )
```

- [ ] **Step 6: Run it to verify it fails**

Run: `cd backend && python3 -c "from test_ddns_service import test_find_zone_id_picks_longest_matching_suffix as t; t()"`
Expected: `ImportError: cannot import name 'find_zone_id' from 'ddns_service'`

- [ ] **Step 7: Write `_cf_request`, `find_zone_id`, `find_record`, `update_record`**

Append to `backend/ddns_service.py`:

```python
def _cf_request(token: str, path: str, method: str = "GET", body: dict[str, Any] | None = None) -> dict[str, Any]:
    req = urllib.request.Request(
        f"{CF_API_BASE}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.load(resp)


def find_zone_id(token: str, domain: str) -> str | None:
    # ponytail: single page of zones (Cloudflare's default page size is 20) -
    # fine for a personal account with a handful of zones; add pagination if
    # you ever have more than that.
    data = _cf_request(token, "/zones")
    best: str | None = None
    best_len = -1
    for zone in data.get("result") or []:
        name = zone.get("name", "")
        if (domain == name or domain.endswith("." + name)) and len(name) > best_len:
            best = zone.get("id")
            best_len = len(name)
    return best


def find_record(token: str, zone_id: str, domain: str) -> dict[str, Any] | None:
    data = _cf_request(token, f"/zones/{zone_id}/dns_records?type=A&name={domain}")
    results = data.get("result") or []
    return results[0] if results else None


def update_record(token: str, zone_id: str, record_id: str, ip: str) -> None:
    _cf_request(token, f"/zones/{zone_id}/dns_records/{record_id}", method="PATCH", body={"content": ip})
```

- [ ] **Step 8: Run it to verify it passes**

Run: `cd backend && python3 -c "
from test_ddns_service import (
    test_find_zone_id_picks_longest_matching_suffix as t1,
    test_find_zone_id_returns_none_when_no_zone_matches as t2,
    test_update_record_patches_only_content_field as t3,
)
t1(); t2(); t3()
print('ok')
"`
Expected: `ok`

- [ ] **Step 9: Write the `DdnsService.sync` orchestration tests**

Append to `backend/test_ddns_service.py`:

```python
def test_sync_skips_update_when_ip_unchanged() -> None:
    from ddns_service import DdnsService

    svc = DdnsService()
    with patch("ddns_service.get_public_ip", return_value="1.2.3.4"), \
         patch("ddns_service.find_zone_id", return_value="zone1"), \
         patch("ddns_service.find_record", return_value={"id": "rec1", "content": "1.2.3.4"}), \
         patch("ddns_service.update_record") as update_record:
        results = svc.sync("tok", ["app.example.com"])
        update_record.assert_not_called()
        assert results == [
            {"domain": "app.example.com", "status": "unchanged", "old_ip": "1.2.3.4", "new_ip": "1.2.3.4", "detail": None}
        ]


def test_sync_updates_record_when_ip_changed() -> None:
    from ddns_service import DdnsService

    svc = DdnsService()
    with patch("ddns_service.get_public_ip", return_value="5.6.7.8"), \
         patch("ddns_service.find_zone_id", return_value="zone1"), \
         patch("ddns_service.find_record", return_value={"id": "rec1", "content": "1.2.3.4"}), \
         patch("ddns_service.update_record") as update_record:
        results = svc.sync("tok", ["app.example.com"])
        update_record.assert_called_once_with("tok", "zone1", "rec1", "5.6.7.8")
        assert results == [
            {"domain": "app.example.com", "status": "updated", "old_ip": "1.2.3.4", "new_ip": "5.6.7.8", "detail": None}
        ]


def test_sync_errors_when_public_ip_unavailable() -> None:
    from ddns_service import DdnsService

    svc = DdnsService()
    with patch("ddns_service.get_public_ip", return_value=None):
        results = svc.sync("tok", ["app.example.com"])
        assert results[0]["status"] == "error"
        assert results[0]["detail"] == "could not determine public IP"


def test_sync_errors_when_zone_not_found() -> None:
    from ddns_service import DdnsService

    svc = DdnsService()
    with patch("ddns_service.get_public_ip", return_value="5.6.7.8"), \
         patch("ddns_service.find_zone_id", return_value=None):
        results = svc.sync("tok", ["app.example.com"])
        assert results[0]["status"] == "error"
        assert "zone" in results[0]["detail"]


def test_sync_errors_when_record_not_found_and_does_not_create() -> None:
    from ddns_service import DdnsService

    svc = DdnsService()
    with patch("ddns_service.get_public_ip", return_value="5.6.7.8"), \
         patch("ddns_service.find_zone_id", return_value="zone1"), \
         patch("ddns_service.find_record", return_value=None), \
         patch("ddns_service.update_record") as update_record:
        results = svc.sync("tok", ["app.example.com"])
        update_record.assert_not_called()
        assert results[0]["status"] == "error"
        assert "record" in results[0]["detail"].lower()


def test_sync_continues_past_one_domains_error() -> None:
    from ddns_service import DdnsService

    svc = DdnsService()
    with patch("ddns_service.get_public_ip", return_value="5.6.7.8"), \
         patch("ddns_service.find_zone_id", side_effect=[None, "zone1"]), \
         patch("ddns_service.find_record", return_value={"id": "rec1", "content": "1.1.1.1"}), \
         patch("ddns_service.update_record") as update_record:
        results = svc.sync("tok", ["bad.example.com", "good.example.com"])
        assert results[0]["status"] == "error"
        assert results[1]["status"] == "updated"
        update_record.assert_called_once_with("tok", "zone1", "rec1", "5.6.7.8")
```

- [ ] **Step 10: Run it to verify it fails**

Run: `cd backend && python3 -c "from test_ddns_service import test_sync_skips_update_when_ip_unchanged as t; t()"`
Expected: `AttributeError: 'DdnsService' object has no attribute 'sync'` (or similar — `DdnsService` class doesn't exist yet)

- [ ] **Step 11: Write `DdnsService`**

Append to `backend/ddns_service.py`:

```python
class DdnsService:
    def sync(self, token: str, domains: list[str]) -> list[dict[str, Any]]:
        ip = get_public_ip()
        results: list[dict[str, Any]] = []
        for domain in domains:
            if ip is None:
                results.append(self._error(domain, "could not determine public IP"))
                continue
            try:
                results.append(self._sync_one(token, domain, ip))
            except Exception as exc:
                logger.exception("DDNS sync failed for %s", domain)
                results.append(self._error(domain, str(exc)))
        return results

    def _sync_one(self, token: str, domain: str, ip: str) -> dict[str, Any]:
        zone_id = find_zone_id(token, domain)
        if zone_id is None:
            return self._error(domain, f"no Cloudflare zone found for {domain}")
        record = find_record(token, zone_id, domain)
        if record is None:
            return self._error(domain, f"no A record found for {domain}")
        current_ip = record.get("content")
        if current_ip == ip:
            return {"domain": domain, "status": "unchanged", "old_ip": current_ip, "new_ip": ip, "detail": None}
        update_record(token, zone_id, record["id"], ip)
        return {"domain": domain, "status": "updated", "old_ip": current_ip, "new_ip": ip, "detail": None}

    @staticmethod
    def _error(domain: str, detail: str) -> dict[str, Any]:
        return {"domain": domain, "status": "error", "old_ip": None, "new_ip": None, "detail": detail}


ddns_service = DdnsService()
```

- [ ] **Step 12: Run it to verify it passes, then wire the full `__main__` block**

Replace the `if __name__ == "__main__":` block in `backend/test_ddns_service.py` with:

```python
if __name__ == "__main__":
    test_get_public_ip_parses_trace_response()
    test_get_public_ip_returns_none_on_failure()
    test_find_zone_id_picks_longest_matching_suffix()
    test_find_zone_id_returns_none_when_no_zone_matches()
    test_update_record_patches_only_content_field()
    test_sync_skips_update_when_ip_unchanged()
    test_sync_updates_record_when_ip_changed()
    test_sync_errors_when_public_ip_unavailable()
    test_sync_errors_when_zone_not_found()
    test_sync_errors_when_record_not_found_and_does_not_create()
    test_sync_continues_past_one_domains_error()
    print("ok")
```

Run: `cd backend && python3 test_ddns_service.py`
Expected: `ok`

- [ ] **Step 13: Commit**

```bash
git add backend/ddns_service.py backend/test_ddns_service.py
git commit -m "feat: add ddns_service — Cloudflare public-IP + A-record sync"
```

---

### Task 2: `health_service.py` integration + `config_service.py` default

**Files:**
- Modify: `backend/health_service.py`
- Modify: `backend/test_health_service.py`
- Modify: `backend/config_service.py:66-67`

**Interfaces:**
- Consumes: `ddns_service.sync(token: str, domains: list[str]) -> list[dict[str, Any]]` from Task 1 (each result: `{"domain", "status", "old_ip", "new_ip", "detail"}`)
- Produces: `HealthService._check_ddns_once(self, webhook_url: str) -> None`; new instance state `self._last_ddns_check: float`, `self._ddns_failing: set[str]`; config default `ddns_domains: []`

- [ ] **Step 1: Add the config default**

In `backend/config_service.py`, right after the `wildcard_domain` block (currently ending at line 67):

```python
# Wildcard domain for ACME certs, e.g. "example.com" issues one "*.example.com"
# cert covering every stack instead of a cert per stack domain. Requires
# cloudflare_api_token (DNS-01 is the only way to prove ownership of a
# wildcard). Leave blank to keep today's per-stack-domain certs.
wildcard_domain: ""

# Domains to keep pointed at this host's current public IP via Cloudflare's
# API. Requires cloudflare_api_token above. Each domain must already have an
# A record in Cloudflare - litethaus updates the IP, never creates records or
# touches proxied/TTL. Leave empty to disable.
ddns_domains: []
```

- [ ] **Step 2: Write the DDNS gate/notify tests**

In `backend/test_health_service.py`, update the `_svc()` helper and add tests. Replace:

```python
def _svc() -> HealthService:
    svc = HealthService()
    svc._last_cert_check = float("-inf")
    return svc
```

with:

```python
def _svc() -> HealthService:
    svc = HealthService()
    svc._last_cert_check = float("-inf")
    svc._last_ddns_check = float("-inf")
    return svc
```

Then append (before the `if __name__` block):

```python
def test_check_ddns_skips_when_no_token_or_domains() -> None:
    svc = _svc()
    with patch(
        "health_service.config_service.load",
        return_value={"cloudflare_api_token": "", "ddns_domains": ["a.com"]},
    ), patch("health_service.ddns_service.sync") as sync:
        svc._check_ddns_once("http://hook.example.com")
        sync.assert_not_called()

    svc2 = _svc()
    with patch(
        "health_service.config_service.load",
        return_value={"cloudflare_api_token": "tok", "ddns_domains": []},
    ), patch("health_service.ddns_service.sync") as sync:
        svc2._check_ddns_once("http://hook.example.com")
        sync.assert_not_called()


def test_check_ddns_respects_time_gate() -> None:
    svc = _svc()
    svc._last_ddns_check = time.monotonic()
    with patch("health_service.ddns_service.sync") as sync:
        svc._check_ddns_once("http://hook.example.com")
        sync.assert_not_called()


def test_check_ddns_notifies_on_ip_change() -> None:
    svc = _svc()
    result = [{"domain": "app.example.com", "status": "updated", "old_ip": "1.1.1.1", "new_ip": "2.2.2.2", "detail": None}]
    with patch(
        "health_service.config_service.load",
        return_value={"cloudflare_api_token": "tok", "ddns_domains": ["app.example.com"]},
    ), patch("health_service.ddns_service.sync", return_value=result), \
         patch("health_service.urllib.request.urlopen") as urlopen:
        svc._check_ddns_once("http://hook.example.com")
        assert urlopen.call_count == 1


def test_check_ddns_notifies_once_on_first_failure_then_stays_silent() -> None:
    svc = _svc()
    result = [{"domain": "app.example.com", "status": "error", "old_ip": None, "new_ip": None, "detail": "boom"}]
    with patch(
        "health_service.config_service.load",
        return_value={"cloudflare_api_token": "tok", "ddns_domains": ["app.example.com"]},
    ), patch("health_service.ddns_service.sync", return_value=result), \
         patch("health_service.urllib.request.urlopen") as urlopen:
        svc._check_ddns_once("http://hook.example.com")
        assert urlopen.call_count == 1

        svc._last_ddns_check = float("-inf")  # force past the time-gate again
        svc._check_ddns_once("http://hook.example.com")
        assert urlopen.call_count == 1  # same failure, no repeat alert


def test_check_ddns_recovery_is_silent_and_clears_failing_state() -> None:
    svc = _svc()
    failing = [{"domain": "app.example.com", "status": "error", "old_ip": None, "new_ip": None, "detail": "boom"}]
    ok = [{"domain": "app.example.com", "status": "unchanged", "old_ip": "1.2.3.4", "new_ip": "1.2.3.4", "detail": None}]
    cfg = {"cloudflare_api_token": "tok", "ddns_domains": ["app.example.com"]}
    with patch("health_service.config_service.load", return_value=cfg), \
         patch("health_service.urllib.request.urlopen") as urlopen:
        with patch("health_service.ddns_service.sync", return_value=failing):
            svc._check_ddns_once("http://hook.example.com")
        assert urlopen.call_count == 1
        assert "app.example.com" in svc._ddns_failing

        svc._last_ddns_check = float("-inf")
        with patch("health_service.ddns_service.sync", return_value=ok):
            svc._check_ddns_once("http://hook.example.com")
        assert urlopen.call_count == 1  # recovery is silent
        assert "app.example.com" not in svc._ddns_failing
```

- [ ] **Step 3: Run it to verify it fails**

Run: `cd backend && python3 -c "from test_health_service import test_check_ddns_skips_when_no_token_or_domains as t; t()"`
Expected: `AttributeError: 'HealthService' object has no attribute '_check_ddns_once'`

- [ ] **Step 4: Implement `_check_ddns_once` and wire it into `check_once`**

In `backend/health_service.py`, add the import and constant near the top:

```python
from ddns_service import ddns_service
```

```python
DDNS_CHECK_INTERVAL_SECONDS = 300
```

In `HealthService.__init__`, add the two new fields (after `self._alerted_certs: set[str] = set()`):

```python
        self._last_ddns_check: float = float("-inf")
        self._ddns_failing: set[str] = set()
```

In `check_once`, call the new method after `self._check_certs_once(webhook_url)`:

```python
        self._check_certs_once(webhook_url)
        self._check_ddns_once(webhook_url)
```

Add the new methods (after `_notify_cert_expiry`):

```python
    def _check_ddns_once(self, webhook_url: str) -> None:
        now = time.monotonic()
        if now - self._last_ddns_check < DDNS_CHECK_INTERVAL_SECONDS:
            return
        self._last_ddns_check = now
        cfg = config_service.load()
        token = cfg.get("cloudflare_api_token") or ""
        domains = cfg.get("ddns_domains") or []
        if not token or not domains:
            return
        for result in ddns_service.sync(token, domains):
            domain = result["domain"]
            if result["status"] == "updated":
                if webhook_url:
                    self._notify_ddns_change(webhook_url, domain, result["old_ip"], result["new_ip"])
                self._ddns_failing.discard(domain)
            elif result["status"] == "error":
                if domain not in self._ddns_failing and webhook_url:
                    self._notify_ddns_error(webhook_url, domain, result["detail"])
                self._ddns_failing.add(domain)
            else:
                self._ddns_failing.discard(domain)

    def _notify_ddns_change(self, webhook_url: str, domain: str, old_ip: str | None, new_ip: str | None) -> None:
        req = urllib.request.Request(
            webhook_url,
            data=json.dumps({"ddns_domain": domain, "old_ip": old_ip, "new_ip": new_ip}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            logger.exception("Failed to send DDNS-change webhook for %s", domain)

    def _notify_ddns_error(self, webhook_url: str, domain: str, detail: str | None) -> None:
        req = urllib.request.Request(
            webhook_url,
            data=json.dumps({"ddns_error": domain, "detail": detail}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            logger.exception("Failed to send DDNS-error webhook for %s", domain)
```

- [ ] **Step 5: Run it to verify it passes, then wire the new tests into `__main__`**

Add the five new test calls to the `if __name__ == "__main__":` block in `backend/test_health_service.py`, before `print("ok")`:

```python
    test_check_ddns_skips_when_no_token_or_domains()
    test_check_ddns_respects_time_gate()
    test_check_ddns_notifies_on_ip_change()
    test_check_ddns_notifies_once_on_first_failure_then_stays_silent()
    test_check_ddns_recovery_is_silent_and_clears_failing_state()
```

Run: `cd backend && python3 test_health_service.py`
Expected: `ok`

- [ ] **Step 6: Run the full backend suite to make sure nothing else broke**

Run: `cd backend && for f in test_*.py; do echo "== $f =="; python3 "$f" || exit 1; done`
Expected: every file prints `ok`

- [ ] **Step 7: Commit**

```bash
git add backend/health_service.py backend/test_health_service.py backend/config_service.py
git commit -m "feat: check Cloudflare DDNS every 5 minutes from the health loop"
```

---

### Task 3: Settings UI — Cloudflare section + `ddns_domains` field

**Files:**
- Modify: `frontend/src/components/SettingsPage.tsx:13-26,182-277` (form state + Cloudflare/ACME block)
- Modify: `frontend/src/api.ts:125-142` (`Config` interface)

**Interfaces:**
- Consumes: `Config` fields `cloudflare_api_token: string`, `wildcard_domain: string` (existing), new `ddns_domains: string[]`
- Produces: nothing new consumed by other tasks — this is the leaf/UI task

- [ ] **Step 1: Add `ddns_domains` to the `Config` type**

In `frontend/src/api.ts`, in the `Config` interface (around line 135), add after `wildcard_domain: string`:

```typescript
  ddns_domains: string[]
```

- [ ] **Step 2: Add `ddnsDomains` to `SettingsPage.tsx`'s form state**

In `frontend/src/components/SettingsPage.tsx`, add to the `FormState` interface (after `wildcard_domain: string`):

```typescript
  ddnsDomains: string
```

(Kept as a single comma-separated string in form state — same pattern the file already uses for other list-shaped raw-text fields — split into `string[]` only on save.)

Add to the initial `useState<FormState>` default (after `wildcard_domain: ''`):

```typescript
    ddnsDomains: '',
```

In the `fetchConfig().then(...)` block, add after `wildcard_domain: String(cfg.wildcard_domain ?? ''),`:

```typescript
          ddnsDomains: Array.isArray(cfg.ddns_domains) ? cfg.ddns_domains.join(', ') : '',
```

- [ ] **Step 3: Split `ddnsDomains` into a list on save**

In `handleSave`, replace:

```typescript
      const updated = await updateConfig({ ...form })
```

with:

```typescript
      const { ddnsDomains, ...rest } = form
      const ddns_domains = ddnsDomains
        .split(',')
        .map((d) => d.trim())
        .filter(Boolean)
      const updated = await updateConfig({ ...rest, ddns_domains })
```

- [ ] **Step 4: Move the Cloudflare fields out of the ACME-only conditional into their own section**

Replace the two conditional blocks (currently `{form.caddy_enabled && form.https_mode === 'acme' && (...)}` containing ACME email + Cloudflare token + wildcard domain, spanning roughly lines 231-277) with two separate blocks — keep ACME email gated on ACME mode, move Cloudflare fields to their own `caddy_enabled`-only section with a header matching the file's one existing section-header precedent (`Change password`):

```tsx
      {form.caddy_enabled && form.https_mode === 'acme' && (
        <div>
          <label className="mb-1 block text-xs uppercase text-neutral-400 dark:text-neutral-500">
            ACME email
          </label>
          <input
            value={form.acme_email}
            onChange={(e) => setForm((f) => ({ ...f, acme_email: e.target.value }))}
            placeholder="you@example.com"
            className="w-full rounded border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 focus:border-neutral-500 focus:outline-none dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
          />
        </div>
      )}

      {form.caddy_enabled && (
        <div className="flex flex-col gap-3 border-t border-neutral-200 pt-5 dark:border-neutral-800">
          <h2 className="text-xs uppercase text-neutral-400 dark:text-neutral-500">Cloudflare</h2>

          <div>
            <label className="mb-1 block text-xs uppercase text-neutral-400 dark:text-neutral-500">
              API token
            </label>
            <input
              type="password"
              value={form.cloudflare_api_token}
              onChange={(e) => setForm((f) => ({ ...f, cloudflare_api_token: e.target.value }))}
              placeholder="optional — enables DNS-01 + wildcard certs, and DDNS below"
              className="w-full rounded border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 focus:border-neutral-500 focus:outline-none dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
            />
            <p className="mt-1 text-xs text-neutral-400 dark:text-neutral-500">
              Needs Zone:Read + DNS:Edit permissions. Leave blank to use Caddy's default HTTP-01/TLS-ALPN-01
              challenges and disable DDNS.
            </p>
          </div>

          <div>
            <label className="mb-1 block text-xs uppercase text-neutral-400 dark:text-neutral-500">
              Wildcard domain
            </label>
            <input
              value={form.wildcard_domain}
              onChange={(e) => setForm((f) => ({ ...f, wildcard_domain: e.target.value }))}
              placeholder="example.com"
              className="w-full rounded border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 focus:border-neutral-500 focus:outline-none dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
            />
            <p className="mt-1 text-xs text-neutral-400 dark:text-neutral-500">
              Optional, requires https_mode "acme" above. If set, issues one wildcard cert (e.g. *.example.com)
              covering every stack instead of a cert per stack domain. Requires the API token above; leave blank
              to keep per-stack certs.
            </p>
          </div>

          <div>
            <label className="mb-1 block text-xs uppercase text-neutral-400 dark:text-neutral-500">
              DDNS domains
            </label>
            <input
              value={form.ddnsDomains}
              onChange={(e) => setForm((f) => ({ ...f, ddnsDomains: e.target.value }))}
              placeholder="example.com, other.com (optional)"
              className="w-full rounded border border-neutral-300 bg-white px-3 py-2 text-sm text-neutral-900 focus:border-neutral-500 focus:outline-none dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100"
            />
            <p className="mt-1 text-xs text-neutral-400 dark:text-neutral-500">
              Comma-separated. Each domain must already have an A record in Cloudflare — litethaus checks
              this host's public IP every 5 minutes and keeps each record's IP in sync, using the API token
              above. Never creates records or touches proxy/TTL settings. Leave blank to disable.
            </p>
          </div>
        </div>
      )}
```

- [ ] **Step 5: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: no output (clean)

- [ ] **Step 6: Manual smoke check**

Run: `cd frontend && npm run dev` (or use the project's `run` skill if available), open Settings, confirm:
- Cloudflare section shows regardless of HTTPS mode (toggle `https_mode` to "off" and "internal" — the section stays visible; ACME email disappears as before)
- Entering `example.com, other.com` in DDNS domains and saving round-trips correctly (reload the page, field still shows `example.com, other.com`)

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/SettingsPage.tsx frontend/src/api.ts
git commit -m "feat: add DDNS domains setting, decouple Cloudflare fields from ACME mode"
```

---

## Follow-up (not part of this plan)

Once merged and running against prod, manually decommission the `cloudflare-ddns` stack in `/docker` (remove the container, delete its compose file with the plaintext token) — a separate manual step, not automated here.
