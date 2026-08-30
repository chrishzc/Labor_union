"""BeClass review Apply must fail closed without owning-domain commands."""

from types import SimpleNamespace

import pytest

from api.dependencies.beclass_import_review import (
    build_beclass_import_review_application,
)
from domains.case_import.beclass_import_review import BeClassImportSourceKind
from infrastructure.mysql.beclass_import_review_writer import (
    BeClassImportReviewOwnerCommandUnavailable,
)
from subsystems.case_import.beclass_import_review_workflow import (
    BeClassImportReviewWriterError,
)


class _Connection:
    def __init__(self):
        self.calls = 0

    def cursor(self):
        self.calls += 1
        raise AssertionError("owner-command gate must not access the connection")


@pytest.mark.parametrize(
    ("source_kind", "code"),
    (
        (
            BeClassImportSourceKind.CLIENT,
            "beclass_import_review_client_owner_command_unavailable",
        ),
        (
            BeClassImportSourceKind.STAFF,
            "beclass_import_review_staff_owner_command_unavailable",
        ),
        (
            BeClassImportSourceKind.HCM,
            "beclass_import_review_hcm_owner_command_unavailable",
        ),
    ),
)
def test_review_owner_command_gate_fails_closed_without_sql(source_kind, code):
    connection = _Connection()
    gate = BeClassImportReviewOwnerCommandUnavailable(connection)

    with pytest.raises(BeClassImportReviewWriterError) as raised:
        gate.apply_corrected_row(SimpleNamespace(source_kind=source_kind))

    assert raised.value.code == code
    assert raised.value.category.value == "domain_blocked"
    assert connection.calls == 0


def test_api_composition_uses_fail_closed_owner_command_gate():
    application = build_beclass_import_review_application(_Connection())

    assert isinstance(
        application.workflow._writer,
        BeClassImportReviewOwnerCommandUnavailable,
    )
