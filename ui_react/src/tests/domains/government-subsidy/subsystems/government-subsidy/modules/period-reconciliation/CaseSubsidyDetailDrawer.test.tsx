import {cleanup,render,screen} from '@testing-library/react';
import {afterEach,beforeEach,expect,it,vi} from 'vitest';
import {CaseSubsidyDetailDrawer} from '../../../../../../../components/CaseSubsidyDetailDrawer';
import {ordersQueryClient} from '../../../../../../../api/orders/order_query_client';
import {clientFinanceHistoryClient} from '../../../../../../../api/client_finance/client_finance_history_client';
import {clientSubsidyReturnQueryClient} from '../../../../../../../api/client_finance/client_subsidy_return_query_client';
import {subsidyPeriodClient} from '../../../../../../../api/government_subsidy/period_reconciliation_client';
vi.mock('../../../../../../../api/orders/order_query_client',()=>({ordersQueryClient:{getOrderDetail:vi.fn()}}));
vi.mock('../../../../../../../api/client_finance/client_finance_history_client',()=>({clientFinanceHistoryClient:{query:vi.fn()}}));
vi.mock('../../../../../../../api/client_finance/client_subsidy_return_query_client',()=>({clientSubsidyReturnQueryClient:{queryAll:vi.fn()}}));
vi.mock('../../../../../../../api/government_subsidy/period_reconciliation_client',()=>({subsidyPeriodClient:{caseCoverage:vi.fn()}}));
vi.mock('../../../../../../../components/FinanceReceiptsWorkspace',()=>({financeMoney:(n:number)=>`NT$ ${n}`}));
vi.mock('../../../../../../../components/FinanceCaseHistory',()=>({financeEntryLabels:{}}));
beforeEach(()=>{
 vi.mocked(ordersQueryClient.getOrderDetail).mockResolvedValue({client_name:'測試客戶'} as Awaited<ReturnType<typeof ordersQueryClient.getOrderDetail>>);
 vi.mocked(clientFinanceHistoryClient.query).mockResolvedValue({obligations:[],ledger_entries:[]} as unknown as Awaited<ReturnType<typeof clientFinanceHistoryClient.query>>);
 vi.mocked(clientSubsidyReturnQueryClient.queryAll).mockResolvedValue({rows:[]} as unknown as Awaited<ReturnType<typeof clientSubsidyReturnQueryClient.queryAll>>);
});
afterEach(()=>{cleanup();vi.resetAllMocks();});
it.each(['人工補登',null] as const)('shows the original case coverage source without inventing a bank (%s)',async source_label=>{
 vi.mocked(subsidyPeriodClient.caseCoverage).mockResolvedValue({case_no:'CASE',service_end_date:'2026-10-20',amount_ntd:6000,coverage:[{receipt_id:9,label:'2026 第4季',amount_ntd:6000,recorded_case_amount_ntd:6000,recorded_service_end_date:'2026-10-20',recovered_advance_ntd:0,source_label}]});
 render(<CaseSubsidyDetailDrawer embedded caseNo="CASE" onClose={()=>{}} onOpenBank={()=>{}} onChanged={()=>{}}/>);
 const receipt=await screen.findByText(/整期入款 NT\$ 6000/);
 if(source_label)expect(receipt).toHaveTextContent('NT$ 6000 · 人工補登');else expect(receipt).not.toHaveTextContent('人工補登');
 expect(receipt).not.toHaveTextContent('銀行流水');
});
