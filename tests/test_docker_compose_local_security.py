"""Static local-container topology guard; target-host evidence remains manual."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_local_stateful_services_bind_only_to_loopback() -> None:
    source = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert '"127.0.0.1:${REDIS_PORT:-6379}:6379"' in source
    assert '"127.0.0.1:${DB_PORT:-3306}:3306"' in source
    assert '"${DB_PORT:-3306}:3306"' not in source
