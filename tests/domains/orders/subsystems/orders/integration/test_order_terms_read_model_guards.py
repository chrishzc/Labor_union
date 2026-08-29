from types import SimpleNamespace

import pytest

from infrastructure.mysql.order_terms_read_model import lock_staff_mutexes


def test_empty_impacted_staff_set_requires_no_mutex_query():
    cursor = SimpleNamespace(execute=lambda *_args: pytest.fail("unexpected SQL"))

    lock_staff_mutexes(cursor, ())
