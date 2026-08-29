from types import SimpleNamespace

from infrastructure.mysql.scheduling_replacement_writer import _assignment_resolution


def test_terms_rebuild_accepts_empty_assignment_resolution():
    resolution = _assignment_resolution(
        SimpleNamespace(command_family="orders_terms_rebuild"),
        {},
    )

    assert dict(resolution.assignment_id_by_candidate_key) == {}
