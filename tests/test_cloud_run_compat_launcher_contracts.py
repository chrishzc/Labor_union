from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAUNCHERS = ROOT / "scripts" / "launchers"


def _read(name: str) -> str:
    return (LAUNCHERS / name).read_text(encoding="utf-8", errors="strict")


def test_builder_owns_three_image_builds_and_built_image_acceptance() -> None:
    script = _read("build_and_validate_cloud_run_compat_images.ps1")

    for dockerfile in (
        "docker/compat/Dockerfile.api",
        "docker/compat/Dockerfile.ui",
        "docker/compat/Dockerfile.runtime-ops",
    ):
        assert dockerfile in script
    assert "import google.auth; import ui.app" in script
    assert "scripts.run_durable_job_worker" in script
    assert "DB_HOST=$mysqlContainer" in script
    assert "UI → API container wiring" in script
    assert "latest-image-acceptance.json" in script


def test_initial_setup_builds_before_first_gcp_resource_mutation() -> None:
    script = _read("setup_gcp_cloud_run_compat.ps1")

    build_position = script.index('Write-Section "從Dockerfile自動build並完成本機image驗收"')
    project_mutation_position = script.index('"projects", "create"')
    assert build_position < project_mutation_position
    assert "Assert-Prerequisites" in script
    assert "Wait-EnabledApis" in script
    assert "ApiImage = [string]$builtImages.Api" in script


def test_publisher_defaults_to_source_build_but_keeps_explicit_advanced_mode() -> None:
    script = _read("publish_gcp_cloud_run_compat.ps1")

    assert '[switch]$SelectExistingImages' in script
    assert 'if ($SelectExistingImages)' in script
    assert "build_and_validate_cloud_run_compat_images.ps1" in script
    assert "^sha256:[0-9a-f]{64}$" in script
    assert "RESOURCE_EXHAUSTED" in script
    assert "rateLimitExceeded" in script


def test_bridge_uses_project_scoped_key_os_login_and_restricted_acl() -> None:
    script = _read("manage_gcp_cloud_run_db_bridge.ps1")

    assert 'scratch\\cloud-run-db-bridge\\$ProjectId' in script
    assert '"-t", "ed25519"' in script
    assert '"/inheritance:r"' in script
    assert '"*S-1-5-32-544"' in script
    assert "只允許目前Windows使用者與SYSTEM" in script
    assert '"compute", "os-login", "ssh-keys", "add"' in script
    assert "sudo fuser -k $RemotePort/tcp" in script
    assert "Remove-StaleRemoteListener" in script
    assert ".ssh\\google_compute_engine" not in script
