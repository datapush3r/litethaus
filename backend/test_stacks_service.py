import tempfile
import threading
from pathlib import Path
from unittest.mock import patch

from stacks_service import StackService, _container_port_from_entry, _detect_port, _icon_candidates, _image_basename

# None of these tests exercise icon-guessing itself, so auto-icon is patched
# off throughout to keep them offline and deterministic (real guessing would
# otherwise hit the network on every scan()/create_stack() call and could
# silently inject an icon into asserted-exact file contents).
NO_ICON = patch("stacks_service.icon_service.guess", return_value=None)


def test_scan_parses_metadata_and_isolates_errors() -> None:
    with tempfile.TemporaryDirectory() as tmp, NO_ICON:
        stacks_dir = Path(tmp)

        good = stacks_dir / "example"
        good.mkdir()
        (good / "docker-compose.yaml").write_text("services:\n  web:\n    image: nginx:alpine\n")
        (good / ".litethaus.yaml").write_text("domain: example.home.arpa\nport: 8080\n")

        broken = stacks_dir / "broken"
        broken.mkdir()
        (broken / "docker-compose.yaml").write_text("services: [this is not: valid: yaml")

        not_a_stack = stacks_dir / "not-a-stack"
        not_a_stack.mkdir()

        svc = StackService(stacks_dir=stacks_dir)
        stacks = {s.name: s for s in svc.scan()}

        assert "not-a-stack" not in stacks
        assert stacks["example"].error is None
        assert stacks["example"].x_litethaus == {"domain": "example.home.arpa", "port": 8080}
        assert stacks["example"].services == ["web"]
        assert stacks["broken"].error is not None


def test_scan_finds_all_compose_filenames_in_docker_compose_precedence_order() -> None:
    with tempfile.TemporaryDirectory() as tmp, NO_ICON:
        stacks_dir = Path(tmp)

        names = {
            "uses-compose-yaml": "compose.yaml",
            "uses-compose-yml": "compose.yml",
            "uses-docker-compose-yaml": "docker-compose.yaml",
            "uses-docker-compose-yml": "docker-compose.yml",
        }
        for stack_name, filename in names.items():
            stack_dir = stacks_dir / stack_name
            stack_dir.mkdir()
            (stack_dir / filename).write_text("services:\n  web:\n    image: nginx:alpine\n")

        # a stack with both compose.yaml and docker-compose.yaml should prefer compose.yaml
        precedence = stacks_dir / "prefers-compose-yaml"
        precedence.mkdir()
        (precedence / "compose.yaml").write_text("services:\n  new:\n    image: nginx:alpine\n")
        (precedence / "docker-compose.yaml").write_text("services:\n  old:\n    image: nginx:alpine\n")

        svc = StackService(stacks_dir=stacks_dir)
        stacks = {s.name: s for s in svc.scan()}

        for stack_name, filename in names.items():
            assert stacks[stack_name].path.endswith(filename), stack_name
            assert stacks[stack_name].error is None, stack_name

        assert stacks["prefers-compose-yaml"].path.endswith("compose.yaml")
        assert stacks["prefers-compose-yaml"].services == ["new"]
        assert stacks["prefers-compose-yaml"].compose_files == ["compose.yaml", "docker-compose.yaml"]
        assert stacks["uses-compose-yaml"].compose_files == ["compose.yaml"]


