-- Government return-payout receipts are immutable accounting evidence.

DROP TRIGGER IF EXISTS trg_government_overpayment_return_payouts_before_update;
CREATE TRIGGER trg_government_overpayment_return_payouts_before_update
BEFORE UPDATE ON government_overpayment_return_payouts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government_overpayment_return_payouts records cannot be updated';

DROP TRIGGER IF EXISTS trg_government_overpayment_return_payouts_before_delete;
CREATE TRIGGER trg_government_overpayment_return_payouts_before_delete
BEFORE DELETE ON government_overpayment_return_payouts
FOR EACH ROW SIGNAL SQLSTATE '45000'
SET MESSAGE_TEXT = 'government_overpayment_return_payouts records cannot be deleted';
