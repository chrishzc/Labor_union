-- Align persistence with the existing optional manual-response reason contract.
-- Preserve every event and all identity, target, fingerprint and append-only guards.
ALTER TABLE matching_response_events DROP CHECK chk_matching_response_manual_reason;
