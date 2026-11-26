"""Static local-container topology guard; target-host evidence remains manual."""

from pathlib import Path
import yaml


ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / "pyproject.toml").is_file())


def test_local_stateful_services_bind_only_to_loopback() -> None:
    source = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert '"127.0.0.1:${DB_PORT:-3306}:3306"' in source
    assert '"127.0.0.1:${REDIS_PORT:-6379}:6379"' in source
    assert '"127.0.0.1:${REGISTRATION_REDIS_PORT:-6380}:6379"' in source
    assert '"127.0.0.1:${REGISTRATION_INTAKE_PORT:-8080}:8080"' in source
    compose = yaml.safe_load(source)
    services = compose["services"]
    assert set(services) == {
        "db",
        "redis",
        "registration-redis",
        "registration-intake",
        "registration-loopback",
        "registration-token-verifier",
    }
    assert "no-new-privileges:true" in services["db"]["security_opt"]
    assert "mysql-data:/var/lib/mysql" in services["db"]["volumes"]
    for service in services.values():
        for binding in service.get("ports", ()):
            assert binding.startswith("127.0.0.1:")

    networks = compose["networks"]
    for name, service in services.items():
        attached = set(service.get("networks", ()))
        if service.get("ports"):
            assert any(not networks[net].get("internal", False) for net in attached), (
                f"{name} publishes ports without any non-internal network"
            )
    intake = services["registration-intake"]
    assert not intake.get("ports")
    assert all(networks[net].get("internal", False) for net in intake.get("networks", ()))
