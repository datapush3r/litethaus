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


if __name__ == "__main__":
    test_scan_parses_metadata_and_isolates_errors()
    print("ok")
