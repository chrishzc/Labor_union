from datetime import UTC, datetime

from shared_kernel.performance_snapshot import InMemoryApiPerformanceRecorder


def test_api_performance_snapshot_uses_fixed_latency_buckets_not_request_logs():
    recorder = InMemoryApiPerformanceRecorder()
    for elapsed_milliseconds in (50, 150, 600, 2100):
        recorder.record_response_time(elapsed_milliseconds)

    snapshot = recorder.snapshot()

    assert snapshot.request_count == 4
    assert snapshot.average_response_time_ms == 725.0
    assert snapshot.p50_response_time_upper_bound_ms == 250
    assert snapshot.p95_response_time_upper_bound_ms == 5000
    assert snapshot.maximum_response_time_ms == 2100
    assert len(recorder._bucket_counts) == 8


def test_empty_api_performance_snapshot_has_no_timing_values():
    recorder = InMemoryApiPerformanceRecorder()

    snapshot = recorder.snapshot()

    assert isinstance(snapshot.started_at, datetime)
    assert snapshot.started_at.tzinfo is UTC
    assert snapshot.request_count == 0
    assert snapshot.average_response_time_ms is None
    assert snapshot.p50_response_time_upper_bound_ms is None
    assert snapshot.p95_response_time_upper_bound_ms is None
    assert snapshot.maximum_response_time_ms is None
