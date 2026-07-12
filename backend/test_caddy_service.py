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


if __name__ == "__main__":
    test_build_config_only_includes_routable_stacks()
    test_build_config_prefers_explicit_service_over_first_service()
    print("ok")
