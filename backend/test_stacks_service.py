import tempfile
import threading
from pathlib import Path

from stacks_service import StackService


def test_scan_parses_metadata_and_isolates_errors() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        stacks_dir = Path(tmp)

        good = stacks_dir / "example"
        good.mkdir()
        (good / "docker-compose.yaml").write_text(
            "x-litethaus:\n  domain: example.home.arpa\n  port: 8080\n"
            "services:\n  web:\n    image: nginx:alpine\n"
        )

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
    with tempfile.TemporaryDirectory() as tmp:
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
    with tempfile.TemporaryDirectory() as tmp:
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
    with tempfile.TemporaryDirectory() as tmp:
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
    with tempfile.TemporaryDirectory() as tmp:
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
    test_restart_watcher_signals_the_current_stop_event_when_armed()
    print("ok")
