import main


def test_no_api_route_is_reachable_at_a_bare_unprefixed_path() -> None:
    # Regression guard for a real auth bypass: enforce_auth() in main.py only
    # gates requests whose path starts with "/api/" - a handler registered at
    # a bare path (e.g. "/config" instead of "/api/config") is reachable with
    # zero auth check, even with auth_enabled: true. Every real API route
    # must therefore live under the "api" router's "/api" prefix; only the
    # SPA catch-all (intentionally bare, serves index.html for the client
    # router) is exempt.
    for route in main.app.routes:
        path = getattr(route, "path", None)
        if path is None:
            continue
        if path == "/{full_path:path}":
            continue
        assert path.startswith("/api/"), f"{path!r} is reachable without the auth middleware's /api/ gate"


if __name__ == "__main__":
    test_no_api_route_is_reachable_at_a_bare_unprefixed_path()
    print("ok")
