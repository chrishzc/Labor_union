"""Current HCM field reviews paginate after the owner resolution predicate."""
from infrastructure.mysql.hcm_resubmission_repository import MySqlHcmResubmissionRepository


class Cursor:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def execute(self, sql, args):
        self.calls.append((sql, args))
        before = args[0]
        self.page = [r for r in self.rows if before is None or r['id'] < before][:100]
    def fetchall(self):
        return self.page


class Connection:
    def __init__(self, rows):
        self.reader = Cursor(rows)
    def cursor(self):
        return self.reader


def test_current_predicate_scans_past_first_hundred_and_paginates_remaining(monkeypatch):
    rows = [dict(id=i, review_identity=f'review-{i}', case_no=f'SYNTH-{i}',
                 issue_codes=['hcm_field_invalid:縣市']) for i in range(102, 0, -1)]
    connection = Connection(rows)
    repository = MySqlHcmResubmissionRepository(connection)
    monkeypatch.setattr(repository, 'query_review', lambda identity: {'resolved': int(identity.split('-')[1]) > 2})
    first = repository.query_current_reviews(limit=1, before_id=None)
    assert [item['case_no'] for item in first['items']] == ['SYNTH-2']
    assert first['next_cursor'] == 2
    second = repository.query_current_reviews(limit=1, before_id=first['next_cursor'])
    assert [item['case_no'] for item in second['items']] == ['SYNTH-1']
    assert second['next_cursor'] is None
    assert len(connection.reader.calls) == 3
    assert connection.reader.calls[1][1] == (3, 3)


def test_multiple_warning_fields_are_visible_without_unusable_correction_button():
    repository = MySqlHcmResubmissionRepository(Connection([dict(id=1, review_identity='review-1', case_no='SYNTH-1', issue_codes=['hcm_field_invalid:縣市', 'hcm_field_missing:姓名'])]))
    page = repository.query_current_reviews(limit=20, before_id=None)
    assert len(page['items']) == 1
    assert page['items'][0]['fields'] == ['姓名', '縣市']
    assert page['items'][0]['can_correct'] is False


def test_service_lock_blocks_order_correction_but_not_client_field(monkeypatch):
    rows = [dict(id=2, review_identity='order-review', case_no='SYNTH-2',
                 issue_codes=['hcm_field_invalid:希望服務天數'], service_data_locked=1),
            dict(id=1, review_identity='client-review', case_no='SYNTH-1',
                 issue_codes=['hcm_field_invalid:縣市'], service_data_locked=1)]
    repository = MySqlHcmResubmissionRepository(Connection(rows))
    monkeypatch.setattr(repository, 'query_review', lambda identity: {'resolved': False})
    page = repository.query_current_reviews(limit=20, before_id=None)
    assert page['items'][0]['can_correct'] is False
    assert page['items'][0]['unavailable_reason'] == 'service_data_locked'
    assert page['items'][1]['can_correct'] is True
