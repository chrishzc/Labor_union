"""Performance policy must not recreate a target-host release gate."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "document/架構重整/01_規格基線/12_Global_效能與UX體感架構.md"


def test_performance_baseline_keeps_transport_contract_without_target_host_gate() -> None:
    source = BASELINE.read_text(encoding="utf-8")

    assert "HTTP/1.1 request／response 與 compression negotiation 必須正確" in source
    assert "不保存為 deployment profile，也不是產品 release gate" in source
    assert "DeploymentProtocolEvidencePort" not in source
    assert "HTTP/2／HTTP/3 只以實際部署協定 evidence 驗收" not in source
