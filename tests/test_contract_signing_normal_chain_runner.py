"""Protect configurable append-only normal-chain test data generation."""

from pathlib import Path


RUNNER = Path("scripts/run_contract_signing_normal_chain.py")


def test_normal_chain_runner_defaults_to_five_service_days() -> None:
    source = RUNNER.read_text(encoding="utf-8")

    assert 'parser.add_argument("--service-days", type=int, default=5)' in source
    assert "SERVICE_END = SERVICE_START + timedelta(days=SERVICE_DAYS - 1)" in source
    assert "range(SERVICE_DAYS)" in source
    assert 'order["service_days"] = SERVICE_DAYS' in source
    assert 'terms["deposit_service_days"] = SERVICE_DAYS' not in source
