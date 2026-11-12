/**
 * 現行銀行工作台的原因文案；原批次人工配對清單已無 UI consumer。
 * 核對抽屜及選款由 bank_reconciliation_workspace.test.tsx 驗證，
 * 匯入原命令與重送由 import_retry.test.tsx 驗證。
 */
import {describe,expect,it} from 'vitest';
import {financeImportReviewReason} from '../adapters/finance/finance_import_query_adapter';

const unrecorded = '未留存當次未核銷原因，請進入核對確認';
const source = {classification_type:'client_receipt',direction:'incoming',available_actions:[],disposition:'business_pending'} as const;

describe('current bank review reasons',()=>{
  it.each([
    ['bank_currency_not_twd','不是新臺幣'],
    ['due_date_missing','缺少正式預計退款日'],
    ['client_subsidy_memo_case_mismatch','定位的案件與所選案件不同'],
    ['client_subsidy_memo_staff_matched','先命中月嫂姓名'],
    ['subsidy_advance_not_due','早於本筆正式到期日'],
    ['subsidy_advance_settlement_ambiguous','正式款項或政府整期資金來源'],
  ])('shows the actual Taishin customer subsidy cause: %s',(code,text)=>{
    const result=financeImportReviewReason({...source,available_actions:[],bank:'taishin',classification_type:'client_subsidy_return',direction:'outgoing',recorded_pending_reason:code});
    expect(result).toContain(text);
  });
  it.each(['outgoing_client_refund_name_ambiguous','outgoing_client_refund_target_ambiguous','client_refund_recipient_account_ambiguous','client_refund_recipient_account_mismatch','client_refund_source_account_missing'])(
    'does not present a removed Taishin customer subsidy code as a current reason: %s',code=>{
      expect(financeImportReviewReason({...source,available_actions:[],bank:'taishin',classification_type:'client_subsidy_return',direction:'outgoing',review_reason:code})).toBe(unrecorded);
    });
  it('keeps the saved subsidy cause before generic or stale operation feedback',()=>{
    const row={...source,available_actions:[],bank:'taishin' as const,classification_type:'client_subsidy_return',direction:'outgoing',recorded_pending_reason:'due_date_missing'};
    for(const dispatch_reason of ['bank_fact_not_eligible','stale_preview'])expect(financeImportReviewReason({...row,dispatch_reason})).toContain('缺少正式預計退款日');
  });
  it.each([
    ['bank_transaction_date_missing','缺少交易日'],
    ['bank_currency_not_twd','不是新臺幣'],
    ['due_date_missing','缺少原預計撥款日'],
    ['outgoing_staff_payout_month_no_match','交易日與預計撥款日都有值'],
    ['staff_payout_amount_mismatch','不符合足額或100元內手續費條件'],
    ['outgoing_staff_payout_multiple_fee_matches','多個單筆或合併付款集合'],
    ['staff_memo_recipient_unconfirmed','原銀行備註的月嫂姓名無法唯一確認'],
    ['cross_staff_allocation_forbidden','原銀行備註確認的月嫂與所選應付款月嫂不同'],
  ])('shows the actual saved Taishin salary step: %s',(code,message)=>{
    const result=financeImportReviewReason({...source,available_actions:[],bank:'taishin',classification_type:'staff_payout',direction:'outgoing',
      review_reason:'unique_staff_payout_name_month_fee_matched',recorded_pending_reason:code});
    expect(result).toContain(message);
    expect(result).not.toContain('未留存');
  });
  it('reads saved Taishin amount aliases without treating old classification evidence as a posting cause',()=>{
    const row={...source,available_actions:[],bank:'taishin' as const,classification_type:'staff_payout',direction:'outgoing'};
    expect(financeImportReviewReason({...row,recorded_pending_reason:'outgoing_staff_payout_amount_mismatch'}))
      .toBe(financeImportReviewReason({...row,recorded_pending_reason:'staff_payout_amount_mismatch'}));
    expect(financeImportReviewReason({...row,review_reason:'outgoing_staff_payout_target_ambiguous'})).toBe(unrecorded);
    expect(financeImportReviewReason({...row,review_reason:'staff_bank_account_ambiguous'})).toBe(unrecorded);
    expect(financeImportReviewReason({...row,dispatch_reason:'outgoing_bank_fact_not_eligible',recorded_pending_reason:'due_date_missing'})).toContain('缺少原預計撥款日');
    expect(financeImportReviewReason({...row,dispatch_reason:'staff_payable_candidate_stale',recorded_pending_reason:'staff_payout_amount_mismatch'})).toContain('不符合足額或100元內手續費條件');
  });
  it.each([
    ['bank_transaction_date_missing','缺少交易日'],
    ['due_date_missing','缺少預計退款日'],
    ['outgoing_client_refund_month_no_match','交易日與預計退款日都有值'],
    ['outgoing_client_refund_amount_mismatch','單筆或同案同月合併待退金額'],
    ['outgoing_client_refund_multiple_fee_matches','多個單筆或合併退款配對'],
    ['client_refund_source_account_missing','原銀行流水未能辨識收款帳號'],
    ['client_refund_recipient_account_mismatch','收款帳號與所選退款單收款帳戶不同'],
    ['client_refund_recipient_account_ambiguous','所選退款單的收款帳戶缺少或不一致'],
  ])('shows the actual saved Sinopac refund step without subsidy copy: %s',(code,text)=>{
    const message=financeImportReviewReason({...source,available_actions:[],bank:'sinopac',classification_type:'client_refund',direction:'outgoing',
      review_reason:'sinopac_unique_client_refund_account_in_transaction_reference',recorded_pending_reason:code});
    expect(message).toContain(text);
    expect(message).not.toContain('補助');
    expect(message).not.toContain('已由交易參考帳號');
  });
  it('does not reinterpret old refund ambiguity and does not replace a saved cause with a generic operation failure',()=>{
    const row={...source,available_actions:[],bank:'sinopac' as const,classification_type:'client_refund' as const,direction:'outgoing' as const};
    expect(financeImportReviewReason({...row,review_reason:'outgoing_client_refund_target_ambiguous'})).toBe(unrecorded);
    expect(financeImportReviewReason({...row,dispatch_reason:'bank_fact_not_eligible',recorded_pending_reason:'due_date_missing'})).toContain('缺少預計退款日');
    expect(financeImportReviewReason({...row,dispatch_reason:'stale_preview',recorded_pending_reason:'outgoing_client_refund_amount_mismatch'})).toContain('合併待退金額');
  });
  it.each([
    ['staff_payout_amount_mismatch','不符合足額或100元內手續費條件'],
    ['due_date_missing','缺少原預計撥款日'],
    ['outgoing_staff_payout_multiple_fee_matches','多個單筆或合併付款集合'],
    ['outgoing_staff_payout_no_open_obligation','目前沒有未清待付款項'],
  ])('shows the saved Sinopac salary cause before successful identification: %s',(recorded_pending_reason,text)=>{
    const message=financeImportReviewReason({...source,bank:'sinopac',classification_type:'staff_payout',direction:'outgoing',available_actions:[],
      recorded_pending_reason,review_reason:'sinopac_unique_staff_account_in_transaction_reference'});
    expect(message).toContain(text);
    expect(message).not.toContain('已由交易參考帳號');
  });
  it.each([
    ['sinopac_client_receipt_shortfall','client_receipt_underpaid'],
    ['sinopac_client_receipt_overage','client_receipt_overpaid'],
    ['sinopac_client_receipt_multiple_same_month_exact','sinopac_client_receipt_multiple_month_candidates'],
    ['sinopac_client_receipt_transaction_date_missing','bank_transaction_date_missing'],
  ])('reads an old receipt reason as the same category without changing stored history: %s',(oldCode,currentCode)=>{
    const render=(reason:string)=>financeImportReviewReason({...source,available_actions:[],recorded_client_receipt_review:{reason,candidates:[]}});
    expect(render(oldCode)).toBe(render(currentCode));
  });

  it('shows the original missing due date and retains an actual overage reason before a refund-operation error',()=>{
    const message=financeImportReviewReason({...source,available_actions:[],recorded_client_receipt_review:{
      reason:'due_date_missing',candidates:[{obligation_identity:'first',obligation_type:'first',due_date:null}],
    }});
    expect(message).toContain('缺少原到期日');
    expect(message).toContain('第一期（到期日 未設定）');
    expect(message).not.toContain('月份不符');
    const overage=financeImportReviewReason({...source,available_actions:[],dispatch_reason:'client_refund_recipient_snapshot_missing',
      recorded_client_receipt_review:{reason:'client_receipt_overpaid',candidates:[]}});
    expect(overage).toContain('核對合計差額');
    expect(overage).not.toContain('退款帳戶');
  });
  it.each([
    ['outgoing_client_refund_no_open_obligation','未清客戶補助退款單'],
    ['due_date_missing','缺少正式預計退款日'],
    ['outgoing_client_refund_month_no_match','交易日與正式預計退款日都有值'],
    ['outgoing_client_refund_amount_mismatch','銀行實付'],
    ['outgoing_client_refund_multiple_fee_matches','多個單筆或合併補助退款配對'],
  ])('shows the saved subsidy failure before the successful memo identification: %s',(recorded_pending_reason,text)=>{
    const message=financeImportReviewReason({...source,available_actions:[],classification_type:'client_subsidy_return',
      review_reason:'taishin_client_subsidy_case_suffix_in_memo',recorded_pending_reason});
    expect(message).toContain(text);
    expect(message).not.toContain('已依備註六碼');
  });
  it.each([
    ['staff_payout','sinopac_unique_staff_account_in_transaction_reference'],
    ['client_refund','sinopac_unique_client_refund_account_in_transaction_reference'],
    ['client_subsidy_return','taishin_client_subsidy_case_suffix_in_memo'],
    ['client_refund','outgoing_client_refund_multiple_fee_matches'],
  ] as const)('does not promote %s classification evidence to a failed posting step: %s',(classification_type,review_reason)=>{
    expect(financeImportReviewReason({...source,available_actions:[],classification_type,direction:'outgoing',review_reason})).toBe(unrecorded);
  });

  it('keeps the recognition result for a historical non-business row',()=>{
    expect(financeImportReviewReason({...source,available_actions:[],classification_type:'non_business_review',direction:'outgoing',review_reason:'taishin_outgoing_unrecognized'}))
      .toContain('備註未辨識到月嫂姓名或可唯一定位案件的六碼');
  });

  it.each([null,'unrecognized_historical_reason'])('does not invent a current cause from missing or unknown history: %s',review_reason=>{
    expect(financeImportReviewReason({...source,available_actions:[],review_reason})).toBe(unrecorded);
  });

  it('shows the recorded formal rejection before classification evidence',()=>{
    expect(financeImportReviewReason({...source,available_actions:[],classification_type:'client_refund',direction:'outgoing',
      review_reason:'unique_client_refund_name_and_month_matched',dispatch_reason:'bank_currency_not_twd'}))
      .toBe('原銀行流水幣別不是新臺幣，無法核銷退款／補助，請先查核來源資料。');
  });

  it('lists the recorded installment dates without selecting a target',()=>{
    const text=financeImportReviewReason({...source,available_actions:[],recorded_client_receipt_review:{
      reason:'sinopac_client_receipt_multiple_same_month_exact',candidates:[
        {obligation_identity:'first',obligation_type:'first',due_date:'2026-10-19'},
        {obligation_identity:'second',obligation_type:'second',due_date:'2026-10-27'},
      ],
    }});
    expect(text).toContain('第一期（到期日 2026-10-19）');
    expect(text).toContain('第二期（到期日 2026-10-27）');
  });
});
