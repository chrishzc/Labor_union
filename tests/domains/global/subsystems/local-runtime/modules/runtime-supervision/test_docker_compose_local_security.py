"""Static local-container topology guard; target-host evidence remains manual."""

from pathlib import Path
import yaml


ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / "pyproject.toml").is_file())


def test_local_stateful_services_bind_only_to_loopback() -> None:
    source = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert '"127.0.0.1:${REDIS_PORT:-6379}:6379"' in source
    services = yaml.safe_load(source)["services"]
    assert "mysql" not in services
    for service in services.values():
        for binding in service.get("ports", ()):
            assert binding.startswith("127.0.0.1:")
            assert not binding.endswith(":3306")