def test_override_file_is_detected_and_ordered_right_after_the_primary_file() -> None:
    with tempfile.TemporaryDirectory() as tmp, NO_ICON:
        stacks_dir = Path(tmp)

        with_override = stacks_dir / "with-override"
        with_override.mkdir()
        (with_override / "compose.yaml").write_text("services:\n  web:\n    image: nginx:alpine\n")
        (with_override / "compose.override.yaml").write_text("services:\n  web:\n    ports: ['8080:80']\n")
        # a leftover legacy file - inert, but should still show up (last)
        (with_override / "docker-compose.yaml").write_text("services:\n  old:\n    image: nginx:alpine\n")

        # docker-compose.* base pairs with docker-compose.override.*, not compose.override.*
        wrong_family = stacks_dir / "wrong-family"
        wrong_family.mkdir()
        (wrong_family / "docker-compose.yaml").write_text("services:\n  web:\n    image: nginx:alpine\n")
        (wrong_family / "compose.override.yaml").write_text("services:\n  web:\n    ports: ['8080:80']\n")

        no_override = stacks_dir / "no-override"
        no_override.mkdir()
        (no_override / "compose.yaml").write_text("services:\n  web:\n    image: nginx:alpine\n")

        svc = StackService(stacks_dir=stacks_dir)
        stacks = {s.name: s for s in svc.scan()}

        assert stacks["with-override"].override_file == "compose.override.yaml"
        assert stacks["with-override"].compose_files == ["compose.yaml", "compose.override.yaml", "docker-compose.yaml"]

        # the mismatched-family override file isn't recognized at all - not
        # merged, not even shown as an editor tab (matching docker compose's
        # own behavior, which wouldn't auto-include it either)
        assert stacks["wrong-family"].override_file is None
        assert stacks["wrong-family"].compose_files == ["docker-compose.yaml"]

        assert stacks["no-override"].override_file is None
        assert stacks["no-override"].compose_files == ["compose.yaml"]


def test_multiple_compose_files_are_each_independently_readable_and_writable() -> None:
    with tempfile.TemporaryDirectory() as tmp, NO_ICON:
        stacks_dir = Path(tmp)
        stack_dir = stacks_dir / "multi"
        stack_dir.mkdir()
        (stack_dir / "compose.yaml").write_text("services:\n  web:\n    image: nginx:alpine\n")
        (stack_dir / "docker-compose.yaml").write_text("services:\n  legacy:\n    image: nginx:alpine\n")

        svc = StackService(stacks_dir=stacks_dir)
        svc.scan()

        assert svc.read_raw("multi") == "services:\n  web:\n    image: nginx:alpine\n"
        assert svc.read_raw("multi", "compose.yaml") == "services:\n  web:\n    image: nginx:alpine\n"
        assert svc.read_raw("multi", "docker-compose.yaml") == "services:\n  legacy:\n    image: nginx:alpine\n"

        svc.write_raw("multi", "services:\n  legacy:\n    image: nginx:latest\n", "docker-compose.yaml")
        assert svc.read_raw("multi", "docker-compose.yaml") == "services:\n  legacy:\n    image: nginx:latest\n"
        # writing the non-primary file must not touch the primary one, or
        # what docker compose/caddy actually read for this stack
        assert svc.read_raw("multi", "compose.yaml") == "services:\n  web:\n    image: nginx:alpine\n"

        try:
            svc.read_raw("multi", "not-a-real-file.yaml")
            assert False, "expected unknown filename to raise"
        except KeyError:
            pass


def test_create_write_and_delete_stack_round_trip() -> None:
    with tempfile.TemporaryDirectory() as tmp, NO_ICON:
        svc = StackService(stacks_dir=Path(tmp))

        created = svc.create_stack("web", "services:\n  app:\n    image: nginx:alpine\n")
        assert created.services == ["app"]
        assert created.path.endswith("compose.yaml")

        try:
            svc.create_stack("web", "services: {}\n")
            assert False, "expected duplicate name to raise"
        except ValueError:
            pass

        try:
            svc.create_stack("bad name", "services: {}\n")
            assert False, "expected invalid name to raise"
        except ValueError:
            pass

        try:
            svc.write_raw("web", "services: [this is not: valid: yaml")
            assert False, "expected invalid yaml to raise"
        except Exception:
            pass
        # a rejected write must not clobber the file it failed to replace
        assert svc.read_raw("web") == "services:\n  app:\n    image: nginx:alpine\n"

        updated = svc.write_raw("web", "services:\n  app:\n    image: nginx:latest\n")
        assert svc.read_raw("web") == "services:\n  app:\n    image: nginx:latest\n"
        assert updated.services == ["app"]

        svc.delete_stack("web")
        assert "web" not in {s.name for s in svc.list_stacks()}


