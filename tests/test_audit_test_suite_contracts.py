"""Contracts for the repository test-suite quality audit itself."""

from pathlib import Path

from scripts.audit_test_suite import audit


def _write(root: Path, relative: str, source: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def test_audit_accepts_a_real_nontrivial_test_file(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "test_valid.py",
        "def test_value():\n    value = 2 + 2\n    assert value == 4\n",
    )

    objective, review, stats = audit(tmp_path)

    assert objective == []
    assert review == []
    assert stats["files"] == 1
    assert stats["test_functions"] == 1


def test_audit_rejects_pass_only_trivial_assert_and_permanent_skip(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "test_dead.py",
        """import pytest

def test_pass_only():
    pass

def test_trivial():
    assert True

def test_skip_only():
    pytest.skip('dead')

@pytest.mark.skip(reason='dead')
def test_decorated_skip():
    assert 1 == 1
""",
    )

    objective, _, stats = audit(tmp_path)
    messages = [finding.message for finding in objective]

    assert any("pass-only" in message for message in messages)
    assert any("trivially-true" in message for message in messages)
    assert any("only calls pytest.skip" in message for message in messages)
    assert any("unconditionally @pytest.mark.skip" in message for message in messages)
    assert stats["unconditional_skip_tests"] == 2


def test_audit_detects_shadowed_test_names_and_exact_duplicate_files(tmp_path: Path) -> None:
    duplicate_source = "def test_duplicate():\n    assert 2 * 3 == 6\n"
    _write(tmp_path, "test_copy_a.py", duplicate_source)
    _write(tmp_path, "nested/test_copy_b.py", duplicate_source)
    _write(
        tmp_path,
        "test_shadow.py",
        """def test_same():
    assert 1 == 1

def test_same():
    assert 2 == 2
""",
    )

    objective, _, _ = audit(tmp_path)
    messages = [finding.message for finding in objective]

    assert any("shadowed test name" in message for message in messages)
    assert sum("exact duplicate test file content" in message for message in messages) == 2


def test_audit_flags_integration_named_file_for_review_until_marked(tmp_path: Path) -> None:
    candidate = _write(
        tmp_path,
        "integration/test_database_contract.py",
        "def test_database_contract():\n    assert {'ok': True}['ok'] is True\n",
    )

    objective, review, stats = audit(tmp_path)

    assert objective == []
    assert [finding.path for finding in review] == [candidate]
    assert stats["integration_marker_candidates"] == 1

    candidate.write_text(
        "import pytest\npytestmark = pytest.mark.integration\n\ndef test_database_contract():\n    assert {'ok': True}['ok'] is True\n",
        encoding="utf-8",
    )
    objective, review, stats = audit(tmp_path)
    assert objective == []
    assert review == []
    assert stats["integration_marked_files"] == 1


def test_audit_rejects_pytest_named_file_without_tests_and_syntax_errors(tmp_path: Path) -> None:
    _write(tmp_path, "test_no_tests.py", "VALUE = 1\n")
    _write(tmp_path, "test_broken.py", "def test_broken(:\n    pass\n")

    objective, _, _ = audit(tmp_path)
    messages = [finding.message for finding in objective]

    assert any("defines no test_*" in message for message in messages)
    assert any("syntax error" in message for message in messages)
