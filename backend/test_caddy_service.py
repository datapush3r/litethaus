from types import SimpleNamespace
from unittest.mock import patch, MagicMock

from caddy_service import CaddyService
from stacks_service import Stack


def test_build_config_only_includes_routable_stacks() -> None:
    stacks = [
        Stack(name="app", path="x", x_litethaus={"domain": "app.home.arpa", "port": 8080}, services=["web"]),
        Stack(name="broken", path="x", error="bad yaml"),
        Stack(name="no-domain", path="x", x_litethaus={"port": 9000}, services=["svc"]),
    ]
    cfg = CaddyService(admin_url="http://caddy:2019").build_config(stacks)
    routes = cfg["apps"]["http"]["servers"]["litethaus"]["routes"]

    assert len(routes) == 1
    assert routes[0]["match"] == [{"host": ["app.home.arpa"]}]
    assert routes[0]["handle"][0]["upstreams"] == [{"dial": "web:8080"}]


def test_build_config_adds_passive_health_checks_to_generated_routes() -> None:
    stacks = [Stack(name="app", path="x", x_litethaus={"domain": "app.home.arpa", "port": 8080}, services=["web"])]
    cfg = CaddyService(admin_url="http://caddy:2019").build_config(stacks)
    routes = cfg["apps"]["http"]["servers"]["litethaus"]["routes"]

    assert routes[0]["handle"][0]["health_checks"] == {"passive": {"fail_duration": "30s"}}


def test_build_config_adds_remote_ip_restriction_when_lan_only() -> None:
    stacks = [
        Stack(name="app", path="x", x_litethaus={"domain": "app.home.arpa", "port": 80, "lan_only": True}, services=["web"]),
        Stack(name="public", path="x", x_litethaus={"domain": "public.home.arpa", "port": 80}, services=["web"]),
    ]
    cfg = CaddyService(admin_url="http://caddy:2019").build_config(stacks)
    routes = cfg["apps"]["http"]["servers"]["litethaus"]["routes"]

    assert routes[0]["match"] == [
        {"host": ["app.home.arpa"], "remote_ip": {"ranges": ["10.0.0.0/8", "172.0.0.0/16", "192.168.0.0/16"]}}
    ]
    assert routes[1]["match"] == [{"host": ["public.home.arpa"]}]


def test_build_config_adds_trailing_wildcard_catchall_when_acme_and_wildcard_domain() -> None:
    stacks = [Stack(name="app", path="x", x_litethaus={"domain": "app.example.com", "port": 80}, services=["web"])]
    cfg = CaddyService(admin_url="http://caddy:2019").build_config(
        stacks, https_mode="acme", acme_email="me@example.com", wildcard_domain="example.com"
    )
    routes = cfg["apps"]["http"]["servers"]["litethaus"]["routes"]

    assert routes[-1]["match"] == [{"host": ["*.example.com"]}]
    assert routes[-1]["handle"] == [{"handler": "static_response", "status_code": 404}]
    # the real per-stack route still comes first, so it isn't shadowed
    assert routes[0]["match"] == [{"host": ["app.example.com"]}]


def test_build_config_skips_wildcard_catchall_without_wildcard_domain_or_acme() -> None:
    cfg = CaddyService(admin_url="http://caddy:2019").build_config([], https_mode="acme")
    routes = cfg["apps"]["http"]["servers"]["litethaus"]["routes"]
    assert routes == []

    cfg = CaddyService(admin_url="http://caddy:2019").build_config([], https_mode="off", wildcard_domain="example.com")
    routes = cfg["apps"]["http"]["servers"]["litethaus"]["routes"]
    assert routes == []


def test_build_config_restricts_server_to_http1_only() -> None:
    cfg = CaddyService(admin_url="http://caddy:2019").build_config([])
    assert cfg["apps"]["http"]["servers"]["litethaus"]["protocols"] == ["h1"]


def test_build_config_prefers_explicit_service_over_first_service() -> None:
    stacks = [
        Stack(
            name="app",
            path="x",
            x_litethaus={"domain": "app.home.arpa", "port": 8080, "service": "api"},
            services=["web", "api"],
        ),
    ]
    cfg = CaddyService(admin_url="http://caddy:2019").build_config(stacks)
    routes = cfg["apps"]["http"]["servers"]["litethaus"]["routes"]

    assert routes[0]["handle"][0]["upstreams"] == [{"dial": "api:8080"}]


def test_build_config_pins_admin_listener_so_reloads_dont_cut_off_the_api() -> None:
    cfg = CaddyService(admin_url="http://caddy:2019").build_config([])
    assert cfg["admin"] == {"listen": "0.0.0.0:2019"}