def test_update_metadata_patches_x_litethaus_and_preserves_comments() -> None:
    with tempfile.TemporaryDirectory() as tmp, NO_ICON:
        stacks_dir = Path(tmp)
        stack_dir = stacks_dir / "web"
        stack_dir.mkdir()
        (stack_dir / "compose.yaml").write_text("services:\n  app:\n    image: nginx:alpine\n")
        (stack_dir / ".litethaus.yaml").write_text(
            "# a comment worth keeping\ndomain: old.home.arpa\nport: 8080\n"
        )

        svc = StackService(stacks_dir=stacks_dir)
        svc.scan()

        updated = svc.update_metadata("web", {"domain": "new.home.arpa", "icon": "nginx", "service": None})
        assert updated.x_litethaus == {"domain": "new.home.arpa", "port": 8080, "icon": "nginx"}
        assert (stack_dir / ".litethaus.yaml").read_text().startswith("# a comment worth keeping\n")
        # metadata never touches the compose file itself
        assert svc.read_raw("web") == "services:\n  app:\n    image: nginx:alpine\n"


def test_image_basename_strips_registry_tag_and_digest() -> None:
    assert _image_basename("linuxserver/plex:latest") == "plex"
    assert _image_basename("ghcr.io/foo/bar:tag") == "bar"
    assert _image_basename("nginx@sha256:abcdef") == "nginx"
    assert _image_basename("myregistry.local:5000/foo/bar:tag") == "bar"
    assert _image_basename("redis") == "redis"


def test_icon_candidates_orders_image_basenames_before_name_before_services() -> None:
    data = {
        "services": {
            "web": {"image": "linuxserver/plex:latest"},
            "worker": {"image": "redis:alpine"},
        }
    }
    assert _icon_candidates("my-stack", data) == ["plex", "redis", "my-stack", "web", "worker"]


def test_create_stack_injects_guessed_icon_when_none_provided() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        svc = StackService(stacks_dir=Path(tmp))
        original = "services:\n  app:\n    image: linuxserver/plex:latest\n"
        with patch("stacks_service.icon_service.guess", return_value="plex"):
            created = svc.create_stack("media", original)

        assert created.x_litethaus == {"icon": "plex"}
        # the guessed icon lands in the sidecar file, never in the compose file
        assert svc.read_raw("media") == original
        assert "icon: plex" in (Path(tmp) / "media" / ".litethaus.yaml").read_text()


def test_create_stack_migrates_embedded_x_litethaus_and_skips_guess_when_icon_present() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        svc = StackService(stacks_dir=Path(tmp))
        submitted = "x-litethaus:\n  icon: custom\nservices:\n  app:\n    image: nginx:alpine\n"
        with patch("stacks_service.icon_service.guess", return_value="something-else") as guess:
            created = svc.create_stack("web", submitted)

        guess.assert_not_called()
        assert created.x_litethaus == {"icon": "custom"}
        # scan()'s migration path strips the embedded block from the compose
        # file and moves it into the sidecar, same as any pre-existing stack
        assert "x-litethaus" not in svc.read_raw("web")
        assert svc.read_raw("web") == "services:\n  app:\n    image: nginx:alpine\n"
        assert "icon: custom" in (Path(tmp) / "web" / ".litethaus.yaml").read_text()


def test_create_stack_leaves_content_untouched_when_no_guess_found() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        svc = StackService(stacks_dir=Path(tmp))
        original = "services:\n  app:\n    image: nginx:alpine\n"
        with patch("stacks_service.icon_service.guess", return_value=None):
            created = svc.create_stack("web", original)

        assert created.x_litethaus == {}
        assert svc.read_raw("web") == original
        assert not (Path(tmp) / "web" / ".litethaus.yaml").exists()


