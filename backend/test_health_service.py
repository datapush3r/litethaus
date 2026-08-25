import datetime as _dt
import tempfile
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

from health_service import HealthService


def _fake_now(hour: int, minute: int) -> _dt.datetime:
    return _dt.datetime(2024, 1, 1, hour, minute)


def _svc() -> HealthService:
    svc = HealthService()
    svc._last_cert_check = float("-inf")
    svc._last_ddns_check = float("-inf")
    svc._last_update_check = float("-inf")
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

        svc._last_cert_check = 0.0
        svc._check_certs_once("http://hook.example.com")
        assert urlopen.call_count == 1


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

        svc._last_ddns_check = float("-inf")
        svc._check_ddns_once("http://hook.example.com")
        assert urlopen.call_count == 1


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
        assert urlopen.call_count == 1
        assert "app.example.com" not in svc._ddns_failing


def test_check_ddns_drops_stale_entry_when_domain_removed_from_config() -> None:
    svc = _svc()
    svc._ddns_failing = {"gone.example.com"}
    result = [{"domain": "app.example.com", "status": "unchanged", "old_ip": "1.2.3.4", "new_ip": "1.2.3.4", "detail": None}]
    with patch(
        "health_service.config_service.load",
        return_value={"cloudflare_api_token": "tok", "ddns_domains": ["app.example.com"]},
    ), patch("health_service.ddns_service.sync", return_value=result), \
         patch("health_service.urllib.request.urlopen"):
        svc._check_ddns_once("http://hook.example.com")
        assert "gone.example.com" not in svc._ddns_failing


def _update_stack(name: str = "app") -> Mock:
    stack = Mock()
    stack.name = name
    stack.error = None
    return stack


def test_check_updates_skips_when_disabled_in_config() -> None:
    svc = _svc()
    with patch("health_service.config_service.load", return_value={"update_check_enabled": False}), \
         patch("health_service.stack_service.list_stacks") as list_stacks:
        svc._check_updates_once("http://hook.example.com")
        list_stacks.assert_not_called()


def test_check_updates_respects_time_gate() -> None:
    svc = _svc()
    svc._last_update_check = time.monotonic()
    with patch("health_service.stack_service.list_stacks") as list_stacks:
        svc._check_updates_once("http://hook.example.com")
        list_stacks.assert_not_called()


def test_check_updates_skips_stopped_stacks() -> None:
    svc = _svc()
    with patch("health_service.config_service.load", return_value={}), \
         patch("health_service.stack_service.list_stacks", return_value=[_update_stack()]), \
         patch("health_service.docker_service.container_status", return_value="stopped"), \
         patch("health_service.docker_service.compose_check_update") as check_update:
        svc._check_updates_once("http://hook.example.com")
        check_update.assert_not_called()
        assert svc.update_available("app") is False


def test_check_updates_notifies_once_on_first_detection_then_stays_silent() -> None:
    svc = _svc()
    with patch("health_service.config_service.load", return_value={}), \
         patch("health_service.stack_service.list_stacks", return_value=[_update_stack()]), \
         patch("health_service.docker_service.container_status", return_value="running"), \
         patch("health_service.docker_service.compose_check_update", return_value=True), \
         patch("health_service.urllib.request.urlopen") as urlopen:
        svc._check_updates_once("http://hook.example.com")
        assert urlopen.call_count == 1
        assert svc.update_available("app") is True

        svc._last_update_check = float("-inf")
        svc._check_updates_once("http://hook.example.com")
        assert urlopen.call_count == 1


def test_check_updates_clear_flag_resets_notified_state() -> None:
    svc = _svc()
    with patch("health_service.config_service.load", return_value={}), \
         patch("health_service.stack_service.list_stacks", return_value=[_update_stack()]), \
         patch("health_service.docker_service.container_status", return_value="running"), \
         patch("health_service.docker_service.compose_check_update", return_value=True), \
         patch("health_service.urllib.request.urlopen") as urlopen:
        svc._check_updates_once("http://hook.example.com")
        assert urlopen.call_count == 1

        svc.clear_update_flag("app")
        assert svc.update_available("app") is False

        svc._last_update_check = float("-inf")
        svc._check_updates_once("http://hook.example.com")
        assert urlopen.call_count == 2


def test_run_auto_updates_skips_when_disabled() -> None:
    svc = _svc()
    with patch("health_service.config_service.load", return_value={"update_check_enabled": False}), \
         patch("health_service.stack_service.list_stacks") as list_stacks:
        svc._run_auto_updates_once("http://hook.example.com")
        list_stacks.assert_not_called()


