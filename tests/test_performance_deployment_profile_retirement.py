"""Performance policy must not recreate a target-host release gate."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "document/架構重整/01_規格基線/12_Global_效能與UX體感架構.md"


def test_performance_baseline_keeps_transport_contract_without_target_host_gate() -> None:
    source = BASELINE.read_text(encoding="utf-8")

    assert "應用程式業務語意不依 HTTP/1.1、HTTP/2、HTTP/3、reverse proxy 或 TLS 設定改變" in source
    assert "不阻擋 release" in source
    assert "DeploymentProtocolEvidencePort" not in source
    assert "HTTP/2／HTTP/3 只以實際部署協定 evidence 驗收" not in source
