"""Current HCM field reviews paginate after the owner resolution predicate."""
from datetime import time, timedelta

import pytest

from domains.case_import.hcm_import_review import unresolved_hcm_review_fields
from infrastructure.mysql.hcm_resubmission_repository import MySqlHcmResubmissionRepository


class Cursor:
    def __init__(self, rows, roots):
        self.rows = rows
        self.roots = roots
        self.calls = []
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def execute(self, sql, args):
        self.calls.append((sql, args))
        if 'WHERE r.review_identity=%s' in sql:
            review = next((r for r in self.rows if r['review_identity'] == args[0]), None)
            self.row = None if review is None else {
                **review, 'binding_id': 1, 'client_id': 11,
                'prior_source_event_identity': 'source-1',
                'clients_name': None, 'clients_phone': None, 'clients_city': None,
                **self.roots.get(args[0], {}),
            }
            return
        if 'MAX(resulting_review_version)' in sql:
            self.row = {'review_version': 0}
            return
        before = args[0]
        self.page = [r for r in self.rows if before is None or r['id'] < before][:100]
    def fetchall(self):
        return self.page
    def fetchone(self):
        return self.row


class Connection:
    def __init__(self, rows, roots=None):
        self.reader = Cursor(rows, roots or {})
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


def test_registry_save_resolves_without_a_resubmission_event_and_remains_read_only():
    roots = {'review-1': {'clients_name': None}}
    connection = Connection([dict(id=1, review_identity='review-1', case_no='SYNTH-1',
                                 issue_codes=['hcm_field_missing:姓名'])], roots)
    repository = MySqlHcmResubmissionRepository(connection)
    assert repository.query_review('review-1')['resolved'] is False
    roots['review-1'] = {'clients_name': '範例客戶', 'client_profile_version': 1}
    assert repository.query_review('review-1')['resolved'] is True
    assert repository.query_current_reviews(limit=20, before_id=None)['items'] == []
    roots['review-1']['order_version'] = 2
    assert repository.query_review('review-1')['resolved'] is True
    roots['review-1']['clients_name'] = ' '
    assert repository.query_review('review-1')['resolved'] is False
    assert all(sql.startswith('SELECT') for sql, _ in connection.reader.calls)


def test_multiple_fields_resolve_individually_and_invalid_phone_stays_visible():
    roots = {'review-1': {'clients_name': '範例客戶', 'clients_phone': '123'}}
    connection = Connection([dict(id=1, review_identity='review-1', case_no='SYNTH-1',
                                 issue_codes=['hcm_field_missing:姓名', 'hcm_field_invalid:行動電話'])], roots)
    repository = MySqlHcmResubmissionRepository(connection)
    assert repository.query_current_reviews(limit=20, before_id=None)['items'][0]['fields'] == ['行動電話']
    roots['review-1']['clients_phone'] = '0912345678'
    assert repository.query_current_reviews(limit=20, before_id=None)['items'] == []


def test_current_predicate_keeps_unsupported_fields_and_checks_canonical_terms():
    values = {'clients.name': '範例客戶', 'clients.phone': 'bad',
              'orders.start_date': '2026-09-30', 'orders.service_days': 0}
    assert unresolved_hcm_review_fields(('姓名', '行動電話', '預計服務日期', '希望服務天數', '身分資格'), values) == ('行動電話', '希望服務天數', '身分資格')


@pytest.mark.parametrize('clock', [time(9), timedelta(hours=9), '09:00:00'])
def test_half_hour_terms_and_zero_end_day_offset_are_valid(clock):
    values = {'orders.service_hours_per_day': 4.5, 'orders.service_start_time': clock,
              'orders.service_end_time': time(13, 30), 'orders.service_end_day_offset': 0}
    assert unresolved_hcm_review_fields(('服務時間',), values) == ()
    values['orders.service_end_day_offset'] = None
    assert unresolved_hcm_review_fields(('服務時間',), values) == ('服務時間',)


def test_registry_canonical_choices_resolve_even_when_the_source_workbook_choices_differ():
    values = {'clients.residence_type': '電梯大樓', 'clients.delivery_type': '未定'}
    assert unresolved_hcm_review_fields(('居住型態', '生產方式'), values) == ()
    values['clients.delivery_type'] = '無效選項'
    assert unresolved_hcm_review_fields(('居住型態', '生產方式'), values) == ('生產方式',)
