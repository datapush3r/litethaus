import main


def test_no_api_route_is_reachable_at_a_bare_unprefixed_path() -> None:
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
