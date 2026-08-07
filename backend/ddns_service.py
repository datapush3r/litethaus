import ipaddress
import json
import logging
import urllib.parse
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
            candidate = line[len("ip=") :].strip()
            try:
                ipaddress.IPv4Address(candidate)
            except ValueError:
                logger.warning("Cloudflare trace endpoint returned a non-IPv4 address: %r", candidate)
                return None
            return candidate
    return None


def _cf_request(token: str, path: str, method: str = "GET", body: dict[str, Any] | None = None) -> dict[str, Any]:
    req = urllib.request.Request(
        f"{CF_API_BASE}{path}",
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.load(resp)
    if data.get("success") is False:
        raise RuntimeError(f"Cloudflare API error: {data.get('errors')}")
    return data


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
    data = _cf_request(token, f"/zones/{zone_id}/dns_records?type=A&name={urllib.parse.quote(domain)}")
    results = data.get("result") or []
    if len(results) > 1:
        # Cloudflare doesn't guarantee result ordering - guessing which of
        # multiple A records (round-robin DNS) to update risks flip-flopping
        # between them. Error instead, matching the zero-records posture.
        raise RuntimeError(f"multiple A records found for {domain}, refusing to guess which to update")
    return results[0] if results else None


def update_record(token: str, zone_id: str, record_id: str, ip: str) -> None:
    _cf_request(token, f"/zones/{zone_id}/dns_records/{record_id}", method="PATCH", body={"content": ip})


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
