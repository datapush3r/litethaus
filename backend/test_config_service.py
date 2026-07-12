import tempfile
from pathlib import Path

from config_service import ConfigService


def test_round_trip_preserves_comments() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "config.yaml"
        svc = ConfigService(path)

        data = svc.load()
        assert data["theme"] == "system"

        svc.update({"theme": "dark"})

        text = path.read_text()
        assert "# litethaus global configuration" in text
        assert "theme: dark" in text

        reloaded = svc.load()
        assert reloaded["theme"] == "dark"
        assert reloaded["stacks_dir"] == "/opt/litethaus/stacks"


if __name__ == "__main__":
    test_round_trip_preserves_comments()
    print("ok")
