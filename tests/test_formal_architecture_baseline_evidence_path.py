from scripts import generate_formal_architecture_baseline as generator
from scripts import validate_formal_architecture_baseline as validator


def test_formal_baseline_generator_and_validator_share_the_tracked_evidence_path():
    expected_segment = "03_追蹤清單與證據"

    assert generator.EVIDENCE_PATH == validator.EVIDENCE_PATH
    assert expected_segment in generator.EVIDENCE_PATH.parts
