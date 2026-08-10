"""Preserve-data rehearsal remains external without reviving target-host gates."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_preserve_data_package_retired_target_host_acceptance() -> None:
    package = (
        ROOT
        / "document/架構重整/02_決策與退役執行記錄"
        / "51_Preserve_Data_and_Historical_Reprocess_Closure_Work_Package.md"
    ).read_text(encoding="utf-8")

    assert "專用 source→backup→candidate→migration→switch→restart/read-smoke rehearsal" in package
    assert "target-host deployment\nacceptance 已由決策 53 退役" in package
    assert "TLS／HTTP2／latency／target-host worker recovery acceptance\n已由決策 53 退役" in package
