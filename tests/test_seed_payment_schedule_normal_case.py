from scripts.seed_payment_schedule_normal_case import (
    DEFAULT_MANIFEST,
    _matches_manifest,
)
from scripts.seed_validation_dataset import DEFAULT_MANIFEST as FOUNDATION_MANIFEST
from scripts.seed_validation_dataset import load_dataset


def test_payment_schedule_normal_case_uses_a_numeric_case_for_virtual_account_reconciliation():
    dataset = load_dataset(DEFAULT_MANIFEST)

    assert dataset["root_case"]["case_no"] == "115000051"
    assert dataset["expected_after_apply"]["virtual_account"] == "99781699115051"
    assert dataset["expected_after_apply"]["deposit_amount_ntd"] == 16000


def test_payment_schedule_normal_customer_identity_is_distinct_from_foundation_case():
    normal = load_dataset(DEFAULT_MANIFEST)
    foundation = load_dataset(FOUNDATION_MANIFEST)

    assert normal["root_case"]["client_attributes"]["name"] != foundation["root_case"]["client_attributes"]["name"]
    assert normal["root_case"]["client_attributes"]["phone"] != foundation["root_case"]["client_attributes"]["phone"]


def test_existing_normal_case_must_match_the_declared_root_identity():
    dataset = load_dataset(DEFAULT_MANIFEST)
    assert _matches_manifest(
        {"case_no": "115000051", "name": "測試正常金流排班客戶051", "phone": "0900000051"},
        dataset,
    )
    assert not _matches_manifest(
        {"case_no": "115000051", "name": "測試正常金流排班客戶", "phone": "0900000002"},
        dataset,
    )