def test_build_config_defaults_to_http_only() -> None:
    stacks = [Stack(name="app", path="x", x_litethaus={"domain": "app.home.arpa", "port": 80}, services=["web"])]
    cfg = CaddyService(admin_url="http://caddy:2019").build_config(stacks)

    assert cfg["apps"]["http"]["servers"]["litethaus"]["listen"] == [":80"]
    assert "tls" not in cfg["apps"]


def test_build_config_internal_https_lists_domains_with_internal_issuer() -> None:
    stacks = [
        Stack(name="app", path="x", x_litethaus={"domain": "app.home.arpa", "port": 80}, services=["web"]),
        Stack(name="broken", path="x", error="bad yaml"),
    ]
    cfg = CaddyService(admin_url="http://caddy:2019").build_config(stacks, https_mode="internal")

    # :80 is deliberately absent so Caddy's automatic_https redirect owns it
    # instead of our own route serving plaintext HTTP alongside HTTPS.
    assert cfg["apps"]["http"]["servers"]["litethaus"]["listen"] == [":443"]
    policy = cfg["apps"]["tls"]["automation"]["policies"][0]
    assert policy["subjects"] == ["app.home.arpa"]
    assert policy["issuers"] == [{"module": "internal"}]


def test_build_config_acme_https_uses_configured_email() -> None:
    stacks = [Stack(name="app", path="x", x_litethaus={"domain": "app.example.com", "port": 80}, services=["web"])]
    cfg = CaddyService(admin_url="http://caddy:2019").build_config(stacks, https_mode="acme", acme_email="me@example.com")

    policy = cfg["apps"]["tls"]["automation"]["policies"][0]
    assert policy["issuers"] == [{"module": "acme", "email": "me@example.com"}]


def test_build_config_acme_https_with_cloudflare_token_adds_dns_challenge() -> None:
    stacks = [Stack(name="app", path="x", x_litethaus={"domain": "app.example.com", "port": 80}, services=["web"])]
    cfg = CaddyService(admin_url="http://caddy:2019").build_config(
        stacks, https_mode="acme", acme_email="me@example.com", cloudflare_api_token="tok123"
    )
    issuer = cfg["apps"]["tls"]["automation"]["policies"][0]["issuers"][0]
    assert issuer["challenges"]["dns"]["provider"] == {"name": "cloudflare", "api_token": "tok123"}
    assert issuer["challenges"]["dns"]["resolvers"] == ["1.1.1.1:53", "8.8.8.8:53"]


def test_build_config_acme_https_with_wildcard_domain_uses_single_wildcard_subject() -> None:
    stacks = [
        Stack(name="app", path="x", x_litethaus={"domain": "app.example.com", "port": 80}, services=["web"]),
        Stack(name="other", path="x", x_litethaus={"domain": "other.example.com", "port": 81}, services=["web"]),
    ]
    cfg = CaddyService(admin_url="http://caddy:2019").build_config(
        stacks, https_mode="acme", acme_email="me@example.com", wildcard_domain="example.com"
    )
    policy = cfg["apps"]["tls"]["automation"]["policies"][0]
    assert policy["subjects"] == ["*.example.com"]


def test_sync_skips_request_when_caddy_disabled() -> None:
    with patch("caddy_service.config_service.load", return_value={"caddy_enabled": False}), \
         patch("caddy_service.urllib.request.urlopen") as urlopen:
        CaddyService(admin_url="http://caddy:2019").sync([])
        urlopen.assert_not_called()


def test_sync_success_records_ok_status() -> None:
    svc = CaddyService(admin_url="http://caddy:2019")
    with patch("caddy_service.config_service.load", return_value={"caddy_enabled": True}), \
         patch("caddy_service.urllib.request.urlopen"):
        svc.sync([])
    status = svc.status()
    assert status["ok"] is True
    assert status["error"] is None
    assert "at" in status


def test_sync_failure_records_error_status() -> None:
    svc = CaddyService(admin_url="http://caddy:2019")
    with patch("caddy_service.config_service.load", return_value={"caddy_enabled": True}), \
         patch("caddy_service.urllib.request.urlopen", side_effect=OSError("no route to host")):
        svc.sync([])
    status = svc.status()
    assert status["ok"] is False
    assert status["error"] == "no route to host"