def test_scan_backfills_icon_for_existing_iconless_stack() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        stacks_dir = Path(tmp)
        stack_dir = stacks_dir / "media"
        stack_dir.mkdir()
        original = "services:\n  app:\n    image: linuxserver/plex:latest\n"
        (stack_dir / "compose.yaml").write_text(original)

        svc = StackService(stacks_dir=stacks_dir)
        with patch("stacks_service.icon_service.guess", return_value="plex"):
            stacks = {s.name: s for s in svc.scan()}

        assert stacks["media"].x_litethaus == {"icon": "plex"}
        assert "icon: plex" in (stack_dir / ".litethaus.yaml").read_text()
        assert (stack_dir / "compose.yaml").read_text() == original


def test_scan_does_not_overwrite_explicit_empty_icon() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        stacks_dir = Path(tmp)
        stack_dir = stacks_dir / "media"
        stack_dir.mkdir()
        (stack_dir / "compose.yaml").write_text("services:\n  app:\n    image: linuxserver/plex:latest\n")
        original_meta = 'icon: ""\n'
        (stack_dir / ".litethaus.yaml").write_text(original_meta)

        svc = StackService(stacks_dir=stacks_dir)
        with patch("stacks_service.icon_service.guess", return_value="plex") as guess:
            stacks = {s.name: s for s in svc.scan()}

        guess.assert_not_called()
        assert stacks["media"].x_litethaus == {"icon": ""}
        assert (stack_dir / ".litethaus.yaml").read_text() == original_meta


def test_scan_migrates_embedded_x_litethaus_to_sidecar_and_preserves_compose_comments() -> None:
    with tempfile.TemporaryDirectory() as tmp, NO_ICON:
        stacks_dir = Path(tmp)
        stack_dir = stacks_dir / "legacy"
        stack_dir.mkdir()
        (stack_dir / "compose.yaml").write_text(
            "# a comment worth keeping\n"
            "x-litethaus:\n  domain: legacy.home.arpa\n  port: 8080\n"
            "services:\n  app:\n    image: nginx:alpine\n"
        )

        svc = StackService(stacks_dir=stacks_dir)
        stacks = {s.name: s for s in svc.scan()}

        assert stacks["legacy"].x_litethaus == {"domain": "legacy.home.arpa", "port": 8080}
        assert (stack_dir / ".litethaus.yaml").read_text() == "domain: legacy.home.arpa\nport: 8080\n"
        compose_text = (stack_dir / "compose.yaml").read_text()
        assert "x-litethaus" not in compose_text
        assert compose_text.startswith("# a comment worth keeping\n")


def test_container_port_from_entry_handles_all_compose_port_syntaxes() -> None:
    assert _container_port_from_entry("8080:80") == 80
    assert _container_port_from_entry("80") == 80
    assert _container_port_from_entry("80/tcp") == 80
    assert _container_port_from_entry("8080:80/udp") == 80
    assert _container_port_from_entry(80) == 80
    assert _container_port_from_entry({"target": 80, "published": 8080}) == 80
    assert _container_port_from_entry({"published": 8080}) is None
    assert _container_port_from_entry("not-a-port") is None


def test_detect_port_prefers_ports_over_expose_and_picks_lowest() -> None:
    assert _detect_port({"ports": ["8080:8080", "8443:443"]}) == 443
    assert _detect_port({"expose": ["9000", "80"]}) == 80
    # ports: present (even if higher) wins over expose: entirely
    assert _detect_port({"ports": ["8080:9000"], "expose": ["80"]}) == 9000
    assert _detect_port({}) is None
    assert _detect_port({"network_mode": "host"}) is None