def test_run_auto_updates_skips_before_scheduled_time() -> None:
    svc = _svc()
    with patch("health_service.config_service.load", return_value={"auto_update_time": "03:00"}), \
         patch("health_service.datetime") as mock_dt, \
         patch("health_service.stack_service.list_stacks") as list_stacks:
        mock_dt.now.return_value = _fake_now(1, 0)
        mock_dt.strptime = _dt.datetime.strptime
        svc._run_auto_updates_once("http://hook.example.com")
        list_stacks.assert_not_called()


def test_run_auto_updates_only_touches_opted_in_running_stacks_with_update() -> None:
    svc = _svc()
    opted_in = _update_stack("opted-in")
    opted_in.x_litethaus = {"auto_update": True}
    not_opted_in = _update_stack("not-opted-in")
    not_opted_in.x_litethaus = {}
    stacks = [opted_in, not_opted_in]

    with patch("health_service.config_service.load", return_value={"auto_update_time": "03:00"}), \
         patch("health_service.datetime") as mock_dt, \
         patch("health_service.stack_service.list_stacks", return_value=stacks), \
         patch("health_service.docker_service.container_status", return_value="running"), \
         patch("health_service.docker_service.compose_check_update", return_value=True) as check_update, \
         patch("health_service.docker_service.compose_update", return_value=(True, "done")) as compose_update, \
         patch("health_service.urllib.request.urlopen") as urlopen:
        mock_dt.now.return_value = _fake_now(4, 0)
        mock_dt.strptime = _dt.datetime.strptime
        svc._run_auto_updates_once("http://hook.example.com")

    assert check_update.call_count == 1
    assert check_update.call_args[0][0] is opted_in
    compose_update.assert_called_once_with(opted_in)
    assert urlopen.call_count == 1
    assert svc.update_available("opted-in") is False


def test_run_auto_updates_skips_stack_with_no_update_available() -> None:
    svc = _svc()
    stack = _update_stack()
    stack.x_litethaus = {"auto_update": True}
    with patch("health_service.config_service.load", return_value={"auto_update_time": "03:00"}), \
         patch("health_service.datetime") as mock_dt, \
         patch("health_service.stack_service.list_stacks", return_value=[stack]), \
         patch("health_service.docker_service.container_status", return_value="running"), \
         patch("health_service.docker_service.compose_check_update", return_value=False), \
         patch("health_service.docker_service.compose_update") as compose_update:
        mock_dt.now.return_value = _fake_now(4, 0)
        mock_dt.strptime = _dt.datetime.strptime
        svc._run_auto_updates_once("http://hook.example.com")
        compose_update.assert_not_called()


def test_run_auto_updates_runs_once_per_day() -> None:
    svc = _svc()
    stack = _update_stack()
    stack.x_litethaus = {"auto_update": True}
    with patch("health_service.config_service.load", return_value={"auto_update_time": "03:00"}), \
         patch("health_service.datetime") as mock_dt, \
         patch("health_service.stack_service.list_stacks", return_value=[stack]) as list_stacks, \
         patch("health_service.docker_service.container_status", return_value="running"), \
         patch("health_service.docker_service.compose_check_update", return_value=False):
        mock_dt.now.return_value = _fake_now(4, 0)
        mock_dt.strptime = _dt.datetime.strptime
        svc._run_auto_updates_once("http://hook.example.com")
        svc._run_auto_updates_once("http://hook.example.com")
        assert list_stacks.call_count == 1


def test_run_auto_updates_now_skips_when_disabled() -> None:
    svc = _svc()
    with patch("health_service.config_service.load", return_value={"update_check_enabled": False}), \
         patch("health_service.stack_service.list_stacks") as list_stacks:
        assert svc.run_auto_updates_now() == []
        list_stacks.assert_not_called()


def test_run_auto_updates_now_bypasses_schedule_gate() -> None:
    svc = _svc()
    stack = _update_stack()
    stack.x_litethaus = {"auto_update": True}
    with patch("health_service.config_service.load", return_value={}), \
         patch("health_service.stack_service.list_stacks", return_value=[stack]), \
         patch("health_service.docker_service.container_status", return_value="running"), \
         patch("health_service.docker_service.compose_check_update", return_value=True), \
         patch("health_service.docker_service.compose_update", return_value=(True, "done")), \
         patch("health_service.urllib.request.urlopen"):
        results = svc.run_auto_updates_now()

    assert results == [{"stack": "app", "ok": True}]
    assert svc.update_available("app") is False


