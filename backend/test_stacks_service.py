import tempfile
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


if __name__ == "__main__":
    test_scan_parses_metadata_and_isolates_errors()
    test_scan_finds_all_compose_filenames_in_docker_compose_precedence_order()
    print("ok")
