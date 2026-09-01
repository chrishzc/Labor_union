from pathlib import Path


ROOT = Path(__file__).parents[7]
SOURCE = (
    ROOT / "scripts" / "launchers" / "start_local_development_no_auth.sh"
).read_text(encoding="utf-8")


def test_no_auth_launcher_forces_source_runtime_before_delegation() -> None:
    delegate = 'exec "$SCRIPT_DIR/start_local_development.sh" "$@"'

    for statement in (
        "export REACT_ADMIN_RUNTIME_PROFILE=source",
        "export REACT_ADMIN_CURRENT_ARTIFACT_DIR=",
        "export REACT_ADMIN_PREVIOUS_ARTIFACT_DIR=",
        "export REACT_ADMIN_ACTIVE_SELECTOR=",
    ):
        assert statement in SOURCE
        assert SOURCE.index(statement) < SOURCE.index(delegate)
