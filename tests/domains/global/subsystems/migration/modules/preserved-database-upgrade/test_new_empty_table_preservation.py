"""Preserve absent-table baselines without relaxing existing-row checks."""
import pytest
from scripts import migrate_preserved_database_additive_schema as migration


@pytest.mark.parametrize('new_count,old_fingerprint,allowed', [(0, 'old', True), (1, 'old', False), (0, 'changed', False)])
def test_new_empty_table_preservation(monkeypatch, new_count, old_fingerprint, allowed):
    absent = migration._local_digest(migration._local_canonical_json({
        'table': 'weekly_report_metrics', 'state': 'absent_or_empty', 'row_count': 0,
    }))
    fingerprints = {'orders': 'old', 'weekly_report_metrics': absent}
    expected = {'data_row_counts': {'orders': 3, 'weekly_report_metrics': 0},
                'data_fingerprints': fingerprints,
                'data_fingerprint_sha256': migration._local_data_fingerprint(fingerprints)}
    actual_fingerprints = {'orders': old_fingerprint, 'weekly_report_metrics': 'new-table-fingerprint'}
    monkeypatch.setattr(migration, '_local_capture_backup_rows', lambda *_: {
        'data_row_counts': {'orders': 3, 'weekly_report_metrics': new_count},
        'data_fingerprints': actual_fingerprints,
        'data_fingerprint_sha256': migration._local_data_fingerprint(actual_fingerprints),
    })
    if allowed:
        migration._local_verify_backup_rows(None, 'lu_test_example', expected)
    else:
        with pytest.raises(migration.LocalAdditiveBlocked, match='fingerprint changed'):
            migration._local_verify_backup_rows(None, 'lu_test_example', expected)
