const historicalAccountingReasons: Record<string,string> = {
 historical_client_bank_reconciliation_required: '已有本案銀行收付款待核對，不能視為沒有收付或自行分配期款。',
 historical_client_cash_requires_review: '原收付款與免自備判定不相容，請核對原帳。',
 historical_subsidy_limit_missing: '缺少本案有效補助上限，免自備資格待確認。',
 historical_client_identity_missing: '缺少正式歷史身分，免自備資格待確認。',
 historical_service_hours_missing: '缺少已採納的整案服務時數，免自備資格待確認。',
 historical_original_client_amount_requires_review: '原客戶款項與免自備判定不相容，請核對原帳。',
 historical_client_payment_evidence_requires_review: '歷史付款證據與免自備判定不相容，請核對原來源。',
 historical_client_payment_evidence_stale: '歷史付款證據已過期待核對，不能視為目前已收或銀行入帳。',
 historical_client_finance_source_missing: '尚未確認正式歷史收付款來源，不能認定沒有收付。',
 historical_total_amount_missing: '缺少本案有效總額，免自備金額待確認。',
 subsidy_amount_conflict: '政府補助更正或金額與免自備判定不相容，請核對正式來源。',
 staff_total_amount_conflict: '月嫂正式應付與本案總額不一致，請核對原帳。',
 original_client_amount_requires_review: '原客戶款項與免自備判定不相容，請核對原帳。',
 client_cash_requires_review: '原收付款與免自備判定不相容，請核對原帳。',
 scheduling_effective_generation_invalid: '排班來源版本無效，政府補助金額待確認。',
 pricing_policy_source_missing: '缺少本案有效費率政策，政府補助金額待確認。',
 eligibility_pending: '補助身分待確認，政府補助金額尚未確認。',
 service_volume_pending: '缺少正式服務量，政府補助金額待確認。',
 rate_snapshot_missing: '缺少有效費率快照，政府補助金額待確認。',
 amount_not_integer: '政府補助金額計算不是整數，請核對來源。',
 subsidy_case_source_missing: '未取得本案正式補助計算來源，金額待確認。',
 unique_assignment_required: '歷史月嫂指派歸屬待確認。',
 service_basis_missing: '缺少歷史服務量依據。',
 rate_policy_not_found: '缺少本案有效計薪費率。',
 binding_conflict: '歷史月嫂或款項歸屬有衝突。',
 original_payment_preserved: '保留原應付與付款來源，差額待核對。',
 installment_date_pending: '原應付日期尚未形成。',
 historical_payroll_due_date_missing: '原正式應付缺少到期日，金額與付款紀錄保留。',
 historical_payroll_funding_source_missing: '單筆應付尚缺可證實的付款來源，預計日待確認。',
 historical_payroll_funding_pending: '月嫂付款來源與補助流向尚未確認，預計付款日與分期保留待確認。',
 historical_payroll_funding_conflict: '補助流向與正式款項來源待查，預計付款日與分期保留待確認。',
 historical_payroll_installment_date_pending: '原正式來源分期缺少到期日。',
 historical_payroll_assignment_source_missing: '缺少歷史月嫂指派來源。',
 historical_payroll_assignment_source_ambiguous: '歷史月嫂指派來源不唯一，請核對歸屬。',
 historical_payroll_service_attribution_missing: '多人服務量尚未按月嫂正式採納，不能分攤整案服務量。',
 historical_payroll_service_basis_missing: '缺少本人的歷史服務量依據。',
 payroll_rate_policy_not_found: '缺少本人的有效計薪費率。',
 historical_payroll_end_date_missing: '缺少已採納的歷史結束日，預計付款日待確認。',
 historical_payroll_obligation_not_established: '已有計薪來源，正式應付尚未建立。',
 historical_payroll_unique_assignment_required: '歷史月嫂指派歸屬待確認。',
};
export function accountingReason(reason:string):string {
 return historicalAccountingReasons[reason] ?? `帳務來源待核對（${reason}）。`;
}

export function unallocatedPaymentLabel(kind:string):string {
 if(kind==='receipt')return '原收款';
 if(kind==='refund')return '原退款';
 if(kind==='refund_reversal')return '退款沖正';
 if(kind==='reversal')return '沖正';
 return '原收付款';
}