def test_run_auto_updates_now_marks_today_so_schedule_does_not_repeat() -> None:
    svc = _svc()
    stack = _update_stack()
    stack.x_litethaus = {"auto_update": True}
    with patch("health_service.config_service.load", return_value={}), \
         patch("health_service.stack_service.list_stacks", return_value=[stack]) as list_stacks, \
         patch("health_service.docker_service.container_status", return_value="running"), \
         patch("health_service.docker_service.compose_check_update", return_value=False):
        svc.run_auto_updates_now()
        assert list_stacks.call_count == 1

        svc._run_auto_updates_once("")
        assert list_stacks.call_count == 1


def test_ping_healthchecks_skips_when_no_url_configured() -> None:
    svc = _svc()
    with patch("health_service.urllib.request.urlopen") as urlopen:
        svc._ping_healthchecks("")
        urlopen.assert_not_called()


def test_ping_healthchecks_pings_configured_url() -> None:
    svc = _svc()
    with patch("health_service.urllib.request.urlopen") as urlopen:
        svc._ping_healthchecks("https://hc-ping.com/some-uuid")
        assert urlopen.call_count == 1
        assert urlopen.call_args[0][0] == "https://hc-ping.com/some-uuid"


def test_ping_healthchecks_swallows_errors() -> None:
    svc = _svc()
    with patch("health_service.urllib.request.urlopen", side_effect=OSError("unreachable")):
        svc._ping_healthchecks("https://hc-ping.com/some-uuid")


def test_check_once_logs_health_transitions_only() -> None:
    svc = _svc()
    stack = Mock()
    stack.name = "app"
    stack.error = None
    with patch("health_service.stack_service.list_stacks", return_value=[stack]), \
         patch("health_service.config_service.load", return_value={}), \
         patch("health_service.docker_service.container_details", return_value=[]), \
         patch("health_service.docker_service.host_container_stats", return_value=[]), \
         patch("health_service.docker_service.container_status", return_value="stopped"), \
         patch("health_service.caddy_service.sync"), \
         patch("health_service.docker_service.summarize_health", side_effect=["healthy", "healthy", "unhealthy"]):
        svc.check_once()
        svc.check_once()
        svc.check_once()
    log = svc.health_log("app")
    assert [e["health"] for e in log] == ["healthy", "unhealthy"]
    assert svc.health_log("other-stack") == []


def test_check_caddy_sync_respects_time_gate() -> None:
    from pathlib import Path

    from stacks_service import stack_service

    original = stack_service._stacks_dir_override
    stack_service._stacks_dir_override = Path(tempfile.mkdtemp())
    try:
        svc = _svc()
        with patch("health_service.config_service.load", return_value={"caddy_enabled": True}), \
             patch("health_service.caddy_service.sync") as sync:
            svc._check_caddy_sync_once()
            assert sync.call_count == 1
            svc._check_caddy_sync_once()
            assert sync.call_count == 1
    finally:
        stack_service._stacks_dir_override = original


def test_check_caddy_sync_skips_when_disabled() -> None:
    svc = _svc()
    with patch("health_service.config_service.load", return_value={"caddy_enabled": False}), \
         patch("health_service.caddy_service.sync") as sync:
        svc._check_caddy_sync_once()
        assert sync.call_count == 0


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
    test_check_ddns_drops_stale_entry_when_domain_removed_from_config()
    test_check_updates_skips_when_disabled_in_config()
    test_check_updates_respects_time_gate()
    test_check_updates_skips_stopped_stacks()
    test_check_updates_notifies_once_on_first_detection_then_stays_silent()
    test_check_updates_clear_flag_resets_notified_state()
    test_run_auto_updates_skips_when_disabled()
    test_run_auto_updates_skips_before_scheduled_time()
    test_run_auto_updates_only_touches_opted_in_running_stacks_with_update()
    test_run_auto_updates_skips_stack_with_no_update_available()
    test_run_auto_updates_runs_once_per_day()
    test_run_auto_updates_now_skips_when_disabled()
    test_run_auto_updates_now_bypasses_schedule_gate()
    test_run_auto_updates_now_marks_today_so_schedule_does_not_repeat()
    test_ping_healthchecks_skips_when_no_url_configured()
    test_ping_healthchecks_pings_configured_url()
    test_ping_healthchecks_swallows_errors()
    test_check_once_logs_health_transitions_only()
    print("ok")