def test_build_config_appends_valid_extra_routes_after_generated_routes() -> None:
    stacks = [Stack(name="app", path="x", x_litethaus={"domain": "app.home.arpa", "port": 80}, services=["web"])]
    extra = '[{"match": [{"host": ["extra.home.arpa"]}], "handle": []}]'
    cfg = CaddyService(admin_url="http://caddy:2019").build_config(stacks, extra_routes_json=extra)
    routes = cfg["apps"]["http"]["servers"]["litethaus"]["routes"]

    assert len(routes) == 2
    assert routes[0]["match"] == [{"host": ["app.home.arpa"]}]
    assert routes[1]["match"] == [{"host": ["extra.home.arpa"]}]


def test_build_config_skips_malformed_extra_routes_without_raising() -> None:
    cfg = CaddyService(admin_url="http://caddy:2019").build_config([], extra_routes_json="not json")
    assert cfg["apps"]["http"]["servers"]["litethaus"]["routes"] == []

    cfg = CaddyService(admin_url="http://caddy:2019").build_config([], extra_routes_json='{"not": "a list"}')
    assert cfg["apps"]["http"]["servers"]["litethaus"]["routes"] == []


def test_fetch_upstreams_returns_parsed_json() -> None:
    svc = CaddyService(admin_url="http://caddy:2019")
    payload = b'[{"address": "web:8080", "num_requests": 5, "fails": 0}]'
    fake_resp = MagicMock()
    fake_resp.__enter__.return_value.read.return_value = payload
    with patch("caddy_service.urllib.request.urlopen", return_value=fake_resp):
        result = svc.fetch_upstreams()
    assert result == [{"address": "web:8080", "num_requests": 5, "fails": 0}]


def test_version_returns_stripped_output_when_container_found() -> None:
    fake_container = SimpleNamespace(name="litethaus-caddy-1")
    with patch("caddy_service.docker_service.find_caddy_container", return_value=fake_container), \
         patch("caddy_service.docker_service.exec_run", return_value=(0, b"v2.8.4 h1:abc123\n")):
        result = CaddyService(admin_url="http://caddy:2019").version()
    assert result == "v2.8.4 h1:abc123"


def test_version_returns_none_when_exec_fails() -> None:
    fake_container = SimpleNamespace(name="litethaus-caddy-1")
    with patch("caddy_service.docker_service.find_caddy_container", return_value=fake_container), \
         patch("caddy_service.docker_service.exec_run", return_value=(1, b"exec failed\n")):
        result = CaddyService(admin_url="http://caddy:2019").version()
    assert result is None


def test_version_returns_none_when_container_not_found() -> None:
    with patch("caddy_service.docker_service.find_caddy_container", return_value=None), \
         patch("caddy_service.docker_service.exec_run") as exec_run:
        result = CaddyService(admin_url="http://caddy:2019").version()
    assert result is None
    exec_run.assert_not_called()


def test_build_config_adds_logs_key_when_access_log_enabled() -> None:
    cfg = CaddyService(admin_url="http://caddy:2019").build_config([], access_log_enabled=True)
    assert cfg["apps"]["http"]["servers"]["litethaus"]["logs"] == {}


def test_build_config_omits_logs_key_by_default() -> None:
    cfg = CaddyService(admin_url="http://caddy:2019").build_config([])
    assert "logs" not in cfg["apps"]["http"]["servers"]["litethaus"]


if __name__ == "__main__":
    test_build_config_only_includes_routable_stacks()
    test_build_config_adds_passive_health_checks_to_generated_routes()
    test_build_config_adds_trailing_wildcard_catchall_when_acme_and_wildcard_domain()
    test_build_config_skips_wildcard_catchall_without_wildcard_domain_or_acme()
    test_build_config_restricts_server_to_http1_only()
    test_build_config_adds_remote_ip_restriction_when_lan_only()
    test_build_config_prefers_explicit_service_over_first_service()
    test_build_config_pins_admin_listener_so_reloads_dont_cut_off_the_api()
    test_build_config_defaults_to_http_only()
    test_build_config_internal_https_lists_domains_with_internal_issuer()
    test_build_config_acme_https_uses_configured_email()
    test_build_config_acme_https_with_cloudflare_token_adds_dns_challenge()
    test_build_config_acme_https_with_wildcard_domain_uses_single_wildcard_subject()
    test_sync_skips_request_when_caddy_disabled()
    test_sync_success_records_ok_status()
    test_sync_failure_records_error_status()
    test_build_config_appends_valid_extra_routes_after_generated_routes()
    test_build_config_skips_malformed_extra_routes_without_raising()
    test_fetch_upstreams_returns_parsed_json()
    test_version_returns_stripped_output_when_container_found()
    test_version_returns_none_when_exec_fails()
    test_version_returns_none_when_container_not_found()
    test_build_config_adds_logs_key_when_access_log_enabled()
    test_build_config_omits_logs_key_by_default()
    print("ok")