def test_detect_service_metadata_reports_per_service_port_and_suggested_name() -> None:
    svc = StackService(stacks_dir=Path("/tmp"))

    single = svc.detect_service_metadata(
        "name: plex-stack\nservices:\n  plex:\n    image: plex\n    ports: ['32400:32400']\n"
    )
    assert single == {"suggested_name": "plex-stack", "services": [{"name": "plex", "port": 32400}]}

    # no top-level name, exactly one service -> falls back to the service key
    sole_service = svc.detect_service_metadata("services:\n  plex:\n    image: plex\n    expose: ['32400']\n")
    assert sole_service["suggested_name"] == "plex"

    # host networking, no ports/expose -> undetectable, not a silent guess
    host_networked = svc.detect_service_metadata("services:\n  plex:\n    image: plex\n    network_mode: host\n")
    assert host_networked["services"] == [{"name": "plex", "port": None}]

    # multiple services and no top-level name -> ambiguous, never auto-picked
    multi = svc.detect_service_metadata(
        "services:\n  app:\n    ports: ['8080:80']\n  db:\n    image: postgres\n"
    )
    assert multi["suggested_name"] is None
    assert multi["services"] == [{"name": "app", "port": 80}, {"name": "db", "port": None}]

    invalid = svc.detect_service_metadata("services: [this is not: valid: yaml")
    assert invalid == {"suggested_name": None, "services": []}


def test_watch_paths_covers_stacks_dir_and_each_stack_dir_only() -> None:
    # Must stay bounded to stacks_dir plus its immediate stack subdirectories -
    # never recurse into a stack's own data/media/db subfolders (that's what
    # made watch_forever expensive when stacks_dir points at a host's whole
    # compose root; see CLAUDE.md architecture note 1).
    with tempfile.TemporaryDirectory() as tmp:
        stacks_dir = Path(tmp)
        (stacks_dir / "plex").mkdir()
        (stacks_dir / "plex" / "data").mkdir()  # nested - must NOT appear in watch paths
        (stacks_dir / "sonarr").mkdir()
        (stacks_dir / "not-a-dir.txt").write_text("")

        svc = StackService(stacks_dir=stacks_dir)

        assert set(svc._watch_paths()) == {stacks_dir, stacks_dir / "plex", stacks_dir / "sonarr"}


def test_restart_watcher_signals_the_current_stop_event_when_armed() -> None:
    svc = StackService(stacks_dir=Path("/tmp"))

    assert svc._watch_stop_event is None
    svc.restart_watcher()  # no watcher running yet: must be a safe no-op

    stop_event = threading.Event()
    svc._watch_stop_event = stop_event
    svc.restart_watcher()

    assert stop_event.is_set()


if __name__ == "__main__":
    test_scan_parses_metadata_and_isolates_errors()
    test_scan_finds_all_compose_filenames_in_docker_compose_precedence_order()
    test_override_file_is_detected_and_ordered_right_after_the_primary_file()
    test_multiple_compose_files_are_each_independently_readable_and_writable()
    test_create_write_and_delete_stack_round_trip()
    test_update_metadata_patches_x_litethaus_and_preserves_comments()
    test_image_basename_strips_registry_tag_and_digest()
    test_icon_candidates_orders_image_basenames_before_name_before_services()
    test_create_stack_injects_guessed_icon_when_none_provided()
    test_create_stack_migrates_embedded_x_litethaus_and_skips_guess_when_icon_present()
    test_create_stack_leaves_content_untouched_when_no_guess_found()
    test_scan_backfills_icon_for_existing_iconless_stack()
    test_scan_does_not_overwrite_explicit_empty_icon()
    test_scan_migrates_embedded_x_litethaus_to_sidecar_and_preserves_compose_comments()
    test_container_port_from_entry_handles_all_compose_port_syntaxes()
    test_detect_port_prefers_ports_over_expose_and_picks_lowest()
    test_detect_service_metadata_reports_per_service_port_and_suggested_name()
    test_watch_paths_covers_stacks_dir_and_each_stack_dir_only()
    test_restart_watcher_signals_the_current_stop_event_when_armed()
    print("ok")
