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


if __name__ == "__main__":
    test_build_config_only_includes_routable_stacks()
    test_build_config_prefers_explicit_service_over_first_service()
    test_build_config_pins_admin_listener_so_reloads_dont_cut_off_the_api()
    test_build_config_defaults_to_http_only()
    test_build_config_internal_https_lists_domains_with_internal_issuer()
    test_build_config_acme_https_uses_configured_email()
    print("ok")
