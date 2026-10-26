/** Retired per-case page delegates to the current whole-period workbench. */
import {render,screen} from '@testing-library/react';
import {expect,it,vi} from 'vitest';
import {SubsidyAdvanceSettlementPanel} from '../../../../../../../components/SubsidyAdvanceSettlementPanel';
vi.mock('../../../../../../../components/SubsidyPeriodWorkbench',()=>({SubsidyPeriodWorkbench:()=> <section aria-label="政府補助整期核銷"/>}));
it('offers whole-period reconciliation without a per-case settlement action',()=>{
  render(<SubsidyAdvanceSettlementPanel initialCaseNo="CASE-1" onOpenImport={vi.fn()}/>);
  expect(screen.getByLabelText('政府補助整期核銷')).toBeInTheDocument();
  expect(screen.queryByRole('button',{name:/銷帳/})).toBeNull();
});
