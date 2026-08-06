import time
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from health_service import HealthService


def _svc() -> HealthService:
    svc = HealthService()
    svc._last_cert_check = float("-inf")
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


if __name__ == "__main__":
    test_check_certs_skips_when_no_webhook_configured()
    test_check_certs_respects_time_gate()
    test_check_certs_notifies_once_for_soon_expiring_cert()
    test_check_certs_does_not_notify_for_cert_far_from_expiry()
    print("ok")
