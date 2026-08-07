import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from health_service import HealthService


def _svc() -> HealthService:
    svc = HealthService()
    svc._last_cert_check = float("-inf")
    svc._last_ddns_check = float("-inf")
    return svc


def test_check_certs_skips_when_no_webhook_configured() -> None:
    svc = _svc()
    with patch("health_service.cert_service.list_certificates") as list_certs:
        svc._check_certs_once("")
        list_certs.assert_not_called()


def test_check_certs_respects_time_gate() -> None:
    svc = _svc()
    svc._last_cert_check = time.monotonic()
    with patch("health_service.cert_service.list_certificates") as list_certs:
        svc._check_certs_once("http://hook.example.com")
        list_certs.assert_not_called()


def test_check_certs_notifies_once_for_soon_expiring_cert() -> None:
    svc = _svc()
    soon = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    certs = [{"domains": ["app.example.com"], "issuer": "Let's Encrypt", "expires_at": soon}]
    with patch("health_service.cert_service.list_certificates", return_value=certs), \
         patch("health_service.urllib.request.urlopen") as urlopen:
        svc._check_certs_once("http://hook.example.com")
        assert urlopen.call_count == 1

        svc._last_cert_check = 0.0  # force past the time-gate again
        svc._check_certs_once("http://hook.example.com")
        assert urlopen.call_count == 1  # same cert, no repeat alert


def test_check_certs_does_not_notify_for_cert_far_from_expiry() -> None:
    svc = _svc()
    later = (datetime.now(timezone.utc) + timedelta(days=90)).isoformat()
    certs = [{"domains": ["app.example.com"], "issuer": "Let's Encrypt", "expires_at": later}]
    with patch("health_service.cert_service.list_certificates", return_value=certs), \
         patch("health_service.urllib.request.urlopen") as urlopen:
        svc._check_certs_once("http://hook.example.com")
        urlopen.assert_not_called()


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


if __name__ == "__main__":
    test_check_certs_skips_when_no_webhook_configured()
    test_check_certs_respects_time_gate()
    test_check_certs_notifies_once_for_soon_expiring_cert()
    test_check_certs_does_not_notify_for_cert_far_from_expiry()
    test_check_ddns_skips_when_no_token_or_domains()
    test_check_ddns_respects_time_gate()
    test_check_ddns_notifies_on_ip_change()
    test_check_ddns_notifies_once_on_first_failure_then_stays_silent()
    test_check_ddns_recovery_is_silent_and_clears_failing_state()
    print("ok")
